/// D7 refresh-token rotation and D13/D14/D15 sync reliability: timeouts,
/// automatic retry with exponential backoff + jitter (408/429/5xx are NOT
/// conflicts), crash recovery of in-flight ops, and stable idempotency
/// keys across every retry.
library;

import 'dart:async';
import 'dart:math';

import 'package:aditya_bionova_mobile/api/client.dart';
import 'package:aditya_bionova_mobile/api/transport.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:aditya_bionova_mobile/sync/conflict.dart';
import 'package:aditya_bionova_mobile/sync/engine.dart';
import 'package:aditya_bionova_mobile/sync/outbox.dart';
import 'package:aditya_bionova_mobile/sync/scheduler.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'fake_transport.dart';

OutboxOp queueOp(Outbox outbox, [String key = 'k1']) => outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': 'p1', 'branch_id': 'b1'},
      dedupeKey: key,
    );

void main() {
  group('refresh-token rotation (D7)', () {
    late Session session;
    setUp(() async {
      session = Session(MemoryTokenStore());
      await session.save(accessToken: 'old-at', refreshToken: 'old-rt-xxxxxxxxxxxxxxxx');
    });

    test('engine: 401 → refresh → same op retried with the SAME key, new '
        'pair persisted', () async {
      final outbox = Outbox();
      final op = queueOp(outbox);
      final fake = FakeTransport((c) async {
        if (c.path == '/auth/refresh') {
          expect(c.body!['refresh_token'], 'old-rt-xxxxxxxxxxxxxxxx');
          return json({
            'access_token': 'new-at',
            'refresh_token': 'new-rt',
            'token_type': 'bearer',
            'expires_in': 1800,
          });
        }
        if (c.headers!['Authorization'] == 'Bearer old-at') {
          return json({'detail': 'Token expired'}, status: 401);
        }
        return json({'id': 'q1'}, status: 201);
      });
      final client = HmsClient(transport: fake, session: session);
      final engine = SyncEngine(
        transport: fake,
        session: session,
        outbox: outbox,
        refresh: client.refresh,
      );

      final result = await engine.sync();
      expect(result.pushed, 1);
      expect(result.stoppedUnauthorized, isFalse);
      final pushes = fake.calls.where((c) => c.path == '/opd/queue').toList();
      expect(pushes, hasLength(2));
      expect(pushes[0].headers!['Idempotency-Key'], op.id);
      expect(pushes[1].headers!['Idempotency-Key'], op.id);
      expect(pushes[1].headers!['Authorization'], 'Bearer new-at');
      expect(await session.accessToken(), 'new-at');
      expect(await session.refreshToken(), 'new-rt');
    });

    test('refresh rejected → run stops, outbox intact, profile kept',
        () async {
      await session.save(
        accessToken: 'old-at',
        refreshToken: 'old-rt-xxxxxxxxxxxxxxxx',
        profile: const SessionProfile(userId: 'u1'),
      );
      final outbox = Outbox()..ownerId = 'u1';
      queueOp(outbox, 'a');
      queueOp(outbox, 'b');
      final fake = FakeTransport(
          (c) async => json({'detail': 'Session revoked'}, status: 401));
      final client = HmsClient(transport: fake, session: session);
      final engine = SyncEngine(
          transport: fake,
          session: session,
          outbox: outbox,
          refresh: client.refresh);

      final result = await engine.sync();
      expect(result.stoppedUnauthorized, isTrue);
      expect(result.conflicts.single.kind, ConflictKind.authRequired);
      expect(outbox.total, 2);
      expect(outbox.count(OpStatus.pending), 2);
      expect(await session.accessToken(), isNull);
      expect((await session.profile())!.userId, 'u1',
          reason: 'the same user can sign in again and keep the outbox');
    });

    test('refresh unreachable → op kept as failed (backoff), not a dead '
        'session', () async {
      final outbox = Outbox();
      queueOp(outbox);
      final fake = FakeTransport((c) async {
        if (c.path == '/auth/refresh') throw Exception('offline');
        return json({'detail': 'expired'}, status: 401);
      });
      final client = HmsClient(transport: fake, session: session);
      final engine = SyncEngine(
          transport: fake,
          session: session,
          outbox: outbox,
          refresh: client.refresh);

      final result = await engine.sync();
      expect(result.stoppedUnauthorized, isFalse);
      expect(outbox.ops.single.status, OpStatus.failed);
      expect(outbox.ops.single.nextAttemptAt, isNotNull);
      expect(await session.refreshToken(), 'old-rt-xxxxxxxxxxxxxxxx');
    });

    test('client: concurrent 401s share ONE refresh (rotation reuse would '
        'revoke the family)', () async {
      var refreshCalls = 0;
      final gate = Completer<void>();
      final fake = FakeTransport((c) async {
        if (c.path == '/auth/refresh') {
          refreshCalls += 1;
          await gate.future;
          return json({'access_token': 'new-at', 'refresh_token': 'new-rt'});
        }
        if (c.headers!['Authorization'] == 'Bearer old-at') {
          return json({'detail': 'expired'}, status: 401);
        }
        return json({'ok': true});
      });
      final client = HmsClient(transport: fake, session: session);

      final a = client.sendRaw('GET', '/auth/me');
      final b = client.sendRaw('GET', '/branches');
      await Future<void>.delayed(Duration.zero);
      gate.complete();
      final results = await Future.wait([a, b]);

      expect(refreshCalls, 1);
      expect(results.every((r) => r.ok), isTrue);
    });
  });

  group('retry classification and backoff (D14, D15)', () {
    late Session session;
    setUp(() async {
      session = Session(MemoryTokenStore());
      await session.save(accessToken: 'tok', refreshToken: 'r');
    });

    for (final status in [408, 429, 500, 502, 503]) {
      test('$status is retryable, never a conflict', () async {
        final outbox = Outbox();
        queueOp(outbox);
        final now = DateTime.utc(2026, 10, 20, 6);
        final fake = FakeTransport((c) async => json(
              {'detail': 'busy'},
              status: status,
              headers: status == 429 ? {'retry-after': '90'} : const {},
            ));
        final engine = SyncEngine(
            transport: fake, session: session, outbox: outbox, clock: () => now);

        final result = await engine.sync();
        expect(result.conflicts, isEmpty);
        expect(result.failed, 1);
        final op = outbox.ops.single;
        expect(op.status, OpStatus.failed);
        expect(op.nextAttemptAt!.isAfter(now), isTrue);
        if (status == 429) {
          expect(op.nextAttemptAt!.difference(now),
              greaterThanOrEqualTo(const Duration(seconds: 90)),
              reason: 'Retry-After is honoured');
        }
      });
    }

    test('403 / 422 are still parked for a human', () async {
      for (final status in [403, 422]) {
        final outbox = Outbox();
        queueOp(outbox);
        final engine = SyncEngine(
            transport: FakeTransport(
                (c) async => json({'detail': 'no'}, status: status)),
            session: session,
            outbox: outbox);
        final result = await engine.sync();
        expect(result.conflicts.single.kind, ConflictKind.rejectedByPolicy);
      }
    });

    test('backoff grows exponentially, is jittered and capped', () {
      final rng = Random(7);
      for (var n = 1; n <= 12; n++) {
        final d = Outbox.backoffDelay(n, rng: rng);
        final full = min(2000 * (1 << (n - 1)), 15 * 60 * 1000);
        expect(d.inMilliseconds, inInclusiveRange(full ~/ 2, full));
      }
      final samples = {for (var i = 0; i < 20; i++) Outbox.backoffDelay(5)};
      expect(samples.length, greaterThan(1), reason: 'jitter');
      expect(Outbox.backoffDelay(400).inMinutes, lessThanOrEqualTo(15));
    });

    test('a failed op is retried automatically once its backoff elapsed, '
        'with the same Idempotency-Key', () async {
      final outbox = Outbox();
      final op = queueOp(outbox);
      var now = DateTime.utc(2026, 10, 20, 6);
      var up = false;
      final fake = FakeTransport((c) async => up
          ? json({'id': 'q1'}, status: 201)
          : json({'detail': 'down'}, status: 503));
      final engine = SyncEngine(
          transport: fake, session: session, outbox: outbox, clock: () => now);

      await engine.sync();
      expect(op.status, OpStatus.failed);

      // too early: not attempted
      await engine.sync();
      expect(fake.calls, hasLength(1));

      up = true;
      now = op.nextAttemptAt!;
      final result = await engine.sync();
      expect(result.pushed, 1);
      expect(fake.calls.map((c) => c.headers!['Idempotency-Key']).toSet(),
          {op.id});
    });

    test('scheduler arms a timer for the next retry and drains the queue',
        () {
      fakeAsync((async) {
        final outbox = Outbox();
        queueOp(outbox);
        var up = false;
        final fake = FakeTransport((c) async => up
            ? json({'id': 'q1'}, status: 201)
            : json({'detail': 'down'}, status: 502));
        final engine = SyncEngine(
          transport: fake,
          session: session,
          outbox: outbox,
          clock: () => DateTime.utc(2026).add(async.elapsed),
        );
        final results = <SyncResult>[];
        final scheduler = SyncScheduler(
          engine: engine,
          outbox: outbox,
          enabled: true,
          onResult: results.add,
          clock: () => DateTime.utc(2026).add(async.elapsed),
        );

        scheduler.requestSync();
        async.flushMicrotasks();
        expect(results.single.failed, 1);
        expect(scheduler.armedFor, isNotNull);

        up = true;
        async.elapse(const Duration(seconds: 3)); // first backoff ≤ 2 s
        expect(results, hasLength(2));
        expect(results.last.pushed, 1);
        expect(outbox.total, 0);
        expect(scheduler.armedFor, isNull);
        scheduler.stop();
      });
    });

    test('a network error ends the run; later ops stay pending', () async {
      final outbox = Outbox();
      queueOp(outbox, 'a');
      queueOp(outbox, 'b');
      final fake = FakeTransport((c) async => throw Exception('no route'));
      final engine =
          SyncEngine(transport: fake, session: session, outbox: outbox);
      final result = await engine.sync();
      expect(result.failed, 1);
      expect(fake.calls, hasLength(1), reason: 'no second timeout wait');
      expect(outbox.count(OpStatus.failed), 1);
      expect(outbox.count(OpStatus.pending), 1);
    });

    test('forced request (resume / unlock) skips the remaining backoff',
        () async {
      final outbox = Outbox();
      final op = queueOp(outbox);
      var up = false;
      final fake = FakeTransport((c) async => up
          ? json({'id': 'q1'}, status: 201)
          : json({'detail': 'down'}, status: 503));
      final engine =
          SyncEngine(transport: fake, session: session, outbox: outbox);
      final scheduler =
          SyncScheduler(engine: engine, outbox: outbox, enabled: true);
      await scheduler.requestSync();
      expect(op.status, OpStatus.failed);
      expect(op.attempts, 1);

      up = true;
      final plain = await scheduler.requestSync();
      expect(plain!.pushed, 0, reason: 'backoff not elapsed');
      final forced = await scheduler.requestSync(force: true);
      expect(forced!.pushed, 1);
      scheduler.stop();
    });

    test('concurrent sync calls coalesce into one run', () async {
      final outbox = Outbox();
      queueOp(outbox);
      final gate = Completer<void>();
      final fake = FakeTransport((c) async {
        await gate.future;
        return json({'id': 'q'}, status: 201);
      });
      final engine =
          SyncEngine(transport: fake, session: session, outbox: outbox);
      final a = engine.sync();
      final b = engine.sync();
      gate.complete();
      final results = await Future.wait([a, b]);
      expect(identical(results[0], results[1]), isTrue);
      expect(fake.calls, hasLength(1));
    });
  });

  test('an op persisted "in flight" by a crash is re-queued at start-up '
      'with the same id', () async {
    final outbox = Outbox();
    final op = queueOp(outbox)..status = OpStatus.inFlight;
    final doc = <String, dynamic>{
      'outbox': {
        'ops': [op.toJson()],
      },
    };

    final graph = await AppGraph.open(
      baseUrl: 'http://test',
      transportOverride: FakeTransport.routes({}),
      store: MemoryLocalStore(doc),
    );
    expect(graph.outbox.ops.single.status, OpStatus.pending);
    expect(graph.outbox.ops.single.id, op.id);
    await graph.flush();
    expect(((graph.store.doc['outbox'] as Map)['ops'] as List).single['status'],
        'pending');
  });

  test('HttpTransport times out a hung request (D13) and keeps headers',
      () async {
    final hung = HttpTransport(
      baseUrl: 'http://test',
      timeout: const Duration(milliseconds: 50),
      client: MockClient((_) => Completer<http.Response>().future),
    );
    await expectLater(
      hung.send(method: 'GET', path: '/auth/me'),
      throwsA(isA<TimeoutException>()),
    );

    final limited = HttpTransport(
      baseUrl: 'http://test',
      client: MockClient((_) async => http.Response(
            '{"detail":"Too many attempts. Try again later."}',
            429,
            headers: {'retry-after': '30'},
          )),
    );
    final res = await limited.send(method: 'POST', path: '/auth/login');
    expect(res.status, 429);
    expect(res.retryable, isTrue);
    expect(res.retryAfter, const Duration(seconds: 30));
  });

  test('429 on login surfaces Retry-After as a readable message', () async {
    final client = HmsClient(
      transport: FakeTransport((c) async => json(
            {'detail': 'Too many attempts. Try again later.'},
            status: 429,
            headers: {'retry-after': '45'},
          )),
      session: Session(MemoryTokenStore()),
    );
    await expectLater(
      client.login(email: 'a@b.c', password: 'x'),
      throwsA(isA<ApiException>().having(
          (e) => e.readable, 'readable', 'Too many attempts. Try again in 45 seconds.')),
    );
    expect(parseRetryAfter('Wed, 21 Oct 2026 07:28:00 GMT',
            now: DateTime.utc(2026, 10, 21, 7, 27)),
        const Duration(minutes: 1));
    expect(parseRetryAfter('garbage'), isNull);
  });
}
