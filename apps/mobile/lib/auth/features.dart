/// Server feature awareness: `GET /auth/me` reports the clinic's
/// `edition` and its enabled `features: [feature_key]`.
///
/// Backward compatibility: a server that does not send `features` (older
/// API) means **everything is enabled** — the app never hides a tab because
/// a field is missing. An explicit empty list means nothing is enabled.
library;

/// Feature keys the mobile app understands (others are ignored).
abstract final class FeatureKeys {
  static const opdQueue = 'opd_queue';
  static const consultation = 'consultation';
  static const billing = 'billing';
  static const pharmacy = 'pharmacy';
  static const mobileOffline = 'mobile_offline';
}

class ServerFeatures {
  const ServerFeatures({this.keys, this.edition});

  /// Unknown / not reported: all features enabled.
  static const ServerFeatures all = ServerFeatures();

  /// Parse the `features` / `edition` fields of a `/auth/me` (or login)
  /// body. A missing or malformed `features` field means "all enabled".
  factory ServerFeatures.fromJson(Map<String, dynamic> body) {
    final raw = body['features'];
    final edition = body['edition'];
    return ServerFeatures(
      keys: raw is List ? raw.whereType<String>().toSet() : null,
      edition: edition is String && edition.isNotEmpty ? edition : null,
    );
  }

  /// Enabled feature keys; null when the server did not report them.
  final Set<String>? keys;

  /// Product edition name as reported by the server (display only).
  final String? edition;

  bool has(String key) => keys == null || keys!.contains(key);
}
