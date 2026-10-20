/// Thin typed client for the endpoints the mobile app needs.
///
/// Authenticated requests carry the session bearer token; errors surface
/// the API's `detail` verbatim (the same 403/409/422 the web shows).
///
/// Session lifecycle (M7.0):
/// * `POST /auth/login` may answer with an MFA challenge
///   (`{mfa_required: true, mfa_token}`) — see [login] / [verifyMfa];
/// * a 401 on an authenticated call triggers ONE refresh-token rotation
///   (`POST /auth/refresh`, single-flight, new pair persisted before use)
///   and the call is retried once; only if that fails is the session
///   reported expired — the outbox is never touched;
/// * 429 surfaces as [ApiException] with `retryAfter`.
library;

import '../auth/session.dart';
import 'transport.dart';

/// Outcome of a refresh attempt.
enum RefreshOutcome {
  /// New token pair stored.
  refreshed,

  /// The server refused the refresh token: the user must sign in again.
  rejected,

  /// Could not reach the server (offline, timeout, 5xx, 429): try later.
  unavailable,
}

/// What `POST /auth/login` answered.
sealed class LoginOutcome {
  const LoginOutcome();
}

/// Signed in; tokens and profile stored.
class LoginSucceeded extends LoginOutcome {
  const LoginSucceeded(this.profile);

  final SessionProfile? profile;
}

/// A second factor is required: call [HmsClient.verifyMfa] with this token.
class MfaChallenge extends LoginOutcome {
  const MfaChallenge({
    required this.mfaToken,
    this.methods = const ['totp'],
    this.expiresIn = 300,
  });

  final String mfaToken;
  final List<String> methods;
  final int expiresIn;
}

class HmsClient {
  HmsClient({
    required this.transport,
    required this.session,
    this.onUnauthorized,
  });

  final ApiTransport transport;
  final Session session;

  /// Called when the session is dead (401 and the refresh was rejected).
  void Function()? onUnauthorized;

  Future<RefreshOutcome>? _refreshing;

