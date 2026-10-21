/// Offline outbox: mutations captured while the device has no network,
/// replayed later in dependency order.
///
/// Rules (M4 acceptance, hardened in M7.0, smart sync in M8):
/// * every mutation is an [OutboxOp] with a client-generated id (from
///   `Random.secure`) used as the server `Idempotency-Key`; the id NEVER
///   changes across retries, restarts or a crash mid-push, so replay never
///   double-applies;
/// * duplicate prevention: one open op per `dedupeKey` (e.g. "queue the
///   same patient into today's queue twice" stays ONE op);
/// * every op records the user who created it ([OutboxOp.userId]); the
///   sync engine refuses to push an op under anyone else's session;
/// * ops never silently disappear: a failed push keeps the op as `failed`
///   with an exponential-backoff-with-jitter retry time; after
///   [Outbox.maxAttempts] transient failures it stops retrying by itself
///   and becomes **Action required** (poison-op isolation); a server
///   conflict parks it as `conflicted` for the user to resolve — no
///   last-write-wins on clinical or financial data;
/// * dependencies: an op that refers to an entity created by another
///   queued op (`$ref:<localRef>` in its path/payload, or an explicit
///   [OutboxOp.dependsOn]) is pushed only after that parent was accepted —
///   see `planner.dart`;
/// * an op left `inFlight` by a crash is re-queued at start-up
///   ([recoverInFlight]) with the SAME idempotency key;
/// * [toJson]/[fromJson] survive an app restart (offline recovery).
library;

import 'dart:convert';
import 'dart:math';

import 'idmap.dart';

enum OpStatus { pending, inFlight, conflicted, failed }

/// Why an op is parked as `conflicted` (persisted with the op so the Sync
/// centre can offer the right resolution after a restart).
abstract final class ConflictReason {
  /// 409/412: the server row moved on.
  static const String versionMismatch = 'versionMismatch';

  /// 409 from `POST /patients` carrying `candidates`: a possible duplicate
  /// registration. "Keep local" re-sends with `allow_duplicates: true`.
  static const String duplicatePatient = 'duplicatePatient';

  /// Other 4xx: the server refused the payload itself.
  static const String rejectedByPolicy = 'rejectedByPolicy';

  /// The op was created by a different user than the one signed in now.
  static const String wrongUser = 'wrongUser';

  /// The op references a registration that was discarded.
  static const String orphaned = 'orphaned';

  /// Transient failures repeated [Outbox.maxAttempts] times: automatic
  /// retries stop (battery, poison-op isolation) until the user taps
  /// "Retry now" — shown as **Action required**.
  static const String maxAttempts = 'maxAttempts';

  /// Reasons that are a genuine data **Conflict** (the server holds a
  /// different truth); every other reason is **Action required**.
  static const Set<String> dataConflicts = {versionMismatch, duplicatePatient};
}

class OutboxOp {
  OutboxOp({
    required this.id,
    required this.entity,
    required this.method,
    required this.path,
    required this.payload,
    required this.dedupeKey,
    required this.baseVersion,
    required this.createdAt,
    this.status = OpStatus.pending,
    this.attempts = 0,
    this.lastError = '',
    this.localRef,
    this.userId,
    this.conflictReason,
    this.nextAttemptAt,
    this.everSent = false,
    this.lastHttpStatus,
    this.serverSnapshot,
    List<String>? dependsOn,
  }) : dependsOn = dependsOn ?? const <String>[];

  factory OutboxOp.fromJson(Map<String, dynamic> json) => OutboxOp(
        id: json['id'] as String,
        entity: json['entity'] as String,
        method: json['method'] as String,
        path: json['path'] as String,
        payload:
            (json['payload'] as Map<String, dynamic>).cast<String, dynamic>(),
        dedupeKey: json['dedupeKey'] as String,
        baseVersion: json['baseVersion'] as int? ?? 0,
        createdAt: DateTime.parse(json['createdAt'] as String),
        status: OpStatus.values.firstWhere(
          (s) => s.name == json['status'],
          orElse: () => OpStatus.pending,
        ),
        attempts: json['attempts'] as int? ?? 0,
        lastError: json['lastError'] as String? ?? '',
        localRef: json['localRef'] as String?,
        userId: json['userId'] as String?,
        conflictReason: json['conflictReason'] as String?,
        nextAttemptAt: json['nextAttemptAt'] is String
            ? DateTime.tryParse(json['nextAttemptAt'] as String)
            : null,
        everSent: json['everSent'] == true,
        lastHttpStatus: json['lastHttpStatus'] as int?,
        serverSnapshot: json['serverSnapshot'] is Map
            ? (json['serverSnapshot'] as Map).cast<String, dynamic>()
            : null,
        dependsOn: (json['dependsOn'] as List<dynamic>? ?? const [])
            .whereType<String>()
            .toList(),
      );

