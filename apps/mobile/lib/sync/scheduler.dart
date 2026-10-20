/// Automatic sync triggers (audit D14).
///
/// * [requestSync] runs the engine now (app resumed, unlocked, signed in,
///   something was just queued) — coalesced with any run in progress;
/// * after a run, if ops are waiting on backoff, ONE timer is armed for
///   the earliest retry time, so failed pushes are retried with
///   exponential backoff + jitter without anybody tapping "Retry";
/// * a run that stopped because the session is gone does not re-arm (the
///   user has to sign in again first).
///
/// Disabled by default so unit/widget tests never leave timers behind;
/// `main()` enables it on the device.
library;

import 'dart:async';

import 'engine.dart';
import 'outbox.dart';

class SyncScheduler {
  SyncScheduler({
    required this.engine,
    required this.outbox,
    this.enabled = false,
    this.onResult,
    DateTime Function()? clock,
  }) : _clock = clock ?? (() => DateTime.now().toUtc());

  final SyncEngine engine;
  final Outbox outbox;

  /// Off in tests; switched on by the device wiring.
  bool enabled;

  /// Notified after every automatic or manual run (UI refresh).
  void Function(SyncResult result)? onResult;

  final DateTime Function() _clock;
  Timer? _timer;

  /// When the next automatic retry is armed for, if any.
  DateTime? armedFor;

  /// Run a sync now (if enabled and there is anything to push).
  ///
  /// [force] (app resumed / unlocked / signed in — connectivity may be
  /// back) also retries failed ops whose backoff has not elapsed yet; the
  /// attempt counter is kept, so the backoff keeps growing if it fails.
  Future<SyncResult?> requestSync({bool force = false}) async {
    if (!enabled) return null;
    _cancel();
    if (outbox.total == 0) return null;
    if (force) outbox.retryOpen();
    final result = await engine.sync();
    onResult?.call(result);
    if (!result.stoppedUnauthorized) _armNext();
    return result;
  }

  void _armNext() {
    final at = outbox.nextRetryAt;
    if (at == null || !enabled) return;
    var delay = at.difference(_clock());
    if (delay.isNegative) delay = Duration.zero;
    armedFor = at;
    _timer = Timer(delay, () {
      _timer = null;
      armedFor = null;
      requestSync();
    });
  }

  void _cancel() {
    _timer?.cancel();
    _timer = null;
    armedFor = null;
  }

  /// Stop all automatic activity (sign-out, app disposal).
  void stop() => _cancel();
}
