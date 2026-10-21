/// Smart sync engine rules (M8), all against a fake transport:
/// dependency ordering + id rewrite (payload AND path), blocked / orphaned
/// children, backoff → max attempts → Action required, poison-op
/// isolation, the 5xx circuit, crash recovery with the same key, no
/// concurrent double-send, metered deferral, halt, frozen payloads, and a
/// 5,000-op run within time bounds.
library;

import 'dart:async';
import 'dart:math';

import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/sync/engine.dart';
import 'package:aditya_bionova_mobile/sync/idmap.dart';
import 'package:aditya_bionova_mobile/sync/network.dart';
import 'package:aditya_bionova_mobile/sync/outbox.dart';
import 'package:aditya_bionova_mobile/sync/planner.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Future<Session> signedIn() async {
  final s = Session(MemoryTokenStore());
  await s.save(
    accessToken: 'tok',
    refreshToken: 'r',
    profile: const SessionProfile(userId: 'u1'),
  );
  return s;
}

OutboxOp patientOp(Outbox o, String ref, {String name = 'A'}) => o.enqueue(
      entity: 'patient',
      method: 'POST',
      path: '/patients',
      payload: {'full_name': name, 'gender': 'female'},
      dedupeKey: 'p:$ref',
      localRef: ref,
      userId: 'u1',
    );

OutboxOp queueOp(Outbox o, String patientRef, {String key = 'q'}) => o.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': IdMap.placeholder(patientRef), 'branch_id': 'b1'},
      dedupeKey: key,
      userId: 'u1',
    );

