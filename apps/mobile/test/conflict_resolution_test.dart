/// D8: "Keep local" on a duplicate-patient 409 re-sends with
/// allow_duplicates=true after explicit confirmation (new idempotency key —
/// the first request created nothing). D9: discarding a registration also
/// discards its dependants, after saying so. D17: a discarded Rx draft never
/// reads "Synced". D18: op ids are v4 UUIDs from a secure RNG.
library;

import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:aditya_bionova_mobile/sync/idmap.dart';
import 'package:aditya_bionova_mobile/sync/outbox.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Map<String, dynamic> duplicate409() => {
      'detail': {
        'message': 'Possible duplicate registration. Confirm to create anyway '
            '(allow_duplicates=true) or open the existing record.',
        'candidates': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Sunita Patil'},
        ],
      },
    };

Future<AppGraph> boot(FakeTransport fake) async {
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: fake,
    tokenStore: MemoryTokenStore(),
    store: MemoryLocalStore({
      'directory': {
        'patients': <dynamic>[],
        'branches': [
          {'id': 'b1', 'name': 'Main'},
        ],
        'drugs': <dynamic>[],
      },
    }),
  );
  await graph.session.save(accessToken: 'tok', refreshToken: 'r');
  return graph;
}

/// Registration + a queue entry + an Rx draft for the same offline patient.
Future<(OutboxOp, String)> seedOfflineWork(AppGraph graph) async {
  final localRef = Outbox.newId();
  final reg = graph.outbox.enqueue(
    entity: 'patient',
    method: 'POST',
    path: '/patients',
    payload: {'full_name': 'Sunita Patil', 'gender': 'female'},
    dedupeKey: 'patient:sunita',
    localRef: localRef,
  );
  await graph.directory.addLocalPatient(
      localRef: localRef, fullName: 'Sunita Patil', gender: 'female');
  graph.outbox.enqueue(
    entity: 'queue_entry',
    method: 'POST',
    path: '/opd/queue',
    payload: {'patient_id': IdMap.placeholder(localRef), 'branch_id': 'b1'},
    dedupeKey: 'queue:sunita',
  );
  final rxRef = Outbox.newId();
  graph.outbox.enqueue(
    entity: 'prescription',
    method: 'POST',
    path: '/prescriptions',
    payload: {
      'patient_id': IdMap.placeholder(localRef),
      'items': <dynamic>[],
    },
    dedupeKey: 'rx:sunita',
    localRef: rxRef,
  );
  await graph.drafts.addDraft(
    localRef: rxRef,
    patientRef: IdMap.placeholder(localRef),
    patientLabel: 'Sunita Patil',
    diagnosis: 'Fever',
    items: const [],
  );
  return (reg, rxRef);
}