  /// Raw call that returns the [ApiResponse] instead of throwing, so the
  /// sync engine can distinguish 409 (conflict) from 5xx (retry later).
  Future<ApiResponse> sendRaw(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? extraHeaders,
  }) async {
    var res = await _sendAuthed(method, path, body, extraHeaders);
    if (res.status == 401) {
      final outcome = await refresh();
      if (outcome == RefreshOutcome.refreshed) {
        res = await _sendAuthed(method, path, body, extraHeaders);
      }
      if (res.status == 401 && outcome != RefreshOutcome.unavailable) {
        onUnauthorized?.call();
      }
    }
    return res;
  }

  Future<ApiResponse> _sendAuthed(
    String method,
    String path,
    Map<String, dynamic>? body,
    Map<String, String>? extraHeaders,
  ) async {
    final token = await session.accessToken();
    final headers = <String, String>{
      if (token != null) 'Authorization': 'Bearer $token',
      ...?extraHeaders,
    };
    return transport.send(
      method: method,
      path: path,
      body: body,
      headers: headers,
    );
  }

  /// Rotate the refresh token. Concurrent callers share ONE request: the
  /// API treats a replayed (already rotated) refresh token as theft and
  /// revokes the whole session family.
  Future<RefreshOutcome> refresh() {
    final inFlight = _refreshing;
    if (inFlight != null) return inFlight;
    final next = _doRefresh();
    _refreshing = next;
    return next.whenComplete(() => _refreshing = null);
  }

  Future<RefreshOutcome> _doRefresh() async {
    final token = await session.refreshToken();
    if (token == null) return RefreshOutcome.rejected;
    final ApiResponse res;
    try {
      res = await transport.send(
        method: 'POST',
        path: '/auth/refresh',
        body: {'refresh_token': token},
      );
    } catch (_) {
      return RefreshOutcome.unavailable;
    }
    if (res.ok) {
      final access = res.body['access_token'];
      final rotated = res.body['refresh_token'];
      if (access is! String || rotated is! String) {
        return RefreshOutcome.unavailable;
      }
      await session.rotate(accessToken: access, refreshToken: rotated);
      return RefreshOutcome.refreshed;
    }
    if (res.retryable) return RefreshOutcome.unavailable;
    // 401/403/422: the refresh token is dead. Keep the profile (and the
    // outbox) so the same user can sign in again.
    await session.expire();
    return RefreshOutcome.rejected;
  }

  /// Same as [sendRaw] but throws [ApiException] on non-2xx responses.
  Future<Object?> request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? extraHeaders,
  }) async {
    final res =
        await sendRaw(method, path, body: body, extraHeaders: extraHeaders);
    if (!res.ok) {
      throw ApiException(res.status, res.detail, retryAfter: res.retryAfter);
    }
    return res.json;
  }

  Future<Map<String, dynamic>> requestMap(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final json = await request(method, path, body: body);
    if (json is! Map<String, dynamic>) {
      throw ApiException(200, 'Unexpected response shape for $path');
    }
    return json;
  }

  /// `POST /auth/login`. Returns [LoginSucceeded] (session stored) or an
  /// [MfaChallenge]; throws [ApiException] on 401/429/…
  Future<LoginOutcome> login({
    required String email,
    required String password,
    String? organizationSlug,
  }) async {
    final res = await transport.send(
      method: 'POST',
      path: '/auth/login',
      body: {
        'email': email,
        'password': password,
        if (organizationSlug != null && organizationSlug.isNotEmpty)
          'organization_slug': organizationSlug,
      },
    );
    if (!res.ok) {
      throw ApiException(res.status, res.detail, retryAfter: res.retryAfter);
    }
    if (res.body['mfa_required'] == true) {
      final token = res.body['mfa_token'];
      if (token is! String || token.isEmpty) {
        throw ApiException(res.status, 'Malformed MFA challenge');
      }
      final methods = res.body['methods'];
      return MfaChallenge(
        mfaToken: token,
        methods: methods is List
            ? methods.whereType<String>().toList()
            : const ['totp'],
        expiresIn: (res.body['expires_in'] as num?)?.toInt() ?? 300,
      );
    }
    return LoginSucceeded(await _storeAuthSession(res));
  }

  /// `POST /auth/mfa/verify` with a 6-digit TOTP or a recovery code.
  Future<LoginSucceeded> verifyMfa({
    required String mfaToken,
    required String code,
  }) async {
    final res = await transport.send(
      method: 'POST',
      path: '/auth/mfa/verify',
      body: {'mfa_token': mfaToken, 'code': code.trim()},
    );
    if (!res.ok) {
      throw ApiException(res.status, res.detail, retryAfter: res.retryAfter);
    }
    return LoginSucceeded(await _storeAuthSession(res));
  }

  Future<SessionProfile?> _storeAuthSession(ApiResponse res) async {
    final tokens = res.body['tokens'];
    if (tokens is! Map<String, dynamic> ||
        tokens['access_token'] is! String ||
        tokens['refresh_token'] is! String) {
      throw ApiException(res.status, 'Malformed login response');
    }
    final profile = SessionProfile.fromAuthSession(res.body);
    await session.save(
      accessToken: tokens['access_token'] as String,
      refreshToken: tokens['refresh_token'] as String,
      profile: profile,
    );
    return profile;
  }

  /// Best-effort server-side logout; never throws (sign-out works offline).
  Future<void> logout() async {
    try {
      final token = await session.accessToken();
      if (token == null) return;
      await transport.send(
        method: 'POST',
        path: '/auth/logout',
        headers: {'Authorization': 'Bearer $token'},
      );
    } catch (_) {
      // Offline: the local wipe still happens; the server session expires.
    }
  }

  Future<Map<String, dynamic>> me() => requestMap('GET', '/auth/me');

  Future<Map<String, dynamic>> listPatients({int limit = 100}) =>
      requestMap('GET', '/patients?limit=$limit');

  Future<List<dynamic>> listBranches() async {
    final json = await request('GET', '/branches');
    if (json is! List) {
      throw ApiException(200, 'Unexpected response shape for /branches');
    }
    return json;
  }
}