  /// Client-generated UUID; replayed as the server `Idempotency-Key`.
  final String id;
  final String entity;
  final String method;
  final String path;
  final Map<String, dynamic> payload;
  final String dedupeKey;
  final int baseVersion;

  /// Device-side id of the entity this op CREATES (e.g. a patient
  /// registered offline). Other ops refer to it as `$ref:<localRef>`; the
  /// sync engine swaps in the server id once this op is accepted.
  ///
  /// It is never sent to the API — the server models use `extra=forbid`,
  /// so the placeholder only ever exists on the device.
  final String? localRef;

  /// Server user id of whoever created this op on the device (null only for
  /// ops captured before M7.0 or without a known profile — those can be
  /// claimed by the signed-in user only through an explicit "Keep local").
  String? userId;
  final DateTime createdAt;
  OpStatus status;
  int attempts;
  String lastError;

  /// One of [ConflictReason] while [status] is `conflicted`.
  String? conflictReason;

  /// Earliest time a `failed` op is retried automatically (backoff).
  DateTime? nextAttemptAt;

  /// True once the op has been handed to the network at least once (even
  /// if the app died before the answer arrived). From then on its payload
  /// is frozen: the server may already hold it under this Idempotency-Key,
  /// and a replay with a different body would be answered from the
  /// idempotency store — the edit would be silently lost.
  bool everSent;

  /// HTTP status of the last answer (null: network error / never sent).
  int? lastHttpStatus;

  /// Small server body kept for the conflict screen (e.g. the duplicate
  /// candidates of a 409) — survives a restart.
  Map<String, dynamic>? serverSnapshot;

  /// Explicit parents (local refs) this op must wait for, in addition to
  /// the `$ref:` placeholders found in its path and payload.
  final List<String> dependsOn;

  /// True while the payload may still be edited in place (never sent).
  bool get editable => !everSent && status == OpStatus.pending;

  Map<String, dynamic> toJson() => {
        'id': id,
        'localRef': localRef,
        'userId': userId,
        'entity': entity,
        'method': method,
        'path': path,
        'payload': payload,
        'dedupeKey': dedupeKey,
        'baseVersion': baseVersion,
        'createdAt': createdAt.toIso8601String(),
        'status': status.name,
        'attempts': attempts,
        'lastError': lastError,
        'conflictReason': conflictReason,
        'nextAttemptAt': nextAttemptAt?.toIso8601String(),
        'everSent': everSent,
        'lastHttpStatus': lastHttpStatus,
        'serverSnapshot': ?serverSnapshot,
        if (dependsOn.isNotEmpty) 'dependsOn': dependsOn,
      };

  List<String>? _refs;

  /// Every local ref this op needs resolved before it can be pushed:
  /// explicit [dependsOn] plus `$ref:` placeholders in path and payload.
  /// Computed once per op ([replacePayload] resets the cache).
  List<String> get parentRefs => _refs ??= {
        ...dependsOn,
        ...IdMap.refsIn(path),
        ...IdMap.refsIn(payload),
      }.toList(growable: false);

  /// True when this op depends on `$ref:<localRef>`.
  bool references(String localRef) => parentRefs.contains(localRef);

  /// Replace the body of a never-sent op (edit a draft before it syncs).
  /// Throws [StateError] once the op has been sent — see [everSent].
  void replacePayload(Map<String, dynamic> next) {
    if (!editable) {
      throw StateError('This change has already been sent; it can no '
          'longer be edited on the device.');
    }
    payload
      ..clear()
      ..addAll(next);
    _refs = null;
  }
}

class Outbox {
  Outbox();

  /// Backoff parameters: 2 s, 4 s, 8 s … capped at 15 min, full jitter on
  /// the upper half (so a fleet of devices coming back online together
  /// does not hammer the API in lock step).
  static const Duration backoffBase = Duration(seconds: 2);
  static const Duration backoffCap = Duration(minutes: 15);

