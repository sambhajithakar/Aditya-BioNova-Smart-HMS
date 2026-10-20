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

  /// QR check-in at the clinic desk. OPT-IN: shown only when the server
  /// explicitly reports it (the check-in endpoint is new — an older server
  /// would answer 404).
  static const qrCheckin = 'qr_checkin';
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
    // The API sends {code, name}; older builds sent a plain string.
    final String? label = switch (edition) {
      final String s when s.isNotEmpty => s,
      {'name': final String name} when name.isNotEmpty => name,
      {'code': final String code} when code.isNotEmpty => code,
      _ => null,
    };
    return ServerFeatures(
      keys: raw is List ? raw.whereType<String>().toSet() : null,
      edition: label,
    );
  }

  /// Enabled feature keys; null when the server did not report them.
  final Set<String>? keys;

  /// Product edition name as reported by the server (display only).
  final String? edition;

  bool has(String key) => keys == null || keys!.contains(key);

  /// True only when the server explicitly reported [key] (opt-in features).
  bool hasExplicit(String key) => keys != null && keys!.contains(key);
}
