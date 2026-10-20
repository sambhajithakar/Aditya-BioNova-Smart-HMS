/// API transport: one small interface between the app and the network.
///
/// Everything above this line (HmsClient, SyncEngine, screens) depends on
/// [ApiTransport], so tests substitute fakes and no widget test touches
/// the network.
library;

import 'dart:convert';
import 'dart:io' show HttpDate, HttpException;

import 'package:http/http.dart' as http;

class ApiResponse {
  const ApiResponse({
    required this.status,
    this.json,
    this.headers = const <String, String>{},
  });

  final int status;

  /// Parsed response body: a JSON object, a JSON array, or null.
  final Object? json;

  /// Response headers, lower-cased names (only `retry-after` is used).
  final Map<String, String> headers;

  bool get ok => status >= 200 && status < 300;

  /// Transient statuses: worth retrying the SAME request later (D15).
  /// 408 (request timeout) and 429 (rate limited) are not conflicts.
  bool get retryable => status == 408 || status == 429 || status >= 500;

  /// `Retry-After` as a duration (delta-seconds or an HTTP date).
  Duration? get retryAfter => parseRetryAfter(headers['retry-after']);

  Map<String, dynamic> get body =>
      json is Map<String, dynamic> ? json as Map<String, dynamic> : const {};

  String get detail {
    final raw = body['detail'];
    if (raw is String) return raw;
    // The duplicate-registration 409 carries {message, candidates}: show
    // the message, not the whole JSON blob.
    if (raw is Map && raw['message'] is String) return raw['message'] as String;
    return jsonEncode(json);
  }
}

Duration? parseRetryAfter(String? raw, {DateTime? now}) {
  if (raw == null || raw.trim().isEmpty) return null;
  final seconds = int.tryParse(raw.trim());
  if (seconds != null) return Duration(seconds: seconds < 0 ? 0 : seconds);
  try {
    final at = HttpDate.parse(raw.trim());
    final delta = at.difference(now ?? DateTime.now().toUtc());
    return delta.isNegative ? Duration.zero : delta;
  } on FormatException {
    return null;
  } on HttpException {
    return null;
  }
}

class ApiException implements Exception {
  ApiException(this.status, this.detail, {this.retryAfter});

  final int status;
  final String detail;
  final Duration? retryAfter;

  /// A message a person can act on (used by the login screen).
  String get readable {
    if (status == 429) {
      final wait = retryAfter;
      if (wait == null) return 'Too many attempts. Please wait and try again.';
      final minutes = (wait.inSeconds / 60).ceil();
      return wait.inSeconds < 60
          ? 'Too many attempts. Try again in ${wait.inSeconds} seconds.'
          : 'Too many attempts. Try again in $minutes minute'
              '${minutes == 1 ? '' : 's'}.';
    }
    return detail;
  }

  @override
  String toString() => 'ApiException($status): $detail';
}

abstract interface class ApiTransport {
  Future<ApiResponse> send({
    required String method,
    required String path,
    Map<String, dynamic>? body,
    Map<String, String>? headers,
  });
}

/// Production transport: talks to `{baseUrl}/api/v1...`.
///
/// Every request has a hard [timeout] (D13): a half-open connection on a
/// flaky rural network must fail (→ retry with backoff), never hang the
/// sync run forever.
class HttpTransport implements ApiTransport {
  HttpTransport({
    required this.baseUrl,
    http.Client? client,
    this.timeout = const Duration(seconds: 20),
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;
  final Duration timeout;

  @override
  Future<ApiResponse> send({
    required String method,
    required String path,
    Map<String, dynamic>? body,
    Map<String, String>? headers,
  }) async {
    final uri = Uri.parse('$baseUrl/api/v1$path');
    final request = http.Request(method, uri)
      ..headers.addAll({'Content-Type': 'application/json', ...?headers});
    if (body != null) {
      request.body = jsonEncode(body);
    }

    final response = await _client
        .send(request)
        .then(http.Response.fromStream)
        .timeout(timeout);

    Object? parsed;
    if (response.body.isNotEmpty) {
      try {
        parsed = jsonDecode(response.body);
      } on FormatException {
        parsed = {'detail': response.body};
      }
    }
    return ApiResponse(
      status: response.statusCode,
      json: parsed,
      headers: response.headers,
    );
  }
}