  /// Transient failures before automatic retries stop and the op becomes
  /// **Action required** (2 s … 15 min: roughly an hour of trying).
  static const int maxAttempts = 10;

  final List<OutboxOp> _ops = [];

  /// Fired whenever the queue changes, so the graph can persist it to the
  /// encrypted local store (an app restart then keeps every pending op).
  void Function()? onChanged;

  /// Server user id stamped on every new op (the signed-in user).
  String? ownerId;

  int _batchDepth = 0;
  bool _dirtyInBatch = false;

  void markDirty() {
    if (_batchDepth > 0) {
      _dirtyInBatch = true;
      return;
    }
    onChanged?.call();
  }

  /// Run [body] with change notifications coalesced into ONE at the end
  /// (bulk adopt / discard of thousands of ops must not re-seal the store
  /// thousands of times).
  T batch<T>(T Function() body) {
    beginBatch();
    try {
      return body();
    } finally {
      endBatch();
    }
  }

  /// Coalesce notifications until [endBatch] (may span awaits — the sync
  /// engine batches a whole run and calls [flushBatch] periodically).
  void beginBatch() => _batchDepth += 1;

  void endBatch() {
    if (_batchDepth == 0) return;
    _batchDepth -= 1;
    if (_batchDepth == 0) flushBatch();
  }

  /// A change a PERSON made (new op, resolution, discard …): persisted at
  /// once even while a sync run is batching its own bookkeeping — a kill
  /// mid-run must never lose what the user just saved.
  void _durable() {
    markDirty();
    flushBatch();
  }

  /// Deliver a pending coalesced notification now (persist checkpoint).
  void flushBatch() {
    if (!_dirtyInBatch) return;
    _dirtyInBatch = false;
    onChanged?.call();
  }

  static final Random _rng = Random.secure();

  List<OutboxOp> get ops => List.unmodifiable(_ops);

  Iterable<OutboxOp> get pending =>
      _ops.where((o) => o.status == OpStatus.pending);

  /// Ops a sync run should attempt at [now]: pending ones, plus failed ones
  /// whose backoff has elapsed.
  List<OutboxOp> eligible(DateTime now) => [
        for (final o in _ops)
          if (o.status == OpStatus.pending ||
              (o.status == OpStatus.failed &&
                  (o.nextAttemptAt == null || !o.nextAttemptAt!.isAfter(now))))
            o,
      ];

  /// Earliest scheduled automatic retry, if any op is waiting on backoff.
  DateTime? get nextRetryAt {
    DateTime? best;
    for (final o in _ops) {
      final at = o.nextAttemptAt;
      if (o.status != OpStatus.failed || at == null) continue;
      if (best == null || at.isBefore(best)) best = at;
    }
    return best;
  }

  int count(OpStatus status) => _ops.where((o) => o.status == status).length;

  int get total => _ops.length;

  /// Ops not yet accepted by the server (everything still in the queue).
  int get unsynced => _ops.length;

  /// Lookup by op id (the Idempotency-Key).
  OutboxOp? byId(String id) {
    for (final op in _ops) {
      if (op.id == id) return op;
    }
    return null;
  }

  /// Queue a mutation. Returns the EXISTING op when an open op with the
  /// same [dedupeKey] is already queued (offline duplicate prevention).
  OutboxOp enqueue({
    required String entity,
    required String method,
    required String path,
    required Map<String, dynamic> payload,
    required String dedupeKey,
    int baseVersion = 0,
    String? id,
    String? localRef,
    String? userId,
    DateTime? now,
    List<String>? dependsOn,
  }) {
    final existing = openOpFor(dedupeKey);
    if (existing != null) return existing;

    final op = OutboxOp(
      id: id ?? newId(),
      entity: entity,
      method: method,
      path: path,
      payload: payload,
      dedupeKey: dedupeKey,
      baseVersion: baseVersion,
      createdAt: now ?? DateTime.now().toUtc(),
      localRef: localRef,
      userId: userId ?? ownerId,
      dependsOn: dependsOn,
    );
    _ops.add(op);
    _durable();
    return op;
  }

