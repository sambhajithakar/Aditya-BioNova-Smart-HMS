/// Sync engine: pushes the outbox in dependency order, classifying every
/// outcome.
///
/// * 2xx  -> op applied and removed (replay-safe via `Idempotency-Key`);
///   when the op CREATED an entity its returned id is recorded in the
///   [IdMap], so later ops referring to it as `$ref:…` push in the SAME run
///   with the server id substituted (path and payload);
/// * 409/412 -> [ConflictKind.versionMismatch] (or
///   [ConflictKind.duplicatePatient] for a duplicate registration) — op
///   parked as conflicted for a human; the server body is kept so the
///   conflict screen can show it after a restart;
/// * other 4xx (403, 422, …) -> [ConflictKind.rejectedByPolicy] — parked,
///   never auto-retried;
/// * 401  -> ONE refresh-token rotation, then the same op (same
///   Idempotency-Key) is retried; if the session cannot be renewed the run
///   STOPS with [ConflictKind.authRequired] and nothing is dropped. The
///   401 detail is reported through [onAccessDenied] first, so the graph
///   can tell an administrator's revocation from a plain expiry;
/// * network error / timeout -> op kept as `failed` with backoff, and the
///   run ends (every later op would just wait for the same timeout);
/// * 408 / 429 / 5xx -> op kept as `failed` with exponential backoff +
///   jitter (`Retry-After` honoured); unrelated ops continue. After
///   [Outbox.maxAttempts] the op stops retrying (Action required — poison
///   op isolation). Three 5xx answers in a row end the run (the server is
///   unwell; do not drain the battery on it);
/// * an op created by another user -> [ConflictKind.wrongUser], never
///   pushed under this session (audit H20);
/// * an op whose parent has not synced yet waits (pending); an op whose
///   parent is parked is **blocked** (not attempted); an op whose parent
///   was discarded is **orphaned** (Action required) — never pushed with a
///   bogus id;
/// * [deferIf] lets the scheduler hold back large ops on metered data.
///
/// Each op also carries `X-Base-Version`, the server version the device
/// based its change on.
///
/// Only one run happens at a time: a second [sync] call while a run is in
/// progress returns that run's result (manual button + auto trigger), and
/// an op is never handed to the transport twice concurrently. After
/// [halt] (device revoked) every run is a no-op until [resume].
library;

import 'dart:convert';

import '../api/client.dart' show RefreshOutcome;
import '../api/transport.dart';
import '../auth/session.dart';
import 'conflict.dart';
import 'idmap.dart';
import 'outbox.dart';
import 'planner.dart';

class SyncResult {
  const SyncResult({
    required this.pushed,
    required this.conflicts,
    required this.failed,
    this.deferred = 0,
    this.blocked = 0,
    this.synced = const <String>[],
    this.stoppedUnauthorized = false,
    this.halted = false,
  });

  static const SyncResult idle = SyncResult(
      pushed: 0, conflicts: <Conflict>[], failed: 0);

  final int pushed;
  final List<Conflict> conflicts;
  final int failed;

  /// Ops not pushed in this run because of a dependency (a parent has not
  /// synced yet, or is blocked) or held back by the network policy.
  final int deferred;

  /// The part of [deferred] whose parent needs the user's action (shown as
  /// **Action required**, not retried until the parent is resolved).
  final int blocked;

  /// Entity labels pushed successfully in this run (the "Synced" state).
  final List<String> synced;

  final bool stoppedUnauthorized;

  /// Nothing ran: the engine is halted (device signed out remotely).
  final bool halted;

  bool get clean =>
      failed == 0 &&
      conflicts.isEmpty &&
      deferred == 0 &&
      !stoppedUnauthorized &&
      !halted;
}