Future<void> openSyncAndRun(WidgetTester tester) async {
  await tester.tap(find.text('Sync'));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('sync-run')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('duplicate 409 → confirmed "register anyway" re-sends with '
      'allow_duplicates and a new idempotency key (D8)', (tester) async {
    tester.view.physicalSize = const Size(1080, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final fake = FakeTransport((c) async {
      switch (c.route) {
        case 'GET /auth/me':
          return json({'role': 'receptionist'});
        case 'POST /patients':
          if (c.body!['allow_duplicates'] == true) {
            return json({'id': 'srv-new', 'uhid': 'P0099'}, status: 201);
          }
          return json(duplicate409(), status: 409);
        case 'POST /opd/queue':
        case 'POST /prescriptions':
          return json({'id': 'x'}, status: 201);
      }
      return json({'detail': 'offline'}, status: 503);
    });
    final graph = await boot(fake);
    final (reg, _) = await seedOfflineWork(graph);

    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();
    await openSyncAndRun(tester);

    expect(reg.status, OpStatus.conflicted);
    expect(reg.conflictReason, ConflictReason.duplicatePatient);
    expect(find.textContaining('waiting 2'), findsOneWidget,
        reason: 'dependants wait for the registration');

    await tester.tap(find.byKey(Key('conflict-register-anyway-${reg.id}')));
    await tester.pumpAndSettle();
    expect(find.text('Register as a NEW patient?'), findsOneWidget);
    await tester.tap(find.byKey(const Key('confirm-ok')));
    await tester.pumpAndSettle();

    final reissued = graph.outbox.ops.first;
    expect(reissued.id, isNot(reg.id));
    expect(reissued.localRef, reg.localRef);
    expect(reissued.payload['allow_duplicates'], isTrue);
    expect(reissued.status, OpStatus.pending);

    await tester.tap(find.byKey(const Key('sync-run')));
    await tester.pumpAndSettle();
    expect(graph.outbox.total, 0);
    final pushes =
        fake.calls.where((c) => c.route == 'POST /patients').toList();
    expect(pushes, hasLength(2));
    expect(pushes.last.headers!['Idempotency-Key'], reissued.id);
    final queue = fake.calls.firstWhere((c) => c.route == 'POST /opd/queue');
    expect(queue.body!['patient_id'], 'srv-new');
  });

  testWidgets('discarding a registration discards its dependants after a '
      'clear warning; the Rx draft shows "Discarded" (D9, D17)',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final fake = FakeTransport((c) async {
      switch (c.route) {
        case 'GET /auth/me':
          return json({'role': 'doctor'});
        case 'POST /patients':
          return json(duplicate409(), status: 409);
      }
      return json({'detail': 'offline'}, status: 503);
    });
    final graph = await boot(fake);
    final (reg, rxRef) = await seedOfflineWork(graph);

    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();
    await openSyncAndRun(tester);

    await tester.tap(find.byKey(Key('conflict-discard-${reg.id}')));
    await tester.pumpAndSettle();
    expect(find.text('Discard patient and 2 more?'), findsOneWidget);
    expect(find.textContaining('queue entry, prescription'), findsOneWidget);

    // cancel first: nothing changes
    await tester.tap(find.byKey(const Key('confirm-cancel')));
    await tester.pumpAndSettle();
    expect(graph.outbox.total, 3);

    await tester.tap(find.byKey(Key('conflict-discard-${reg.id}')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('confirm-ok')));
    await tester.pumpAndSettle();

    expect(graph.outbox.total, 0, reason: 'no orphan waits forever');
    expect(find.textContaining('and 2 dependent changes'), findsOneWidget);
    expect(graph.directory.patientById(reg.localRef!), isNull);
    expect(graph.drafts.drafts.single['discarded'], isTrue);

    await tester.tap(find.text('Rx'));
    await tester.pumpAndSettle();
    expect(find.text('Discarded — not sent'), findsOneWidget);
    expect(find.text('Synced'), findsNothing);
    expect(find.byKey(Key('rx-sign-$rxRef')), findsNothing);
  });

  test('dependentsOf is transitive and resolveConflict(discard) removes '
      'them', () {
    final outbox = Outbox();
    final reg = outbox.enqueue(
      entity: 'patient',
      method: 'POST',
      path: '/patients',
      payload: const {},
      dedupeKey: 'p',
      localRef: 'loc-p',
    )..status = OpStatus.conflicted;
    final rx = outbox.enqueue(
      entity: 'prescription',
      method: 'POST',
      path: '/prescriptions',
      payload: {'patient_id': IdMap.placeholder('loc-p')},
      dedupeKey: 'rx',
      localRef: 'loc-rx',
    );
    final sign = outbox.enqueue(
      entity: 'prescription_sign',
      method: 'POST',
      path: '/x',
      payload: {'prescription_id': IdMap.placeholder('loc-rx')},
      dedupeKey: 'sign',
    );
    outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': 'other'},
      dedupeKey: 'unrelated',
    );

    expect(outbox.dependentsOf(reg), [rx, sign]);
    outbox.resolveConflict(reg, keepLocal: false);
    expect(outbox.ops.map((o) => o.dedupeKey), ['unrelated']);
  });

  test('op ids are RFC 4122 v4 UUIDs (D18)', () {
    final re = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$');
    for (var i = 0; i < 200; i++) {
      expect(re.hasMatch(Outbox.newId()), isTrue);
    }
  });
}