  /// Append ops restored from elsewhere (quarantine release), keeping their
  /// ids — a replay is still answered from the server idempotency store.
  void adopt(Iterable<OutboxOp> ops) {
    final known = {for (final o in _ops) o.id};
    for (final op in ops) {
      if (known.add(op.id)) _ops.add(op);
    }
    _durable();
  }

  /// Remove and return every op (quarantine on device revocation).
  List<OutboxOp> takeAll() {
    final all = List<OutboxOp>.of(_ops);
    _ops.clear();
    _durable();
    return all;
  }

  /// The open (pending/in-flight/failed) op for a dedupe key, if any.
  OutboxOp? openOpFor(String dedupeKey) {
    for (final op in _ops) {
      if (op.dedupeKey == dedupeKey && op.status != OpStatus.conflicted) {
        return op;
      }
    }
    return null;
  }

  /// The op (any state) that creates the entity [localRef], if queued.
  OutboxOp? creatorOf(String localRef) {
    for (final op in _ops) {
      if (op.localRef == localRef) return op;
    }
    return null;
  }

  void remove(OutboxOp op) {
    _ops.remove(op);
    markDirty();
  }

  /// Wipe the queue (sign-out / local reset). Callers must have obtained
  /// the user's explicit confirmation when [unsynced] > 0.
  void clear() {
    _ops.clear();
    _durable();
  }

  /// Crash recovery: an op persisted as `inFlight` was interrupted mid-push.
  /// It goes back to `pending` with the SAME id, so if the server did apply
  /// it the replay is answered from the idempotency store.
  int recoverInFlight() {
    var n = 0;
    for (final op in _ops) {
      if (op.status == OpStatus.inFlight) {
        op.status = OpStatus.pending;
        op.everSent = true; // it may have reached the server
        n += 1;
      }
    }
    if (n > 0) _durable();
    return n;
  }

  /// Record a transient failure (network / timeout / 408 / 429 / 5xx) and
  /// schedule the automatic retry. [retryAfter] (from a 429/503
  /// `Retry-After`) is honoured as a floor. After [maxAttempts] failures the
  /// op stops retrying by itself (Action required).
  void markFailed(
    OutboxOp op,
    String error, {
    Duration? retryAfter,
    DateTime? now,
    Random? rng,
  }) {
    op.attempts += 1;
    op.lastError = error;
    if (op.attempts >= maxAttempts) {
      // Poison-op isolation: stop waking the radio for it and ask a human.
      // Unrelated ops keep syncing.
      op.status = OpStatus.conflicted;
      op.conflictReason = ConflictReason.maxAttempts;
      op.nextAttemptAt = null;
      return;
    }
    op.status = OpStatus.failed;
    var delay = backoffDelay(op.attempts, rng: rng);
    if (retryAfter != null && retryAfter > delay) delay = retryAfter;
    op.nextAttemptAt = (now ?? DateTime.now().toUtc()).add(delay);
  }

  /// Exponential backoff with jitter for the [attempts]-th failure:
  /// a random delay in `[d/2, d]` where `d = min(cap, base * 2^(n-1))`.
  static Duration backoffDelay(int attempts, {Random? rng}) {
    final n = attempts < 1 ? 1 : attempts;
    final exp = n > 20 ? 1 << 20 : 1 << (n - 1);
    var ms = backoffBase.inMilliseconds * exp;
    if (ms > backoffCap.inMilliseconds) ms = backoffCap.inMilliseconds;
    final half = ms ~/ 2;
    return Duration(milliseconds: half + (rng ?? _rng).nextInt(half + 1));
  }

  /// Re-queue everything the user asked to retry now (failed, and
  /// optionally conflicted), skipping any remaining backoff.
  void retryOpen({bool includeConflicted = false}) {
    var changed = false;
    for (final op in _ops) {
      if (op.status == OpStatus.failed ||
          (includeConflicted && op.status == OpStatus.conflicted)) {
        op.status = OpStatus.pending;
        op.lastError = '';
        op.nextAttemptAt = null;
        op.conflictReason = null;
        changed = true;
      }
    }
    if (changed) _durable();
  }

