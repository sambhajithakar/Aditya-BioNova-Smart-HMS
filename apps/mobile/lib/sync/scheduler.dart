/// Automatic sync triggers (audit D14) — battery-friendly by design.
///
/// * [requestSync] runs the engine now (app resumed, unlocked, signed in,
///   something was just queued, connectivity regained) — coalesced with any
///   run in progress;
/// * after a run, if ops are waiting on backoff, ONE timer is armed for
///   the earliest retry time, so failed pushes are retried with
///   exponential backoff + jitter without anybody tapping "Retry". There is
///   no periodic polling: with nothing queued, no timer exists at all;
/// * the [NetworkMonitor] reports offline → online transitions; the first
///   successful request after an outage triggers one forced run;
/// * on a metered network, large ops wait (see [SyncPolicy]); small
///   clinical drafts are never held back;
/// * a run that stopped because the session is gone does not re-arm (the
///   user has to sign in again first); after [stop] (sign-out / device
///   revocation) nothing fires until [start].
///
/// Disabled by default so unit/widget tests never leave timers behind;
/// `main()` enables it on the device.
library;

import 'dart:async';

import 'engine.dart';
import 'network.dart';
import 'outbox.dart';

class SyncScheduler {
  SyncScheduler({
    required this.engine,
    required this.outbox,
    this.enabled = false,
    this.onResult,
    NetworkMonitor? network,
    this.policy = const SyncPolicy(),
    DateTime Function()? clock,
  })  : network = network ?? NetworkMonitor(),
        _clock = clock ?? (() => DateTime.now().toUtc()) {
    this.network.onRegained = _regained;
    engine.deferIf = (op, bytes) => policy.defer(bytes, this.network.value);
  }

  final SyncEngine engine;
  final Outbox outbox;
  final NetworkMonitor network;
  final SyncPolicy policy;

  /// Off in tests; switched on by the device wiring.
  bool enabled;

  /// Notified after every automatic or manual run (UI refresh).
  void Function(SyncResult result)? onResult;

  final DateTime Function() _clock;
  Timer? _timer;
  bool _stopped = false;

  /// When the next automatic retry is armed for, if any.
  DateTime? armedFor;

  /// Runs triggered by a connectivity regain (diagnostics / tests).
  int regainRuns = 0;

  /// Run a sync now (if enabled and there is anything to push).
  ///
  /// [force] (app resumed / unlocked / signed in — connectivity may be
  /// back) also retries failed ops whose backoff has not elapsed yet; the
  /// attempt counter is kept, so the backoff keeps growing if it fails.
  Future<SyncResult?> requestSync({bool force = false}) async {
    if (!enabled || _stopped) return null;
    _cancel();
    if (outbox.total == 0) return null;
    if (force) outbox.retryOpen();
    final result = await engine.sync();
    onResult?.call(result);
    if (!result.stoppedUnauthorized && !result.halted) _armNext();
    return result;
  }

  void _regained() {
    if (!enabled || _stopped || outbox.total == 0) return;
    regainRuns += 1;
    // Out of the current request's call stack.
    scheduleMicrotask(() => requestSync(force: true));
  }

  void _armNext() {
    final at = outbox.nextRetryAt;
    if (at == null || !enabled || _stopped) return;
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

  /// Stop all automatic activity (sign-out, device revocation, disposal).
  void stop() {
    _stopped = true;
    _cancel();
  }

  /// Allow automatic activity again (after a sign-in).
  void start() => _stopped = false;

  bool get isStopped => _stopped;
}
