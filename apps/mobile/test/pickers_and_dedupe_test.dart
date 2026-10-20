/// H24 / D6: a directory refresh keeps unsynced offline registrations in
/// every patient picker ("pending sync") and no raw device id is ever put
/// in a payload. D10/D11/D12: dedupe keys cover price/qty and the full
/// regimen, on the LOCAL day. Rx items carry optional `dispense_quantity`.
library;

import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/data/directory.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:aditya_bionova_mobile/sync/idmap.dart';
import 'package:aditya_bionova_mobile/util/dates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Map<String, dynamic> seed() => {
      'directory': {
        'patients': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Aarti Patil'},
        ],
        'branches': [
          {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
        ],
        'drugs': [
          {'id': 'd1', 'generic_name': 'Amoxicillin'},
        ],
      },
    };

FakeTransport server({String role = 'doctor'}) => FakeTransport.routes({
      'GET /auth/me': json({'role': role}),
      // the server does not know the offline registration yet
      'GET /patients': json({
        'items': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Aarti Patil'},
          {'id': 'p2', 'uhid': 'P0002', 'full_name': 'Bhavna Rao'},
        ],
        'total': 2,
      }),
      'GET /branches': json([
        {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
      ]),
    });

Future<AppGraph> boot(FakeTransport fake) async {
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: fake,
    tokenStore: MemoryTokenStore(),
    store: MemoryLocalStore(seed()),
  );
  await graph.session.save(accessToken: 'tok', refreshToken: 'r');
  return graph;
}