void main() {
  group('dependency ordering', () {
    test('a child queued BEFORE its parent is still pushed after it, in the '
        'same run, with the server id substituted', () async {
      final outbox = Outbox();
      // child first (e.g. restored from quarantine in a different order)
      final child = queueOp(outbox, 'loc-p');
      patientOp(outbox, 'loc-p');
      final fake = FakeTransport((c) async => c.path == '/patients'
          ? json({'id': 'srv-p'}, status: 201)
          : json({'id': 'q1'}, status: 201));
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox);

      final r = await engine.sync();

      expect(r.pushed, 2);
      expect(fake.calls.map((c) => c.path), ['/patients', '/opd/queue']);
      expect(fake.calls.last.body!['patient_id'], 'srv-p');
      expect(fake.calls.last.headers!['Idempotency-Key'], child.id);
      expect(outbox.total, 0);
    });

    test(r'$ref in the PATH is rewritten too (encounter → vitals)', () async {
      final outbox = Outbox();
      outbox.enqueue(
        entity: 'encounter',
        method: 'POST',
        path: '/encounters',
        payload: {'patient_id': 'p1', 'branch_id': 'b1'},
        dedupeKey: 'e',
        localRef: 'loc-e',
        userId: 'u1',
      );
      outbox.enqueue(
        entity: 'vitals',
        method: 'POST',
        path: '/encounters/${IdMap.placeholder('loc-e')}/vitals',
        payload: {'pulse': 72},
        dedupeKey: 'v',
        userId: 'u1',
      );
      final fake = FakeTransport((c) async => json({'id': 'srv-e'}, status: 201));
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox);
      await engine.sync();
      expect(fake.calls.map((c) => c.path),
          ['/encounters', '/encounters/srv-e/vitals']);
    });

    test('a parent parked as Conflict BLOCKS its children (not attempted); '
        'resolving the parent unblocks them', () async {
      final outbox = Outbox();
      final parent = patientOp(outbox, 'loc-p');
      queueOp(outbox, 'loc-p');
      var allowDuplicates = false;
      final fake = FakeTransport((c) async {
        if (c.path == '/patients') {
          if (c.body!['allow_duplicates'] == true) allowDuplicates = true;
          return allowDuplicates
              ? json({'id': 'srv-p'}, status: 201)
              : json({
                  'detail': {'message': 'dup', 'candidates': []},
                }, status: 409);
        }
        return json({'id': 'q'}, status: 201);
      });
      final ids = IdMap();
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox, idMap: ids);

      final first = await engine.sync();
      expect(parent.status, OpStatus.conflicted);
      expect(first.blocked, 1);
      expect(fake.calls.where((c) => c.path == '/opd/queue'), isEmpty);
      final planner = SyncPlanner(outbox.ops, ids);
      expect(planner.infoFor(outbox.ops.last).state, DependencyState.blocked);
      expect(planner.infoFor(outbox.ops.last).parent, same(parent));

      // second run: still blocked, still not attempted
      await engine.sync();
      expect(fake.calls.where((c) => c.path == '/opd/queue'), isEmpty);

      outbox.reissue(parent, {...parent.payload, 'allow_duplicates': true});
      final third = await engine.sync();
      expect(third.pushed, 2);
      expect(fake.calls.last.body!['patient_id'], 'srv-p');
    });

    test('a FAILED parent makes the child wait (pending), not blocked',
        () async {
      final outbox = Outbox();
      patientOp(outbox, 'loc-p');
      final child = queueOp(outbox, 'loc-p');
      final fake = FakeTransport((c) async => json({'detail': 'down'}, status: 503));
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox);
      final r = await engine.sync();
      expect(r.deferred, 1);
      expect(r.blocked, 0);
      expect(child.status, OpStatus.pending);
      expect(fake.calls, hasLength(1));
    });

    test('a child whose parent was discarded is ORPHANED (Action required), '
        'never pushed with a bogus id', () async {
      final outbox = Outbox();
      final child = queueOp(outbox, 'gone');
      final fake = FakeTransport((c) async => json({'id': 'x'}, status: 201));
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox);
      await engine.sync();
      expect(fake.calls, isEmpty);
      expect(child.status, OpStatus.conflicted);
      expect(child.conflictReason, ConflictReason.orphaned);
    });

    test('planner order is topological and otherwise FIFO', () {
      final outbox = Outbox();
      final a = queueOp(outbox, 'p2', key: 'a');
      final u = outbox.enqueue(
          entity: 'invoice',
          method: 'POST',
          path: '/billing/invoices',
          payload: {'patient_id': 'srv'},
          dedupeKey: 'u');
      final p2 = patientOp(outbox, 'p2');
      final ordered =
          SyncPlanner(outbox.ops, IdMap()).order(outbox.eligible(DateTime.now()));
      expect(ordered, [p2, a, u]);
    });
  });

  group('retries, poison ops and idempotency', () {
    test('the SAME Idempotency-Key is sent on every retry of an op',
        () async {
      final outbox = Outbox();
      final op = queueOp(outbox, 'x');
      IdMap ids = IdMap({'x': 'srv-x'});
      var n = 0;
      final fake = FakeTransport((c) async =>
          ++n < 3 ? json({'detail': 'busy'}, status: 503) : json({'id': 'q'}));
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox, idMap: ids);
      for (var i = 0; i < 3; i++) {
        outbox.retryOpen(); // skip the backoff wait
        await engine.sync();
      }
      expect(fake.calls, hasLength(3));
      expect(fake.calls.map((c) => c.headers!['Idempotency-Key']).toSet(),
          {op.id});
      expect(outbox.total, 0);
    });

    test('exponential backoff with jitter stays within [d/2, d] and caps',
        () {
      final rng = Random(7);
      for (var n = 1; n <= 12; n++) {
        final d = Outbox.backoffDelay(n, rng: rng);
        final cap = min(2000 * (1 << (n - 1)), 15 * 60 * 1000);
        expect(d.inMilliseconds, inInclusiveRange(cap ~/ 2, cap));
      }
    });

    test('after maxAttempts transient failures the op stops retrying by '
        'itself (Action required); Retry now gives it a fresh budget', () {
      final outbox = Outbox();
      final op = queueOp(outbox, 'x');
      for (var i = 0; i < Outbox.maxAttempts; i++) {
        outbox.markFailed(op, '503');
      }
      expect(op.status, OpStatus.conflicted);
      expect(op.conflictReason, ConflictReason.maxAttempts);
      expect(op.nextAttemptAt, isNull);
      expect(outbox.nextRetryAt, isNull, reason: 'no timer for it any more');
      expect(outbox.retryNow(op), isTrue);
      expect(op.status, OpStatus.pending);
      expect(op.attempts, 0);
    });

    test('poison-op isolation: one op that keeps failing does not block '
        'unrelated ops', () async {
      final outbox = Outbox();
      final poison = outbox.enqueue(
          entity: 'invoice',
          method: 'POST',
          path: '/billing/invoices',
          payload: {'poison': true},
          dedupeKey: 'poison',
          userId: 'u1');
      outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': 'p1', 'branch_id': 'b1'},
          dedupeKey: 'ok',
          userId: 'u1');
      final fake = FakeTransport((c) async => c.body!['poison'] == true
          ? json({'detail': 'boom'}, status: 500)
          : json({'id': 'q'}, status: 201));
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox);
      final r = await engine.sync();
      expect(r.pushed, 1);
      expect(outbox.ops.single, same(poison));
      expect(poison.status, OpStatus.failed);

      // a 422 is parked for a human immediately and also blocks nothing
      final rejected = outbox.enqueue(
          entity: 'invoice',
          method: 'POST',
          path: '/billing/invoices',
          payload: {'bad': true},
          dedupeKey: 'bad',
          userId: 'u1');
      outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': 'p2', 'branch_id': 'b1'},
          dedupeKey: 'ok2',
          userId: 'u1');
      final fake2 = FakeTransport((c) async => c.body!['bad'] == true
          ? json({'detail': 'invalid'}, status: 422)
          : json({'id': 'q2'}, status: 201));
      final engine2 = SyncEngine(
          transport: fake2, session: await signedIn(), outbox: outbox);
      final r2 = await engine2.sync();
      expect(r2.pushed, 1);
      expect(rejected.conflictReason, ConflictReason.rejectedByPolicy);
      expect(rejected.lastHttpStatus, 422);
    });

    test('three 5xx answers in a row end the run (server unwell)', () async {
      final outbox = Outbox();
      for (var i = 0; i < 6; i++) {
        outbox.enqueue(
            entity: 'invoice',
            method: 'POST',
            path: '/billing/invoices',
            payload: {'i': i},
            dedupeKey: 'i$i',
            userId: 'u1');
      }
      final fake = FakeTransport((c) async => json({'detail': 'x'}, status: 502));
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox);
      final r = await engine.sync();
      expect(fake.calls, hasLength(SyncEngine.serverErrorCircuit));
      expect(r.failed, 3);
      expect(outbox.count(OpStatus.pending), 3);
    });
  });

  group('crash recovery and concurrency', () {
    test('an op marked in-flight when the app died is retried with the SAME '
        'key and its payload is frozen', () async {
      final outbox = Outbox();
      final op = queueOp(outbox, 'x', key: 'k');
      op.status = OpStatus.inFlight; // persisted just before the kill
      final restored = Outbox.fromJson(outbox.toJson());
      expect(restored.recoverInFlight(), 1);
      final again = restored.ops.single;
      expect(again.status, OpStatus.pending);
      expect(again.id, op.id);
      expect(again.everSent, isTrue);
      expect(again.editable, isFalse);
      expect(() => again.replacePayload({'x': 1}), throwsStateError);

      final fake = FakeTransport((c) async => json({'id': 'q'}, status: 200));
      final engine = SyncEngine(
          transport: fake,
          session: await signedIn(),
          outbox: restored,
          idMap: IdMap({'x': 'srv'}));
      await engine.sync();
      expect(fake.calls.single.headers!['Idempotency-Key'], op.id);
    });

    test('a never-sent draft can be edited in place (same op, same key)', () {
      final outbox = Outbox();
      final op = queueOp(outbox, 'x');
      expect(op.editable, isTrue);
      op.replacePayload({'patient_id': 'p9', 'branch_id': 'b1'});
      expect(outbox.ops.single.payload['patient_id'], 'p9');
      expect(op.parentRefs, isEmpty);
    });

    test('two sync() calls at once send each op exactly once', () async {
      final outbox = Outbox();
      for (var i = 0; i < 5; i++) {
        outbox.enqueue(
            entity: 'queue_entry',
            method: 'POST',
            path: '/opd/queue',
            payload: {'patient_id': 'p$i', 'branch_id': 'b1'},
            dedupeKey: 'q$i',
            userId: 'u1');
      }
      final gate = Completer<void>();
      final fake = FakeTransport((c) async {
        await gate.future;
        return json({'id': 'x'}, status: 201);
      });
      final engine = SyncEngine(
          transport: fake, session: await signedIn(), outbox: outbox);
      final a = engine.sync();
      final b = engine.sync();
      gate.complete();
      final ra = await a;
      final rb = await b;
      expect(identical(ra, rb), isTrue);
      expect(fake.calls, hasLength(5));
      expect(fake.calls.map((c) => c.headers!['Idempotency-Key']).toSet(),
          hasLength(5));
    });

    test('halt (device revoked) stops every run until resume', () async {
      final outbox = Outbox();
      queueOp(outbox, 'x');
      final fake = FakeTransport((c) async => json({'id': 'q'}, status: 201));
      final engine = SyncEngine(
          transport: fake,
          session: await signedIn(),
          outbox: outbox,
          idMap: IdMap({'x': 's'}));
      engine.halt();
      final r = await engine.sync();
      expect(r.halted, isTrue);
      expect(fake.calls, isEmpty);
      engine.resume();
      expect((await engine.sync()).pushed, 1);
    });
  });

  group('network awareness', () {
    test('metered: large ops wait, small ones go', () async {
      final outbox = Outbox();
      outbox.enqueue(
          entity: 'invoice',
          method: 'POST',
          path: '/billing/invoices',
          payload: {'notes': 'x' * 40000},
          dedupeKey: 'big',
          userId: 'u1');
      outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': 'p1', 'branch_id': 'b1'},
          dedupeKey: 'small',
          userId: 'u1');
      final network = NetworkMonitor()..setMetered(true);
      const policy = SyncPolicy();
      final fake = FakeTransport((c) async => json({'id': 'x'}, status: 201));
      final engine = SyncEngine(
        transport: fake,
        session: await signedIn(),
        outbox: outbox,
        deferIf: (op, bytes) => policy.defer(bytes, network.value),
      );
      final r = await engine.sync();
      expect(r.pushed, 1);
      expect(r.deferred, 1);
      expect(outbox.ops.single.dedupeKey, 'big');
      network.setMetered(false);
      expect((await engine.sync()).pushed, 1);
    });

    test('reachability: an answer means online, an exception offline; '
        'offline → online fires onRegained once', () async {
      final monitor = NetworkMonitor();
      var regained = 0;
      monitor.onRegained = () => regained += 1;
      var fail = true;
      final t = ReachabilityTransport(
          FakeTransport((c) async =>
              fail ? throw Exception('no network') : json({}, status: 503)),
          monitor);
      await expectLater(t.send(method: 'GET', path: '/x'), throwsException);
      expect(monitor.value.isOffline, isTrue);
      fail = false;
      final res = await t.send(method: 'GET', path: '/x');
      expect(res.status, 503);
      expect(monitor.value.isOnline, isTrue);
      await t.send(method: 'GET', path: '/x');
      expect(regained, 1);
    });
  });

  test('5,000 queued ops sync in one run within time bounds, with batched '
      'persistence (not one store write per op)', () async {
    final outbox = Outbox();
    var notifications = 0;
    outbox.onChanged = () => notifications += 1;
    outbox.batch(() {
      for (var i = 0; i < 2500; i++) {
        patientOp(outbox, 'p$i', name: 'Synthetic $i');
        queueOp(outbox, 'p$i', key: 'q$i');
      }
    });
    expect(outbox.total, 5000);
    notifications = 0;
    var n = 0;
    final fake = FakeTransport((c) async => json({'id': 'srv-${n++}'}, status: 201));
    final engine = SyncEngine(
        transport: fake, session: await signedIn(), outbox: outbox);
    final sw = Stopwatch()..start();
    final r = await engine.sync();
    sw.stop();
    expect(r.pushed, 5000);
    expect(outbox.total, 0);
    expect(sw.elapsed, lessThan(const Duration(seconds: 20)));
    expect(notifications, lessThan(5000 ~/ SyncEngine.persistEvery + 10),
        reason: 'persistence is checkpointed, not per op');
  });
}