  /// "Retry now" on ONE op (sync dashboard): back to pending, backoff
  /// skipped, SAME id. A max-attempts op gets a fresh attempt budget. Data
  /// conflicts are refused here — they need an explicit resolution.
  bool retryNow(OutboxOp op) {
    if (op.status == OpStatus.inFlight) return false;
    if (op.status == OpStatus.conflicted &&
        op.conflictReason != ConflictReason.maxAttempts &&
        op.conflictReason != ConflictReason.rejectedByPolicy) {
      return false;
    }
    if (op.conflictReason == ConflictReason.maxAttempts) op.attempts = 0;
    op.status = OpStatus.pending;
    op.nextAttemptAt = null;
    op.conflictReason = null;
    op.lastError = '';
    _durable();
    return true;
  }

  /// Resolve a conflict: either discard the local change (server wins for
  /// THAT op — the user explicitly chose it) or re-send it unchanged.
  ///
  /// A discarded op that CREATES an entity takes its dependants with it —
  /// use [discardWithDependents] so the caller can tell the user which.
  void resolveConflict(OutboxOp op, {required bool keepLocal}) {
    if (op.status != OpStatus.conflicted) return;
    if (keepLocal) {
      op.status = OpStatus.pending;
      op.lastError = '';
      op.conflictReason = null;
    } else {
      discardWithDependents(op);
      return;
    }
    _durable();
  }

  /// "Use the server record" for a duplicate registration: the caller has
  /// mapped [op]'s local ref to the EXISTING server patient in the id map;
  /// the registration itself is dropped (never sent), its dependants stay
  /// and will push against the existing patient.
  void resolveUsingServer(OutboxOp op) {
    _ops.remove(op);
    _durable();
  }

  /// Every queued op that (transitively) references the entity [op]
  /// creates — they could never be pushed once [op] is gone.
  List<OutboxOp> dependentsOf(OutboxOp op) {
    final result = <OutboxOp>[];
    final seen = <OutboxOp>{op};
    final refs = <String>[if (op.localRef != null) op.localRef!];
    while (refs.isNotEmpty) {
      final ref = refs.removeLast();
      for (final other in _ops) {
        if (seen.contains(other)) continue;
        if (other.references(ref)) {
          seen.add(other);
          result.add(other);
          if (other.localRef != null) refs.add(other.localRef!);
        }
      }
    }
    final order = {for (var i = 0; i < _ops.length; i++) _ops[i]: i};
    result.sort((a, b) => order[a]!.compareTo(order[b]!));
    return result;
  }

  /// Discard [op] and every op depending on it. Returns the dependants
  /// that were removed (for the user-facing message).
  List<OutboxOp> discardWithDependents(OutboxOp op) {
    final dependents = dependentsOf(op);
    final drop = {op, ...dependents};
    _ops.removeWhere(drop.contains);
    _durable();
    return dependents;
  }

  /// Replace [op] with a NEW op (new id → new `Idempotency-Key`) carrying
  /// [payload], at the same queue position. Used only when the user has
  /// explicitly changed what is being sent (e.g. "register anyway" with
  /// `allow_duplicates: true` after a duplicate 409): the original request
  /// created nothing, and re-using its key would replay the stored 409.
  OutboxOp reissue(OutboxOp op, Map<String, dynamic> payload) {
    final index = _ops.indexOf(op);
    final next = OutboxOp(
      id: newId(),
      entity: op.entity,
      method: op.method,
      path: op.path,
      payload: payload,
      dedupeKey: op.dedupeKey,
      baseVersion: op.baseVersion,
      createdAt: op.createdAt,
      localRef: op.localRef,
      userId: op.userId,
      dependsOn: op.dependsOn,
    );
    if (index < 0) {
      _ops.add(next);
    } else {
      _ops[index] = next;
    }
    _durable();
    return next;
  }

  String toJson() => jsonEncode({
        'ops': _ops.map((o) => o.toJson()).toList(),
      });

  factory Outbox.fromJson(String source) {
    final outbox = Outbox();
    final decoded = jsonDecode(source) as Map<String, dynamic>;
    final ops = decoded['ops'] as List<dynamic>? ?? const [];
    for (final raw in ops) {
      outbox._ops.add(OutboxOp.fromJson(
          (raw as Map<String, dynamic>).cast<String, dynamic>()));
    }
    return outbox;
  }

  /// RFC 4122 v4 UUID from a cryptographically secure RNG (D18): it is the
  /// server-side idempotency key, so it must not be predictable.
  static String newId() {
    final bytes = List<int>.generate(16, (_) => _rng.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }
}
