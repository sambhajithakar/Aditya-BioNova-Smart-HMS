/// LAN demo build (opt-in): the app talks to a demo server on the owner's
/// own computer, whose address is typed in on the phone.
///
/// Built only with `--dart-define=HMS_DEMO_LAN=true` (see docs/DEMO.md).
/// The same flag makes Gradle overlay a network policy that permits
/// cleartext HTTP, so this build is debug-signed only and never for
/// distribution. Every other build is unchanged: the API base is fixed at
/// build time and release builds are HTTPS-only.
///
/// Plain `http://` is accepted only for private LAN addresses
/// (10/8, 172.16/12, 192.168/16, `*.local`) so a demo phone cannot be
/// pointed at a cleartext server on the internet. `https://` is accepted
/// for any host. The demo server holds synthetic data only.
library;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const bool kDemoLan = bool.fromEnvironment('HMS_DEMO_LAN');

/// Port of the demo API when the address has none (docs/DEMO.md).
const int kDemoDefaultPort = 8000;

/// Normalise what the user typed into `scheme://host:port`, or null when
/// it is not acceptable. A bare `192.168.1.20` becomes
/// `http://192.168.1.20:8000`.
String? normalizeDemoServer(String input) {
  var text = input.trim();
  if (text.isEmpty) return null;
  if (!text.contains('://')) text = 'http://$text';
  final Uri uri;
  try {
    uri = Uri.parse(text);
  } on FormatException {
    return null;
  }
  if (uri.scheme != 'http' && uri.scheme != 'https') return null;
  if (uri.host.isEmpty || uri.userInfo.isNotEmpty) return null;
  if (uri.hasQuery || uri.hasFragment) return null;
  if (uri.path.isNotEmpty && uri.path != '/') return null;
  if (uri.scheme == 'http' && !isPrivateLanHost(uri.host)) return null;
  // Uri drops a port equal to the scheme default (":80"), so read the
  // typed one; with none, http means the demo API port.
  final typed = RegExp(r'^[a-z]+://[^/?#]*:(\d+)$|^[a-z]+://[^/?#]*:(\d+)/')
      .firstMatch(text.toLowerCase());
  final port = typed != null
      ? int.parse(typed.group(1) ?? typed.group(2)!)
      : (uri.scheme == 'https' ? 443 : kDemoDefaultPort);
  if (port < 1 || port > 65535) return null;
  return '${uri.scheme}://${uri.host}:$port';
}

/// Private IPv4 ranges (RFC 1918) and mDNS `.local` names.
bool isPrivateLanHost(String host) {
  final h = host.toLowerCase();
  if (h.endsWith('.local') && h.length > '.local'.length) return true;
  final parts = h.split('.');
  if (parts.length != 4) return false;
  final octets = <int>[];
  for (final p in parts) {
    if (p.isEmpty || p.length > 3 || !RegExp(r'^\d+$').hasMatch(p)) {
      return false;
    }
    final v = int.parse(p);
    if (v > 255) return false;
    octets.add(v);
  }
  final a = octets[0], b = octets[1];
  return a == 10 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168);
}

/// The chosen demo server, kept on the phone (Keystore-backed storage).
class DemoServerStore {
  DemoServerStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const keyName = 'hms_demo_server';

  final FlutterSecureStorage _storage;

  Future<String?> read() async {
    final v = await _storage.read(key: keyName);
    return v == null ? null : normalizeDemoServer(v);
  }

  Future<void> write(String url) => _storage.write(key: keyName, value: url);

  Future<void> clear() => _storage.delete(key: keyName);
}
