/// Sync engine: pushes the outbox in order, classifying every outcome.
///
/// * 2xx  -> op applied and removed (replay-safe via `Idempotency-Key`);
///   when the op CREATED an entity its returned id is recorded in the
///   [IdMap], so later ops referring to it as `$ref:…` can push;
/// * 409/412 -> [ConflictKind.versionMismatch] (or
///   [ConflictKind.duplicatePatient] for a duplicate registration) — op
///   parked as conflicted for a human;
/// * other 4xx (403, 422, …) -> [ConflictKind.rejectedByPolicy] — parked,
///   never auto-retried;
/// * 401  -> ONE refresh-token rotation, then the same op (same
///   Idempotency-Key) is retried; if the session cannot be renewed the run
///   STOPS with [ConflictKind.authRequired] and nothing is dropped;
/// * network error / timeout / 408 / 429 / 5xx -> op kept as `failed`
///   with an exponential-backoff-with-jitter retry time (`Retry-After`
///   honoured); the next run after that time retries it automatically. A
///   network-level error also ends the run (the rest stay pending);
/// * an op created by another user -> [ConflictKind.wrongUser], never
///   pushed under this session (audit H20);
/// * an op whose payload still references an entity that has not synced
///   yet is DEFERRED to the next run — never pushed with a bogus id.
///
/// Each op also carries `X-Base-Version`, the server version the device
/// based its change on.
///
/// Only one run happens at a time: a second [sync] call while a run is in
/// progress returns that run's result (manual button + auto trigger).
library;

import '../api/client.dart' show RefreshOutcome;
import '../api/transport.dart';
import '../auth/session.dart';
import 'conflict.dart';
import 'idmap.dart';
import 'outbox.dart';

class SyncResult {
  const SyncResult({
    required this.pushed,
    required this.conflicts,
    required this.failed,
    this.deferred = 0,
    this.synced = const <String>[],
    this.stoppedUnauthorized = false,
  });

  final int pushed;
  final List<Conflict> conflicts;
  final int failed;

  /// Ops left pending because something they reference has not synced yet.
  final int deferred;

  /// Entity labels pushed successfully in this run (the "Synced" state).
  final List<String> synced;

  final bool stoppedUnauthorized;

  bool get clean =>
      failed == 0 &&
      conflicts.isEmpty &&
      deferred == 0 &&
      !stoppedUnauthorized;
}

class SyncEngine {
  SyncEngine({
    required this.transport,
    required this.session,
    required this.outbox,
    IdMap? idMap,
    this.onPersist,
    this.refresh,
    DateTime Function()? clock,
  })  : idMap = idMap ?? IdMap(),
        _clock = clock ?? (() => DateTime.now().toUtc());

  final ApiTransport transport;
  final Session session;
  final Outbox outbox;
  final IdMap idMap;

  /// Called after every run so the graph can seal the outbox + id map into
  /// the encrypted store (restart keeps both).
  final Future<void> Function()? onPersist;

  /// Refresh-token rotation (the [HmsClient.refresh] of the same graph).
  final Future<RefreshOutcome> Function()? refresh;

  final DateTime Function() _clock;

  Future<SyncResult>? _running;

  bool get isRunning => _running != null;

  Future<SyncResult> sync() {
    final running = _running;
    if (running != null) return running;
    final next = _run();
    _running = next;
    return next.whenComplete(() => _running = null);
  }

