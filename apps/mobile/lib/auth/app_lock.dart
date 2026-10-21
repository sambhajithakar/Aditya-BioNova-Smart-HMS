/// Local app lock (audit H22 / D24): a PIN the user sets after the first
/// online sign-in, required on every cold start and after inactivity before
/// any PHI is shown.
///
/// * The PIN is never stored: only `PBKDF2-HMAC-SHA256(pin, salt)` with a
///   16-byte `Random.secure` salt, kept in the Keystore-backed secure store
///   (the same [TokenStore] as the session).
/// * Comparison is constant-time.
/// * After [maxAttempts] consecutive wrong PINs the PIN is erased AND the
///   stored session is expired, so the device needs an online sign-in by
///   the account owner. The outbox is kept (its ops are tagged with their
///   creator and never pushed under anyone else).
library;

import 'dart:convert';
import 'dart:isolate';
import 'dart:math';
import 'dart:typed_data';

import 'package:pointycastle/export.dart';

import 'session.dart';

enum UnlockResult { unlocked, wrongPin, lockedOut }

class AppLock {
  AppLock(
    this._store, {
    this.iterations = 120000,
    this.maxAttempts = 5,
    this.inactivityTimeout = const Duration(minutes: 5),
    this.useIsolate = false,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  static const String pinKey = 'app_lock_pin_v1';
  static const String failuresKey = 'app_lock_failures';

  /// PIN rules: 4–8 digits.
  static final RegExp pinPattern = RegExp(r'^\d{4,8}$');

  final TokenStore _store;
  final int iterations;
  final int maxAttempts;
  final Duration inactivityTimeout;

  /// Derive on a background isolate (device) instead of the UI thread.
  final bool useIsolate;
  final DateTime Function() _clock;

  bool _unlocked = false;
  DateTime? _backgroundedAt;

  /// True once the PIN was entered (or set) in this process.
  bool get isUnlocked => _unlocked;

  Future<bool> hasPin() async => (await _store.read(pinKey)) != null;

  Future<void> setPin(String pin) async {
    if (!pinPattern.hasMatch(pin)) {
      throw ArgumentError('The PIN must be 4 to 8 digits.');
    }
    final rng = Random.secure();
    final salt =
        Uint8List.fromList(List<int>.generate(16, (_) => rng.nextInt(256)));
    final hash = await _derive(pin, salt, iterations);
    await _store.write(
      pinKey,
      jsonEncode({
        'v': 1,
        'alg': 'pbkdf2-hmac-sha256',
        'iter': iterations,
        'salt': _hex(salt),
        'hash': _hex(hash),
      }),
    );
    await _store.delete(failuresKey);
    _unlocked = true;
  }

  Future<UnlockResult> unlock(String pin) async {
    final raw = await _store.read(pinKey);
    if (raw == null) return UnlockResult.lockedOut;
    final record = jsonDecode(raw) as Map<String, dynamic>;
    final salt = _unhex(record['salt'] as String);
    final expected = _unhex(record['hash'] as String);
    final iter = (record['iter'] as num?)?.toInt() ?? iterations;
    final actual = await _derive(pin, salt, iter);

    if (_constantTimeEquals(actual, expected)) {
      await _store.delete(failuresKey);
      _unlocked = true;
      _backgroundedAt = null;
      return UnlockResult.unlocked;
    }

    final failures =
        (int.tryParse(await _store.read(failuresKey) ?? '') ?? 0) + 1;
    if (failures >= maxAttempts) {
      await _store.delete(pinKey);
      await _store.delete(failuresKey);
      await Session(_store).expire();
      _unlocked = false;
      return UnlockResult.lockedOut;
    }
    await _store.write(failuresKey, '$failures');
    return UnlockResult.wrongPin;
  }

  Future<int> remainingAttempts() async =>
      maxAttempts -
      (int.tryParse(await _store.read(failuresKey) ?? '') ?? 0);

  /// A successful ONLINE sign-in (password / MFA) also unlocks.
  void markUnlocked() {
    _unlocked = true;
    _backgroundedAt = null;
  }

  /// Lock now (cold start, sign-out, explicit lock).
  void lock() {
    _unlocked = false;
  }

  /// The app went to the background. Android reports `hidden` both on
  /// the way out and on the way back in, so only the FIRST call counts.
  void onBackground() {
    _backgroundedAt ??= _clock();
  }

  /// The app came back: lock if it was away longer than the timeout.
  /// Returns true when the lock screen must be shown.
  bool onResume() {
    final away = _backgroundedAt;
    _backgroundedAt = null;
    if (away != null && _clock().difference(away) >= inactivityTimeout) {
      _unlocked = false;
    }
    return !_unlocked;
  }

  /// Forget the PIN (sign-out / local reset).
  Future<void> clear() async {
    await _store.delete(pinKey);
    await _store.delete(failuresKey);
    _unlocked = false;
  }

  Future<Uint8List> _derive(String pin, Uint8List salt, int iter) {
    if (!useIsolate) return Future.value(pbkdf2(pin, salt, iter));
    return Isolate.run(() => pbkdf2(pin, salt, iter));
  }

  static Uint8List pbkdf2(String pin, Uint8List salt, int iterations) {
    final derivator = PBKDF2KeyDerivator(HMac(SHA256Digest(), 64))
      ..init(Pbkdf2Parameters(salt, iterations, 32));
    return derivator.process(Uint8List.fromList(utf8.encode(pin)));
  }

  static bool _constantTimeEquals(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a[i] ^ b[i];
    }
    return diff == 0;
  }

  static String _hex(List<int> bytes) =>
      bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

  static Uint8List _unhex(String hex) => Uint8List.fromList(List<int>.generate(
      hex.length ~/ 2,
      (i) => int.parse(hex.substring(i * 2, i * 2 + 2), radix: 16)));
}