class SyncEngine {
  SyncEngine({
    required this.transport,
    required this.session,
    required this.outbox,
    IdMap? idMap,
    this.onPersist,
    this.refresh,
    this.onAccessDenied,
    this.deferIf,
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

  /// Told the `detail` of every 401 before the refresh is attempted.
  final void Function(String detail)? onAccessDenied;

  /// Hold an op back in this run (e.g. a large body on metered data).
  bool Function(OutboxOp op, int payloadBytes)? deferIf;

  final DateTime Function() _clock;

  Future<SyncResult>? _running;
  bool _halted = false;
  final Set<String> _sending = <String>{};

  /// Consecutive 5xx answers that end a run.
  static const int serverErrorCircuit = 3;

  bool get isRunning => _running != null;

  bool get isHalted => _halted;

  /// Stop all pushing (device revoked). In-progress HTTP calls finish; no
  /// new op is started.
  void halt() => _halted = true;

  void resume() => _halted = false;

  Future<SyncResult> sync() {
    if (_halted) {
      return Future.value(const SyncResult(
          pushed: 0, conflicts: <Conflict>[], failed: 0, halted: true));
    }
    final running = _running;
    if (running != null) return running;
    final next = _batched();
    _running = next;
    return next.whenComplete(() => _running = null);
  }

  /// Entities whose create endpoint does not (yet) honour Idempotency-Key
  /// server-side: their "in flight" mark is persisted BEFORE the request,
  /// so a crash mid-push is visible (and the payload frozen) after restart.
  static const Set<String> nonIdempotentEntities = {'appointment', 'encounter'};

  /// Persist checkpoint every N accepted ops during a long run.
  static const int persistEvery = 25;

  Future<SyncResult> _batched() async {
    // One store write per checkpoint instead of one per op: thousands of
    // queued ops must not re-seal the encrypted store thousands of times.
    outbox.beginBatch();
    try {
      return await _run();
    } finally {
      outbox.endBatch();
    }
  }

  Future<SyncResult> _run() async {
    var pushed = 0;
    var failed = 0;
    var deferred = 0;
    var blocked = 0;
    var serverErrors = 0;
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

    SyncResult stop({required bool unauthorized, bool halted = false}) =>
        SyncResult(
          pushed: pushed,
          conflicts: conflicts,
          failed: failed,
          deferred: deferred,
          blocked: blocked,
          synced: synced,
          stoppedUnauthorized: unauthorized,
          halted: halted,
        );

    final planner = SyncPlanner(outbox.ops, idMap);
    final runList = planner.order(outbox.eligible(_clock()));

    for (final op in runList) {
      if (_halted) return _finish(stop(unauthorized: true, halted: true));
      // Removed or re-parked by an earlier step of this run / the user.
      if (op.status != OpStatus.pending && op.status != OpStatus.failed) {
        continue;
      }
      if (_sending.contains(op.id)) continue;

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

      // Dependencies, from the live statuses (a parent may just have
      // synced, failed or been parked earlier in this very run).
      final dep = planner.infoFor(op);
      if (dep.state == DependencyState.waiting) {
        deferred += 1;
        continue;
      }
      if (dep.state == DependencyState.blocked) {
        blocked += 1;
        deferred += 1;
        continue;
      }
      if (dep.state == DependencyState.orphaned) {
        op.status = OpStatus.conflicted;
        op.conflictReason = ConflictReason.orphaned;
        op.lastError = 'It refers to a record that was discarded on this '
            'device, so it can never be sent as it is.';
        conflicts.add(Conflict(
          op: op,
          kind: ConflictKind.rejectedByPolicy,
          detail: op.lastError,
        ));
        continue;
      }

      final payload = idMap.substitute(op.payload);
      final path = idMap.substitutePath(op.path);
      if (payload == null || path == null) {
        deferred += 1;
        continue;
      }

      final hold = deferIf;
      if (hold != null && hold(op, utf8.encode(jsonEncode(payload)).length)) {
        deferred += 1;
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
      if (_halted) return _finish(stop(unauthorized: true, halted: true));

      op.status = OpStatus.inFlight;
      op.everSent = true;
      _sending.add(op.id);
      outbox.markDirty();
      if (nonIdempotentEntities.contains(op.entity)) outbox.flushBatch();
      ApiResponse res;
      var renewalUnavailable = false;
      try {
        res = await _push(op, path, payload, token);
        if (res.status == 401) {
          onAccessDenied?.call(res.detail);
          if (refresh != null && !_halted) {
            final outcome = await refresh!();
            if (outcome == RefreshOutcome.refreshed) {
              final renewed = await session.accessToken();
              if (renewed != null && !_halted) {
                res = await _push(op, path, payload, renewed);
              }
            } else if (outcome == RefreshOutcome.unavailable) {
              renewalUnavailable = true;
            }
          }
        }
      } catch (err) {
        // Airplane mode / timeout / server unreachable: keep the op, back
        // off, and stop the run — every later op would just wait for the
        // same timeout. They stay pending for the next run.
        _sending.remove(op.id);
        op.lastHttpStatus = null;
        outbox.markFailed(op, err.toString(), now: _clock());
        failed += 1;
        return _finish(stop(unauthorized: false));
      }
      _sending.remove(op.id);
      op.lastHttpStatus = res.status;

      if (renewalUnavailable) {
        // 401 and the session could not be renewed right now (offline /
        // server busy): keep the op, retry later — not a dead session.
        outbox.markFailed(op, 'Could not renew the session (offline)',
            now: _clock());
        failed += 1;
        return _finish(stop(unauthorized: false));
      }

      if (res.ok) {
        serverErrors = 0;
        final created = res.body['id'];
        if (op.localRef != null && created is String) {
          idMap.put(op.localRef!, created);
        }
        outbox.remove(op);
        pushed += 1;
        synced.add(op.entity);
        if (pushed % persistEvery == 0) {
          outbox.flushBatch();
          await onPersist?.call();
        }
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
        if (res.status >= 500) {
          serverErrors += 1;
          if (serverErrors >= serverErrorCircuit) {
            return _finish(stop(unauthorized: false));
          }
        }
        continue;
      }
      serverErrors = 0;

      // A 409 from check-in is a definitive answer about the visit (already
      // checked in, appointment cancelled, queued at another branch), not a
      // row that moved on: "keep mine / keep server" makes no sense for it,
      // so it is parked like any other refusal (M8.1).
      if ((res.status == 409 || res.status == 412) && op.entity != 'check_in') {
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
        op.serverSnapshot = _snapshot(res.body);
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
      op.serverSnapshot = _snapshot(res.body);
      conflicts.add(Conflict(
        op: op,
        kind: ConflictKind.rejectedByPolicy,
        detail: res.detail,
        serverState: res.body,
      ));
    }

    return _finish(stop(unauthorized: false));
  }

  /// Keep at most ~8 KB of the server answer with the op (bounded storage).
  static Map<String, dynamic>? _snapshot(Map<String, dynamic> body) {
    if (body.isEmpty) return null;
    final encoded = jsonEncode(body);
    if (encoded.length <= 8 * 1024) return body;
    return {'detail': encoded.substring(0, 8 * 1024)};
  }

  Future<ApiResponse> _push(
    OutboxOp op,
    String path,
    Map<String, dynamic> payload,
    String token,
  ) =>
      transport.send(
        method: op.method,
        path: path,
        body: payload,
        headers: {
          'Authorization': 'Bearer $token',
          'Idempotency-Key': op.id,
          'X-Base-Version': '${op.baseVersion}',
        },
      );

  Future<SyncResult> _finish(SyncResult result) async {
    outbox.markDirty();
    outbox.flushBatch();
    await onPersist?.call();
    return result;
  }
}