Future<void> pickPatient(WidgetTester tester, String picker, String label) async {
  await tester.tap(find.byKey(Key(picker)));
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

void main() {
  group('directory merge (H24)', () {
    test('refresh keeps unsynced local patients, drops them once the server '
        'lists the synced record', () async {
      final dir = DirectoryCache(MemoryLocalStore());
      final ids = IdMap();
      await dir.addLocalPatient(
          localRef: 'loc1', fullName: 'Sunita', gender: 'female');

      await dir.replacePatients([
        {'id': 'p1', 'full_name': 'Aarti'},
      ], idMap: ids);
      expect(dir.patients.map((p) => p['id']), ['loc1', 'p1']);
      expect(dir.refFor('loc1', ids), r'$ref:loc1');

      ids.put('loc1', 'srv9');
      expect(dir.refFor('loc1', ids), 'srv9');
      await dir.replacePatients([
        {'id': 'p1', 'full_name': 'Aarti'},
        {'id': 'srv9', 'full_name': 'Sunita'},
      ], idMap: ids);
      expect(dir.patients.map((p) => p['id']), ['p1', 'srv9']);
      expect(dir.resolveSelection('loc1', ids), 'srv9',
          reason: 'a selected local patient follows to the server row');
    });

    test('a device id is never sent raw, even after its entry is gone',
        () async {
      final store = MemoryLocalStore();
      final dir = DirectoryCache(store);
      await dir.addLocalPatient(
          localRef: 'loc1', fullName: 'Sunita', gender: 'female');
      await dir.removeLocalPatient('loc1');
      expect(dir.patientById('loc1'), isNull);
      expect(dir.refFor('loc1', IdMap()), r'$ref:loc1');

      // and the knowledge survives a restart
      final reloaded = DirectoryCache(store)..load();
      expect(reloaded.refFor('loc1', IdMap()), r'$ref:loc1');
      expect(reloaded.refFor('p1', IdMap()), 'p1');
      expect(reloaded.resolveSelection('loc1', IdMap()), isNull,
          reason: 'a vanished selection is never swapped for someone else');
    });
  });

  testWidgets('offline registration stays in queue / billing / Rx pickers '
      'after a refresh, and is sent as \$ref', (tester) async {
    tester.view.physicalSize = const Size(1080, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final graph = await boot(server());
    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle(); // queue tab auto-refreshes on open

    await tester.tap(find.text('Register'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('register-name')), 'Sunita Patil');
    await tester.enterText(find.byKey(const Key('register-phone')), '9876500001');
    await tester.tap(find.byKey(const Key('register-add')));
    await tester.pump();
    final localRef = graph.outbox.ops.single.localRef!;

    // queue: refresh from the server (which does not list her yet)
    await tester.tap(find.text('Queue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Refresh'));
    await tester.pumpAndSettle();
    expect(graph.directory.patientById(localRef), isNotNull);
    expect(graph.directory.patientById('p2'), isNotNull);

    await pickPatient(tester, 'queue-patient', 'Sunita Patil (pending sync)');
    await tester.tap(find.byKey(const Key('queue-add')));
    await tester.pump();
    final queueOp = graph.outbox.ops.last;
    expect(queueOp.payload['patient_id'], IdMap.placeholder(localRef));

    // billing picker lists her too
    await tester.tap(find.text('Billing'));
    await tester.pumpAndSettle();
    await pickPatient(tester, 'billing-patient', 'Sunita Patil (pending sync)');
    await tester.enterText(
        find.byKey(const Key('billing-description')), 'Consultation fee');
    await tester.enterText(find.byKey(const Key('billing-price')), '200');
    await tester.tap(find.byKey(const Key('billing-add')));
    await tester.pump();
    expect(graph.outbox.ops.last.entity, 'invoice');
    expect(graph.outbox.ops.last.payload['patient_id'],
        IdMap.placeholder(localRef));

    // Rx picker lists her too
    await tester.tap(find.text('Rx'));
    await tester.pumpAndSettle();
    await pickPatient(tester, 'rx-patient', 'Sunita Patil (pending sync)');
    await tester.enterText(find.byKey(const Key('rx-dose')), '500 mg');
    await tester.enterText(find.byKey(const Key('rx-frequency')), 'BD');
    await tester.tap(find.byKey(const Key('rx-add-item')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('rx-save')));
    await tester.pump();
    expect(graph.outbox.ops.last.entity, 'prescription');
    expect(graph.outbox.ops.last.payload['patient_id'],
        IdMap.placeholder(localRef));

    // nothing in the outbox carries the raw device id as patient_id
    for (final op in graph.outbox.ops) {
      expect(op.payload['patient_id'], isNot(localRef));
    }
  });

  testWidgets('invoice dedupe covers price and quantity (D10)',
      (tester) async {
    final graph = await boot(server(role: 'receptionist'));
    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Billing'));
    await tester.pumpAndSettle();

    Future<void> line(String price, {String qty = '1'}) async {
      await tester.enterText(
          find.byKey(const Key('billing-description')), 'Dressing');
      await tester.enterText(find.byKey(const Key('billing-quantity')), qty);
      await tester.enterText(find.byKey(const Key('billing-price')), price);
      await tester.tap(find.byKey(const Key('billing-add')));
      await tester.pump();
    }

    await line('100');
    await line('150'); // same description, different price → a real line
    await line('100', qty: '2'); // different quantity → a real line
    expect(graph.outbox.total, 3);
    await line('100'); // exact double-tap → prevented
    expect(graph.outbox.total, 3);
    expect(find.textContaining('duplicate prevented'), findsOneWidget);
    expect(graph.outbox.ops.first.dedupeKey, endsWith(localDay()));
  });

  testWidgets('Rx: corrected dose is a new draft; dispense_quantity is sent '
      'when given and validated (D11, M7 contract)', (tester) async {
    tester.view.physicalSize = const Size(1080, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final graph = await boot(server());
    await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Rx'));
    await tester.pumpAndSettle();

    Future<void> draft(String dose, {String qty = ''}) async {
      await tester.enterText(find.byKey(const Key('rx-dose')), dose);
      await tester.enterText(find.byKey(const Key('rx-frequency')), 'BD');
      await tester.enterText(find.byKey(const Key('rx-dispense-qty')), qty);
      await tester.tap(find.byKey(const Key('rx-add-item')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('rx-save')));
      await tester.pump();
    }

    await draft('250 mg', qty: '10');
    final first = graph.outbox.ops.single;
    expect(first.payload['items'][0]['dispense_quantity'], 10);

    await draft('500 mg'); // dose corrected → NOT swallowed as a duplicate
    expect(graph.outbox.total, 2);
    expect(
      (graph.outbox.ops.last.payload['items'][0] as Map)
          .containsKey('dispense_quantity'),
      isFalse,
      reason: 'blank quantity is omitted, not sent as null',
    );

    await draft('500 mg'); // identical regimen again → prevented
    expect(graph.outbox.total, 2);
    expect(find.textContaining('duplicate prevented'), findsOneWidget);

    // invalid quantity is refused before anything is queued
    await tester.enterText(find.byKey(const Key('rx-dose')), '1 g');
    await tester.enterText(find.byKey(const Key('rx-frequency')), 'OD');
    await tester.enterText(find.byKey(const Key('rx-dispense-qty')), '0');
    await tester.tap(find.byKey(const Key('rx-add-item')));
    await tester.pump();
    expect(find.textContaining('1–10000'), findsOneWidget);
  });

  test('localDay uses the device-local calendar day (D12)', () {
    // 00:30 local is still "today" locally, whatever UTC says
    final early = DateTime(2026, 10, 20, 0, 30);
    expect(localDay(early), '2026-10-20');
    final utc = DateTime.utc(2026, 10, 19, 20, 0);
    final local = utc.toLocal();
    expect(localDay(utc),
        '${local.year}-${local.month.toString().padLeft(2, '0')}-'
        '${local.day.toString().padLeft(2, '0')}');
  });
}
