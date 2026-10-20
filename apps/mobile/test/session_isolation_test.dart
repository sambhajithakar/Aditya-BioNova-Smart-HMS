/// H20 / D7: sign-out warns about unsynced work, then wipes everything the
/// user left on the device; ops are tagged with their creator and are
/// never pushed under another user's session.
library;

import 'package:aditya_bionova_mobile/auth/app_lock.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:aditya_bionova_mobile/sync/conflict.dart';
import 'package:aditya_bionova_mobile/sync/outbox.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

const userA = SessionProfile(userId: 'user-a', email: 'a@clinic.test');
const userB = SessionProfile(userId: 'user-b', email: 'b@clinic.test');

Future<AppGraph> boot(FakeTransport fake, {MemoryTokenStore? tokens}) async {
  final store = tokens ?? MemoryTokenStore();
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: fake,
    tokenStore: store,
    appLock: AppLock(store, iterations: 1000),
    store: MemoryLocalStore({
      'directory': {
        'patients': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Aarti Patil'},
        ],
        'branches': [
          {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
        ],
        'drugs': <dynamic>[],
      },
      'rx_drafts': {
        'drafts': [
          {'localRef': 'rx1', 'patientLabel': 'Aarti', 'items': <dynamic>[]},
        ],
      },
      'idmap': {
        'ids': {'loc1': 'srv1'},
      },
    }),
  );
  return graph;
}

Future<void> signIn(AppGraph graph, SessionProfile who) async {
  await graph.session.save(accessToken: 'tok', refreshToken: 'r', profile: who);
  await graph.onSignedIn(who);
}

OutboxOp queueOp(AppGraph graph, String key) => graph.outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': 'p1', 'branch_id': 'b1'},
      dedupeKey: key,
    );

FakeTransport server() => FakeTransport.routes({
      'GET /auth/me': json({'role': 'receptionist'}),
      'GET /patients': json({'items': <dynamic>[], 'total': 0}),
      'GET /branches': json([
        {'id': 'b1', 'name': 'Main'},
      ]),
      'POST /opd/queue': json({'id': 'q1'}, status: 201),
      'POST /auth/logout': json({'status': 'logged_out'}),
    });

void main() {
  test('every op records the user who created it', () async {
    final graph = await boot(server());
    await signIn(graph, userA);
    final op = queueOp(graph, 'k1');
    expect(op.userId, 'user-a');
    // survives a restart
    final restored = Outbox.fromJson(graph.outbox.toJson());
    expect(restored.ops.single.userId, 'user-a');
  });

  test("another user's ops are parked, never pushed — and push again when "
      'their creator signs back in', () async {
    final fake = server();
    final graph = await boot(fake);
    await signIn(graph, userA);
    final op = queueOp(graph, 'k1');

    // A's session expires; B signs in on the same phone
    await signIn(graph, userB);
    final asB = await graph.engine.sync();
    expect(asB.pushed, 0);
    expect(asB.conflicts.single.kind, ConflictKind.wrongUser);
    expect(op.status, OpStatus.conflicted);
    expect(op.conflictReason, ConflictReason.wrongUser);
    expect(fake.calls.where((c) => c.path == '/opd/queue'), isEmpty,
        reason: "A's op must never travel under B's token");

    // B's own op still syncs
    queueOp(graph, 'k2');
    final mine = await graph.engine.sync();
    expect(mine.pushed, 1);

    // A signs in again: the parked op is released and pushed
    await signIn(graph, userA);
    final asA = await graph.engine.sync();
    expect(asA.pushed, 1);
    expect(graph.outbox.total, 0);
  });

  test('a legacy op without a creator is parked until someone claims it',
      () async {
    final graph = await boot(server());
    graph.outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': 'p1', 'branch_id': 'b1'},
      dedupeKey: 'legacy',
    );
    await signIn(graph, userB);
    final result = await graph.engine.sync();
    expect(result.conflicts.single.kind, ConflictKind.wrongUser);
    expect(graph.outbox.ops.single.lastError, contains('Keep local'));
  });

  testWidgets('sign-out with unsynced work warns; cancel keeps everything',
      (tester) async {
    final graph = await boot(server());
    await signIn(graph, userA);
    queueOp(graph, 'k1');

    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sign-out')));
    await tester.pumpAndSettle();

    expect(find.text('Unsynced changes will be lost'), findsOneWidget);
    expect(find.textContaining('1 change saved on this device has NOT'),
        findsOneWidget);
    await tester.tap(find.byKey(const Key('sign-out-cancel')));
    await tester.pumpAndSettle();

    expect(graph.outbox.total, 1);
    expect(await graph.session.accessToken(), 'tok');
    expect(find.byKey(const Key('queue-add')), findsOneWidget);
  });

  testWidgets('confirmed sign-out wipes outbox, directory, id map, drafts, '
      'tokens, profile and PIN', (tester) async {
    final fake = server();
    final graph = await boot(fake);
    await signIn(graph, userA);
    await graph.appLock.setPin('2468');
    queueOp(graph, 'k1');
    await graph.directory.addLocalPatient(
        localRef: 'loc2', fullName: 'Walk In', gender: 'female');

    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sign-out')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sign-out-confirm')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-submit')), findsOneWidget);
    expect(graph.outbox.total, 0);
    expect(graph.directory.patients, isEmpty);
    expect(graph.directory.localRefs, isEmpty);
    expect(graph.drafts.drafts, isEmpty);
    expect(graph.idMap.serverIdOf('loc1'), isNull);
    expect(graph.store.doc['directory'], isNull);
    expect(graph.store.doc['rx_drafts'], isNull);
    expect(graph.store.doc['idmap'], isNull);
    expect((graph.store.doc['outbox'] as Map)['ops'], isEmpty);
    expect(await graph.session.hasStoredSession(), isFalse);
    expect(await graph.session.profile(), isNull);
    expect(await graph.appLock.hasPin(), isFalse);
    expect(graph.outbox.ownerId, isNull);

    final logout = fake.calls.where((c) => c.route == 'POST /auth/logout');
    expect(logout, hasLength(1), reason: 'server session revoked too');
    expect(logout.single.headers!['Authorization'], 'Bearer tok');
  });

  testWidgets('sign-out with nothing queued asks a plain confirmation',
      (tester) async {
    final graph = await boot(server());
    await signIn(graph, userA);

    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sign-out')));
    await tester.pumpAndSettle();
    expect(find.text('Sign out of this device?'), findsOneWidget);
    await tester.tap(find.byKey(const Key('sign-out-confirm')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('login-submit')), findsOneWidget);
  });

  testWidgets('a dead server session shows a sign-in banner; offline work '
      'is kept and re-login does not wipe it', (tester) async {
    final fake = FakeTransport((c) async {
      if (c.route == 'POST /auth/refresh') {
        return json({'detail': 'Refresh token revoked'}, status: 401);
      }
      return json({'detail': 'Token expired'}, status: 401);
    });
    final graph = await boot(fake);
    await signIn(graph, userA);
    queueOp(graph, 'k1');

    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('session-expired')), findsOneWidget);
    expect(fake.calls.where((c) => c.route == 'POST /auth/refresh'),
        isNotEmpty, reason: 'refresh is tried before giving up');
    expect(graph.outbox.total, 1);

    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('login-notice')), findsOneWidget);
    expect(graph.outbox.total, 1, reason: 're-login keeps the outbox');
    expect(
      tester.widget<TextField>(find.byKey(const Key('login-email'))).controller!.text,
      'a@clinic.test',
    );
  });
}