  Future<SyncResult> _run() async {
    var pushed = 0;
    var failed = 0;
    var deferred = 0;
    final conflicts = <Conflict>[];
    final synced = <String>[];

    final profile = await session.profile();
    final currentUser = profile?.userId;

    // The owner is back: their parked ops may push again.
    for (final op in outbox.ops) {
      if (op.status == OpStatus.conflicted &&
          op.conflictReason == ConflictReason.wrongUser &&
          op.userId != null &&
          op.userId == currentUser) {
        op.status = OpStatus.pending;
        op.conflictReason = null;
        op.lastError = '';
      }
    }

    SyncResult stop({required bool unauthorized}) => SyncResult(
          pushed: pushed,
          conflicts: conflicts,
          failed: failed,
          deferred: deferred,
          synced: synced,
          stoppedUnauthorized: unauthorized,
        );

    for (final op in outbox.eligible(_clock())) {
      // Never push one user's work under another user's session.
      if (op.userId != currentUser) {
        final legacy = op.userId == null;
        op.status = OpStatus.conflicted;
        op.conflictReason = ConflictReason.wrongUser;
        op.lastError = legacy
            ? 'Saved before this app recorded who created it — confirm '
                '"Keep local" to send it under your account, or discard it.'
            : 'Created by another user on this device — it only syncs '
                'when that user signs in.';
        conflicts.add(Conflict(
          op: op,
          kind: ConflictKind.wrongUser,
          detail: op.lastError,
        ));
        continue;
      }

      var token = await session.accessToken();
      if (token == null && refresh != null) {
        final outcome = await refresh!();
        if (outcome == RefreshOutcome.refreshed) {
          token = await session.accessToken();
        } else if (outcome == RefreshOutcome.unavailable) {
          outbox.markFailed(op, 'Could not renew the session (offline)',
              now: _clock());
          failed += 1;
          return _finish(stop(unauthorized: false));
        }
      }
      if (token == null) {
        conflicts.add(Conflict(
          op: op,
          kind: ConflictKind.authRequired,
          detail: 'Not signed in',
        ));
        return _finish(stop(unauthorized: true));
      }

      // Substitute $ref:<local> placeholders with real server ids. A
      // reference that has not synced yet defers this op to the next run.
      final payload = idMap.substitute(op.payload);
      if (payload == null) {
        deferred += 1;
        continue;
      }

      op.status = OpStatus.inFlight;
      ApiResponse res;
      var renewalUnavailable = false;
      try {
        res = await _push(op, payload, token);
        if (res.status == 401 && refresh != null) {
          final outcome = await refresh!();
          if (outcome == RefreshOutcome.refreshed) {
            final renewed = await session.accessToken();
            if (renewed != null) res = await _push(op, payload, renewed);
          } else if (outcome == RefreshOutcome.unavailable) {
            renewalUnavailable = true;
          }
        }
      } catch (err) {
        // Airplane mode / timeout / server unreachable: keep the op, back
        // off, and stop the run — every later op would just wait for the
        // same timeout. They stay pending for the next run.
        outbox.markFailed(op, err.toString(), now: _clock());
        failed += 1;
        return _finish(stop(unauthorized: false));
      }

      if (renewalUnavailable) {
        // 401 and the session could not be renewed right now (offline /
        // server busy): keep the op, retry later — not a dead session.
        outbox.markFailed(op, 'Could not renew the session (offline)',
            now: _clock());
        failed += 1;
        return _finish(stop(unauthorized: false));
      }

      if (res.ok) {
        final created = res.body['id'];
        if (op.localRef != null && created is String) {
          idMap.put(op.localRef!, created);
        }
        outbox.remove(op);
        pushed += 1;
        synced.add(op.entity);
        continue;
      }

      if (res.status == 401) {
        op.status = OpStatus.pending; // nothing pushed for this op
        conflicts.add(Conflict(
          op: op,
          kind: ConflictKind.authRequired,
          detail: res.detail,
        ));
        return _finish(stop(unauthorized: true));
      }

      if (res.retryable) {
        // 408 / 429 / 5xx: transient, NOT a conflict (D15).
        outbox.markFailed(op, res.detail,
            retryAfter: res.retryAfter, now: _clock());
        failed += 1;
        continue;
      }

      if (res.status == 409 || res.status == 412) {
        final rawDetail = res.body['detail'];
        final duplicate = op.method == 'POST' &&
            op.path == '/patients' &&
            rawDetail is Map &&
            rawDetail.containsKey('candidates');
        op.status = OpStatus.conflicted;
        op.conflictReason = duplicate
            ? ConflictReason.duplicatePatient
            : ConflictReason.versionMismatch;
        op.lastError = res.detail;
        conflicts.add(Conflict(
          op: op,
          kind: duplicate
              ? ConflictKind.duplicatePatient
              : ConflictKind.versionMismatch,
          detail: res.detail,
          serverState: res.body,
        ));
        continue;
      }

      // Client-side rejection: retrying the same payload would fail the
      // same way — park it for a human.
      op.status = OpStatus.conflicted;
      op.conflictReason = ConflictReason.rejectedByPolicy;
      op.lastError = res.detail;
      conflicts.add(Conflict(
        op: op,
        kind: ConflictKind.rejectedByPolicy,
        detail: res.detail,
        serverState: res.body,
      ));
    }

    return _finish(stop(unauthorized: false));
  }

  Future<ApiResponse> _push(
    OutboxOp op,
    Map<String, dynamic> payload,
    String token,
  ) =>
      transport.send(
        method: op.method,
        path: op.path,
        body: payload,
        headers: {
          'Authorization': 'Bearer $token',
          'Idempotency-Key': op.id,
          'X-Base-Version': '${op.baseVersion}',
        },
      );

  Future<SyncResult> _finish(SyncResult result) async {
    outbox.markDirty();
    await onPersist?.call();
    return result;
  }
}
