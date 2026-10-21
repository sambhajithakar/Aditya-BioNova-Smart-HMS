/// Session storage: tokens + the signed-in user's profile.
///
/// Tests use [MemoryTokenStore]; on the device [TokenStore] is backed by
/// flutter_secure_storage (Android Keystore — `SecureTokenStore` in
/// `store/platform_stores.dart`). Nothing outside this file knows which
/// implementation is in use.
///
/// The profile (user id, e-mail, name, organisation, role) is kept next to
/// the tokens so the app can start offline after a restart (audit H22) and
/// so every outbox op can be stamped with the user who created it (H20).
library;

import 'dart:convert';

import 'features.dart';
import 'roles.dart';

abstract interface class TokenStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}

class MemoryTokenStore implements TokenStore {
  final Map<String, String> _data = {};

  @override
  Future<String?> read(String key) async => _data[key];

  @override
  Future<void> write(String key, String value) async {
    _data[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    _data.remove(key);
  }
}

/// Who is signed in on this device.
class SessionProfile {
  const SessionProfile({
    required this.userId,
    this.email = '',
    this.fullName = '',
    this.organizationId = '',
    this.organizationName = '',
    this.role = '',
    this.features,
    this.edition,
    this.permissions,
  });

  factory SessionProfile.fromJson(Map<String, dynamic> json) => SessionProfile(
        userId: json['userId'] as String? ?? '',
        email: json['email'] as String? ?? '',
        fullName: json['fullName'] as String? ?? '',
        organizationId: json['organizationId'] as String? ?? '',
        organizationName: json['organizationName'] as String? ?? '',
        role: json['role'] as String? ?? '',
        features: json['features'] is List
            ? (json['features'] as List).whereType<String>().toList()
            : null,
        edition: json['edition'] as String?,
        permissions: json['permissions'] is List
            ? (json['permissions'] as List).whereType<String>().toList()
            : null,
      );

  /// Build from the API's `AuthSessionOut` body (login / MFA verify).
  static SessionProfile? fromAuthSession(Map<String, dynamic> body) {
    final user = body['user'];
    if (user is! Map || user['id'] is! String) return null;
    final org = body['organization'];
    return SessionProfile(
      userId: user['id'] as String,
      email: (user['email'] as String?) ?? '',
      fullName: (user['full_name'] as String?) ?? '',
      organizationId: org is Map ? (org['id'] as String?) ?? '' : '',
      organizationName: org is Map ? (org['name'] as String?) ?? '' : '',
      role: (body['role'] as String?) ?? '',
      features: ServerFeatures.fromJson(body).keys?.toList(),
      edition: ServerFeatures.fromJson(body).edition,
      permissions: Permissions.fromJson(body).keys?.toList(),
    );
  }

  final String userId;
  final String email;
  final String fullName;
  final String organizationId;
  final String organizationName;
  final String role;

  /// Feature keys the server reported (`/auth/me` `features`); null when it
  /// did not report any — every feature is then treated as enabled.
  final List<String>? features;

  /// Product edition reported by the server, if any.
  final String? edition;

  /// Permission keys from `/auth/me` (null: not reported).
  final List<String>? permissions;

  Permissions get serverPermissions => permissions == null
      ? Permissions.unknown
      : Permissions(permissions!.toSet());

  /// The feature set to gate the UI with (works offline after a restart).
  ServerFeatures get serverFeatures => ServerFeatures(
        keys: features?.toSet(),
        edition: edition,
      );

  /// A copy carrying what `GET /auth/me` just reported.
  SessionProfile withServerInfo({
    String? role,
    ServerFeatures? features,
    Permissions? permissions,
  }) =>
      SessionProfile(
        userId: userId,
        email: email,
        fullName: fullName,
        organizationId: organizationId,
        organizationName: organizationName,
        role: role ?? this.role,
        features: features == null ? this.features : features.keys?.toList(),
        edition: features == null ? edition : features.edition,
        permissions:
            permissions == null ? this.permissions : permissions.keys?.toList(),
      );

  Map<String, dynamic> toJson() => {
        'userId': userId,
        'email': email,
        'fullName': fullName,
        'organizationId': organizationId,
        'organizationName': organizationName,
        'role': role,
        'features': ?features,
        'edition': ?edition,
        'permissions': ?permissions,
      };
}

class Session {
  Session(this._store);

  static const accessTokenKey = 'access_token';
  static const refreshTokenKey = 'refresh_token';
  static const profileKey = 'session_profile';

  final TokenStore _store;
  SessionProfile? _profile;
  bool _profileLoaded = false;

  /// The underlying secure store (the app lock keeps its PIN hash here).
  TokenStore get store => _store;

  Future<void> save({
    required String accessToken,
    required String refreshToken,
    SessionProfile? profile,
  }) async {
    await _store.write(accessTokenKey, accessToken);
    await _store.write(refreshTokenKey, refreshToken);
    if (profile != null) {
      await _store.write(profileKey, jsonEncode(profile.toJson()));
      _profile = profile;
      _profileLoaded = true;
    }
  }

  /// Replace the stored profile (e.g. after `/auth/me` reported a new role
  /// or feature set) without touching the tokens.
  Future<void> updateProfile(SessionProfile profile) async {
    await _store.write(profileKey, jsonEncode(profile.toJson()));
    _profile = profile;
    _profileLoaded = true;
  }

  /// Persist a rotated token pair (refresh flow) without touching the
  /// profile.
  Future<void> rotate({
    required String accessToken,
    required String refreshToken,
  }) =>
      save(accessToken: accessToken, refreshToken: refreshToken);

  Future<String?> accessToken() => _store.read(accessTokenKey);

  Future<String?> refreshToken() => _store.read(refreshTokenKey);

  /// True when a session was stored on this device (it may have expired —
  /// the refresh flow or a re-login decides that when we are online).
  Future<bool> hasStoredSession() async =>
      (await refreshToken()) != null || (await accessToken()) != null;

  Future<SessionProfile?> profile() async {
    if (_profileLoaded) return _profile;
    final raw = await _store.read(profileKey);
    if (raw != null) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is Map<String, dynamic>) {
          _profile = SessionProfile.fromJson(decoded);
        }
      } on FormatException {
        _profile = null;
      }
    }
    _profileLoaded = true;
    return _profile;
  }

  /// Synchronous view of the profile once [profile] has been awaited.
  SessionProfile? get cachedProfile => _profile;

  /// Drop the access token only: the server rejected it and refresh failed.
  /// The profile stays, so the same user can sign in again without losing
  /// the outbox.
  Future<void> expire() async {
    await _store.delete(accessTokenKey);
    await _store.delete(refreshTokenKey);
  }

  /// Forget everything (sign-out).
  Future<void> clear() async {
    await _store.delete(accessTokenKey);
    await _store.delete(refreshTokenKey);
    await _store.delete(profileKey);
    _profile = null;
    _profileLoaded = true;
  }
}
