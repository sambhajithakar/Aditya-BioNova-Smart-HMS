/// Widget tests: status chips + sync dashboard, per-item retry, conflict
/// resolution screens (use server record / merge by review), the offline
/// guard on finalisation buttons, lazy lists with 2,000 rows, bounded
/// patient cache, QR check-in + GS1 batch scan through a fake scanner, and
/// PDF generation (watermark, server-only signed Rx / receipt).
library;

import 'dart:convert';

import 'package:aditya_bionova_mobile/api/transport.dart';
import 'package:aditya_bionova_mobile/auth/app_lock.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/data/directory.dart';
import 'package:aditya_bionova_mobile/l10n/l10n.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/pdf/documents.dart';
import 'package:aditya_bionova_mobile/pdf/pdf_output.dart';
import 'package:aditya_bionova_mobile/scan/checkin.dart';
import 'package:aditya_bionova_mobile/scan/gs1.dart';
import 'package:aditya_bionova_mobile/scan/scanner.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/screens/patients_tab.dart';
import 'package:aditya_bionova_mobile/screens/sync_tab.dart';
import 'package:aditya_bionova_mobile/screens/sync_widgets.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:aditya_bionova_mobile/sync/idmap.dart';
import 'package:aditya_bionova_mobile/sync/network.dart';
import 'package:aditya_bionova_mobile/sync/outbox.dart';
import 'package:aditya_bionova_mobile/sync/sync_status.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Map<String, dynamic> seed({int patients = 1}) => {
      'directory': {
        'patients': [
          for (var i = 0; i < patients; i++)
            {
              'id': 'p$i',
              'uhid': 'P${i.toString().padLeft(4, '0')}',
              'full_name': 'Synthetic Patient $i',
            },
        ],
        'branches': [
          {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
        ],
        'drugs': [
          {'id': 'd1', 'generic_name': 'Paracetamol'},
        ],
      },
    };

Future<AppGraph> boot(
  ApiTransport t, {
  int patients = 1,
  CodeScanner? scanner,
  PdfOutput? pdf,
  NetworkMonitor? network,
  String role = '',
}) async {
  final tokens = MemoryTokenStore();
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: t,
    tokenStore: tokens,
    store: MemoryLocalStore(seed(patients: patients)),
    appLock: AppLock(tokens, iterations: 1000),
    scanner: scanner,
    pdfOutput: pdf,
    network: network,
  );
  await graph.session.save(
    accessToken: 'tok',
    refreshToken: 'r',
    profile: SessionProfile(
        userId: 'u1',
        organizationId: 'o1',
        organizationName: 'Demo Clinic',
        role: role),
  );
  await graph.restoreSession();
  return graph;
}

Widget host(Widget child) => MaterialApp(home: Scaffold(body: child));

void big(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

Map<String, dynamic> dup409() => {
      'detail': {
        'message': 'Possible duplicate registration.',
        'candidates': [
          {
            'id': 'srv-existing',
            'uhid': 'P0042',
            'full_name': 'Sunita Patil',
            'gender': 'female',
            'date_of_birth': null,
            'phone': '9876500001',
            'matched_on': ['name', 'phone'],
          },
        ],
      },
    };

void main() {
  group('sync dashboard', () {
    testWidgets('status chips with counts, per-item status and Retry now',
        (tester) async {
      big(tester);
      final network =
          NetworkMonitor(const NetworkState(reachability: Reachability.online));
      final graph = await boot(
          FakeTransport((c) async => json({'detail': 'down'}, status: 503)),
          network: network);
      final failing = graph.outbox.enqueue(
          entity: 'invoice',
          method: 'POST',
          path: '/billing/invoices',
          payload: {'patient_id': 'p0'},
          dedupeKey: 'i');
      graph.outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': 'p0', 'branch_id': 'b1'},
          dedupeKey: 'q');
      await tester.pumpWidget(host(SyncTab(graph: graph)));
      await tester.pumpAndSettle();

      expect(find.text('Pending sync: 2'), findsOneWidget);
      expect(find.text('Conflict: 0'), findsOneWidget);

      await tester.tap(find.byKey(const Key('sync-run')));
      await tester.pumpAndSettle();
      expect(failing.status, OpStatus.failed);
      expect(find.text('Server problem — it will be retried automatically.'),
          findsWidgets);

      // Retry now on one item: back to pending, backoff skipped, same key
      final id = failing.id;
      await tester.tap(find.byKey(Key('op-retry-$id')));
      await tester.pump();
      expect(failing.status, OpStatus.pending);
      expect(failing.nextAttemptAt, isNull);
      expect(failing.id, id);
    });

    testWidgets('max attempts → Action required card with Retry now',
        (tester) async {
      big(tester);
      final graph = await boot(FakeTransport.routes({}));
      final op = graph.outbox.enqueue(
          entity: 'invoice',
          method: 'POST',
          path: '/billing/invoices',
          payload: {},
          dedupeKey: 'i');
      for (var i = 0; i < Outbox.maxAttempts; i++) {
        graph.outbox.markFailed(op, 'x');
      }
      op.lastHttpStatus = 500;
      graph.outbox.markDirty();
      await tester.pumpWidget(host(SyncTab(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.text('Action required: 1'), findsOneWidget);
      expect(find.textContaining('automatic retries stopped'), findsWidgets);
      await tester.tap(find.byKey(Key('conflict-retry-${op.id}')));
      await tester.pump();
      expect(op.status, OpStatus.pending);
    });

    testWidgets('the queued list is lazy: 2,000 items build only what is '
        'on screen', (tester) async {
      final graph = await boot(FakeTransport.routes({}));
      graph.outbox.batch(() {
        for (var i = 0; i < 2000; i++) {
          graph.outbox.enqueue(
              entity: 'queue_entry',
              method: 'POST',
              path: '/opd/queue',
              payload: {'patient_id': 'p0', 'branch_id': 'b1', 'i': i},
              dedupeKey: 'q$i');
        }
      });
      final sw = Stopwatch()..start();
      await tester.pumpWidget(host(SyncTab(graph: graph)));
      await tester.pumpAndSettle();
      sw.stop();
      final built = find.byType(ListTile).evaluate().length;
      expect(built, lessThan(60), reason: 'only visible rows are built');
      expect(graph.outbox.total, 2000);
    });
  });

  group('conflict resolution', () {
    Future<AppGraph> dupGraph(WidgetTester tester, FakeTransport fake) async {
      final graph = await boot(fake);
      await graph.directory.addLocalPatient(
          localRef: 'loc1', fullName: 'Sunita Patil', gender: 'female');
      graph.outbox.enqueue(
          entity: 'patient',
          method: 'POST',
          path: '/patients',
          payload: {
            'full_name': 'Sunita Patil',
            'gender': 'female',
            'phone': '9876500001',
            'allergies': 'Penicillin',
          },
          dedupeKey: 'p',
          localRef: 'loc1');
      graph.outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': IdMap.placeholder('loc1'), 'branch_id': 'b1'},
          dedupeKey: 'q');
      await graph.engine.sync();
      return graph;
    }

    testWidgets('duplicate → Review → "Use this record": registration not '
        'sent, the queued visit goes to the existing patient', (tester) async {
      big(tester);
      final fake = FakeTransport((c) async {
        if (c.path == '/patients') return json(dup409(), status: 409);
        return json({'id': 'q1'}, status: 201);
      });
      final graph = await dupGraph(tester, fake);
      final reg = graph.outbox.ops.first;
      expect(reg.conflictReason, ConflictReason.duplicatePatient);
      expect(reg.serverSnapshot, isNotNull,
          reason: 'candidates survive a restart');

      await tester.pumpWidget(host(SyncTab(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.text('Conflict: 1'), findsOneWidget);
      await tester.tap(find.byKey(Key('conflict-review-${reg.id}')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('candidate-srv-existing')), findsOneWidget);
      expect(find.textContaining('Matched on: name, phone'), findsOneWidget);

      await tester.tap(find.byKey(const Key('use-server-srv-existing')));
      await tester.pumpAndSettle();
      expect(find.textContaining('1 queued changes'), findsOneWidget);
      await tester.tap(find.byKey(const Key('confirm-ok')));
      await tester.pumpAndSettle();

      expect(graph.idMap.serverIdOf('loc1'), 'srv-existing');
      expect(graph.outbox.ops.single.entity, 'queue_entry');
      expect(graph.directory.patientById('srv-existing'), isNotNull);
      await graph.engine.sync();
      expect(fake.calls.last.path, '/opd/queue');
      expect(fake.calls.last.body!['patient_id'], 'srv-existing');
      expect(fake.calls.where((c) => c.path == '/patients'), hasLength(1),
          reason: 'the duplicate registration was never re-sent');
    });

    testWidgets('merge by review: nothing pre-ticked; only ticked fields are '
        'PATCHed online', (tester) async {
      big(tester);
      final fake = FakeTransport((c) async {
        switch (c.route) {
          case 'POST /patients':
            return json(dup409(), status: 409);
          case 'GET /patients/srv-existing':
            return json({
              'id': 'srv-existing',
              'uhid': 'P0042',
              'full_name': 'Sunita Patil',
              'gender': 'female',
              'phone': '9876500001',
              'allergies': '',
            });
          case 'PATCH /patients/srv-existing':
            return json({'id': 'srv-existing', 'allergies': c.body!['allergies']});
        }
        return json({'id': 'x'}, status: 201);
      });
      final graph = await dupGraph(tester, fake);
      final reg = graph.outbox.ops.first;
      await tester.pumpWidget(host(SyncTab(graph: graph)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(Key('conflict-review-${reg.id}')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('merge-srv-existing')));
      await tester.pumpAndSettle();

      final box = tester.widget<CheckboxListTile>(
          find.byKey(const Key('merge-field-allergies')));
      expect(box.value, isFalse, reason: 'nothing is pre-selected');
      expect(find.byKey(const Key('merge-field-full_name')), findsNothing,
          reason: 'identical fields are not offered');
      await tester.tap(find.byKey(const Key('merge-field-allergies')));
      await tester.pump();
      await tester.tap(find.text('Copy 1 fields and use the record'));
      await tester.pumpAndSettle();

      final patch = fake.calls.singleWhere((c) => c.method == 'PATCH');
      expect(patch.body, {'allergies': 'Penicillin'});
      expect(graph.idMap.serverIdOf('loc1'), 'srv-existing');
      expect(graph.outbox.ops.single.entity, 'queue_entry');
    });

    testWidgets('version mismatch: shows mine and the server answer; "Send '
        'mine again" needs confirmation and uses a NEW key', (tester) async {
      big(tester);
      final graph = await boot(FakeTransport((c) async =>
          json({'detail': 'Record changed', 'version': 4}, status: 409)));
      final op = graph.outbox.enqueue(
          entity: 'invoice',
          method: 'POST',
          path: '/billing/invoices',
          payload: {'patient_id': 'p0', 'notes': 'mine'},
          dedupeKey: 'i');
      await graph.engine.sync();
      expect(op.conflictReason, ConflictReason.versionMismatch);
      await tester.pumpWidget(host(SyncTab(graph: graph)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(Key('conflict-review-${op.id}')));
      await tester.pumpAndSettle();
      expect(find.textContaining('notes: mine'), findsOneWidget);
      expect(find.textContaining('version: 4'), findsOneWidget);
      await tester.tap(find.byKey(const Key('send-mine-again')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('confirm-ok')));
      await tester.pumpAndSettle();
      final next = graph.outbox.ops.single;
      expect(next.id, isNot(op.id));
      expect(next.status, OpStatus.pending);
    });
  });

  group('offline guard on finalisation', () {
    testWidgets('Rx Sign is disabled offline and says it will not be '
        'finalised offline', (tester) async {
      big(tester);
      final network =
          NetworkMonitor(const NetworkState(reachability: Reachability.offline));
      // offline: every request fails; the stored role (doctor) applies
      final graph = await boot(
          FakeTransport((c) async => throw Exception('offline')),
          network: network,
          role: 'doctor');
      graph.idMap.put('rx1', 'srv-rx');
      await graph.drafts.addDraft(
          localRef: 'rx1',
          patientRef: 'p0',
          patientLabel: 'P0000 Synthetic Patient 0',
          diagnosis: 'Fever',
          items: const []);
      await graph.drafts.adoptSynced(graph.idMap);
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Rx'));
      await tester.pumpAndSettle();
      final sign = tester.widget<TextButton>(find.byKey(const Key('rx-sign-rx1')));
      expect(sign.onPressed, isNull);
      expect(find.byKey(const Key('rx-sign-offline-rx1')), findsOneWidget);
      expect(find.text('Needs connection — will not be finalised offline'),
          findsWidgets);

      network.reportReachable();
      await tester.pumpAndSettle();
      final online = tester.widget<TextButton>(find.byKey(const Key('rx-sign-rx1')));
      expect(online.onPressed, isNotNull);
    });

    testWidgets('OnlineOnlyButton: disabled with the message while offline',
        (tester) async {
      final network =
          NetworkMonitor(const NetworkState(reachability: Reachability.offline));
      var pressed = 0;
      await tester.pumpWidget(host(OnlineOnlyButton(
          network: network, label: 'Confirm payment', onPressed: () => pressed++)));
      expect(find.text('Needs connection — will not be finalised offline'),
          findsOneWidget);
      await tester.tap(find.text('Confirm payment'));
      expect(pressed, 0);
      network.reportReachable();
      await tester.pump();
      await tester.tap(find.text('Confirm payment'));
      expect(pressed, 1);
    });

    testWidgets('consultation note draft works offline; Complete waits for '
        'sync and the network', (tester) async {
      big(tester);
      final graph = await boot(
          FakeTransport((c) async => throw Exception('offline')),
          role: 'doctor');
      graph.network.reportUnreachable();
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Consult'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('consult-complaint')), 'Fever 3 days');
      await tester.tap(find.byKey(const Key('consult-save')));
      await tester.pumpAndSettle();
      final op = graph.outbox.ops.single;
      expect(op.entity, 'encounter');
      expect(op.payload['chief_complaint'], 'Fever 3 days');
      expect(find.text('Saved on device'), findsWidgets);
      // edit before it was ever sent → same op, same key
      await tester.tap(find.byKey(Key('consult-edit-${op.localRef}')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('consult-complaint')), 'Fever 4 days');
      await tester.tap(find.byKey(const Key('consult-save')));
      await tester.pumpAndSettle();
      expect(graph.outbox.ops.single.id, op.id);
      expect(graph.outbox.ops.single.payload['chief_complaint'], 'Fever 4 days');
      expect(find.textContaining('Needs connection'), findsWidgets);
    });
  });

  group('low-cost device', () {
    testWidgets('patients tab with 2,000 cached patients builds lazily and '
        'searches the cache offline', (tester) async {
      final graph = await boot(FakeTransport.routes({}), patients: 2000);
      await tester.pumpWidget(host(PatientsTab(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.byType(ListTile).evaluate().length, lessThan(40));
      await tester.enterText(find.byKey(const Key('patients-search')), 'P1999');
      await tester.pump();
      expect(find.text('P1999 Synthetic Patient 1999'), findsOneWidget);
    });

    test('patient cache is bounded, TTL-expired and clearable (keeps '
        'unsynced registrations)', () async {
      var now = DateTime.utc(2026, 10, 1);
      final store = MemoryLocalStore();
      final dir = DirectoryCache(store, clock: () => now);
      await dir.replacePatients([
        for (var i = 0; i < DirectoryCache.maxCachedPatients + 50; i++)
          {'id': 's$i', 'full_name': 'S $i'},
      ]);
      expect(dir.cachedServerPatients, DirectoryCache.maxCachedPatients);
      await dir.addLocalPatient(localRef: 'loc', fullName: 'Local', gender: 'male');

      now = now.add(DirectoryCache.patientTtl + const Duration(hours: 1));
      final reloaded = DirectoryCache(store, clock: () => now)..load();
      expect(reloaded.cachedServerPatients, 0, reason: 'TTL expired');
      expect(reloaded.patientById('loc'), isNotNull);

      await reloaded.rememberFetched([
        {'id': 'x', 'full_name': 'X'},
      ]);
      expect(await reloaded.clearCachedPatients(), 1);
      expect(reloaded.patients.single['id'], 'loc');
    });

    test('storage usage is reported per section', () async {
      final graph = await boot(FakeTransport.routes({}), patients: 10);
      final usage = graph.storageUsage();
      expect(usage['directory'], greaterThan(100));
    });
  });

  group('scanning', () {
    test('GS1 parser: FNC1 and bracketed forms, plain SKU', () {
      final a = parseGs1(']d201089012345678901721123110BATCH42\u001d21SER9');
      expect(a.gtin, '08901234567890');
      expect(a.expiryText, '2021-12-31'.replaceFirst('2021', '2021'));
      expect(a.expiry, DateTime.utc(2021, 12, 31));
      expect(a.batch, 'BATCH42');
      expect(a.serial, 'SER9');
      final b = parseGs1('(01)08901234567890(17)271100(10)AB-1');
      expect(b.expiry, DateTime.utc(2027, 11, 30), reason: 'DD=00 → month end');
      expect(b.batch, 'AB-1');
      final c = parseGs1('SKU-PARA-500');
      expect(c.isGs1, isFalse);
      expect(c.raw, 'SKU-PARA-500');
    });

    test('check-in token: opaque shapes accepted, others refused', () {
      const t = 'Zx9_aB3-kLm0QwErTy12';
      expect(CheckInToken.parse(t), t);
      expect(CheckInToken.parse('https://clinic.example/c/$t'), t);
      expect(CheckInToken.parse('hms://checkin?t=$t'), t);
      expect(CheckInToken.parse('8901234567890'), isNull);
      expect(CheckInToken.parse('Ramesh Kumar 9876500001'), isNull);
    });

    testWidgets('QR check-in (opd_queue + checkin.manage) queues ONE check-in request '
        'offline through the fake scanner', (tester) async {
      big(tester);
      const token = 'Zx9_aB3-kLm0QwErTy12';
      final scanner = FakeCodeScanner([token, token, 'not a token']);
      final graph = await boot(
        FakeTransport.routes({
          'GET /auth/me': json({
            'role': 'receptionist',
            'features': ['opd_queue', 'mobile_offline'],
            'permissions': [
              'queue.read', 'queue.manage', 'patient.read', 'patient.write',
              'appointment.read', 'appointment.write', 'checkin.manage',
            ],
          }),
        }),
        scanner: scanner,
      );
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('queue-scan-checkin')));
      await tester.pumpAndSettle();
      final op = graph.outbox.ops.single;
      expect(op.path, kCheckInPath);
      expect(op.payload['code'], token);
      expect(op.payload.containsKey('token'), isFalse);
      expect(find.textContaining('Check-in saved on device'), findsOneWidget);

      await tester.tap(find.byKey(const Key('queue-scan-checkin')));
      await tester.pumpAndSettle();
      expect(graph.outbox.total, 1, reason: 'duplicate prevented');
      await tester.tap(find.byKey(const Key('queue-scan-checkin')));
      await tester.pumpAndSettle();
      expect(find.text('This is not a clinic check-in code.'), findsOneWidget);
    });

    testWidgets('no explicit opd_queue + checkin.manage → no scan button',
        (tester) async {
      final graph = await boot(FakeTransport.routes(
          {'GET /auth/me': json({'role': 'receptionist'})}));
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('queue-scan-checkin')), findsNothing);
    });

    testWidgets('opd_queue without checkin.manage → no scan button',
        (tester) async {
      final graph = await boot(FakeTransport.routes({
        'GET /auth/me': json({
          'role': 'receptionist',
          'features': ['opd_queue', 'mobile_offline'],
          'permissions': ['queue.read', 'queue.manage', 'patient.read'],
        }),
      }));
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('queue-scan-checkin')), findsNothing);
    });

    testWidgets('stock count: scanned GS1 batch fills batch/expiry; the '
        'count stays a device draft', (tester) async {
      big(tester);
      final scanner =
          FakeCodeScanner(['(01)08901234567890(17)271231(10)LOT7']);
      final graph = await boot(
        FakeTransport.routes({
          'GET /auth/me': json({'role': 'pharmacist'}),
          'GET /inventory/items': json({
            'items': [
              {'id': 'it1', 'name': 'Paracetamol 500', 'sku': '08901234567890',
                'quantity_on_hand': 40},
            ],
          }),
        }),
        scanner: scanner,
      );
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.text('Stock'), findsWidgets);
      await tester.tap(find.byKey(const Key('stock-scan')));
      await tester.pumpAndSettle();
      expect(find.text('Batch LOT7 · expiry 2027-12-31'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('stock-qty')), '37');
      await tester.tap(find.byKey(const Key('stock-save')));
      await tester.pumpAndSettle();
      final c = graph.stock.counts.single;
      expect(c['itemId'], 'it1');
      expect(c['counted'], 37);
      expect(c['batch'], 'LOT7');
      expect(graph.outbox.total, 0, reason: 'never auto-synced');
    });
  });

  group('PDF', () {
    String text(List<int> bytes) => latin1.decode(bytes, allowInvalid: true);

    test('Rx DRAFT preview carries the watermark on the page', () async {
      final bytes = await buildRxDraftPdf(
        draft: {
          'patientLabel': 'P0001 Synthetic Patient',
          'diagnosis': 'Fever',
          'items': [
            {'drug_name': 'Paracetamol', 'dose': '500 mg', 'frequency': 'TDS',
              'duration_days': 5},
          ],
        },
        clinicName: 'Demo Clinic',
        compress: false,
      );
      expect(bytes, isNotEmpty);
      final s = text(bytes);
      expect(s.startsWith('%PDF'), isTrue);
      // `pdf` writes text word by word: every word of the watermark is on
      // the page, and DRAFT twice (diagonal background + banner).
      for (final word in kDraftWatermark.split(' ')) {
        expect(s, contains('($word)'), reason: word);
      }
      expect('(DRAFT)'.allMatches(s).length, greaterThanOrEqualTo(2));
      expect(s, contains('Paracetamol'));
    });

    test('signed Rx PDF only from a server record the server signed',
        () async {
      await expectLater(
          buildSignedRxPdf(serverRx: {'status': 'draft'}, clinicName: 'C'),
          throwsA(isA<RxSignatureMissing>()));
      final bytes = await buildSignedRxPdf(
        serverRx: {
          'id': 'srv-rx',
          'status': 'signed',
          'signed_at': '2026-10-20T10:00:00Z',
          'version': 1,
          'items': [
            {'drug_name': 'Amoxicillin', 'dose': '250 mg', 'route': 'oral',
              'frequency': 'BD', 'duration_days': 5},
          ],
        },
        clinicName: 'Demo Clinic',
        compress: false,
      );
      final s = text(bytes);
      expect(s, contains('Amoxicillin'));
      expect(s, isNot(contains('(DRAFT)')));
    });

    test('receipt only from a server invoice; text outside Latin-1 is '
        'made safe', () async {
      await expectLater(
          buildReceiptPdf(serverInvoice: {'total': 5}, clinicName: 'C'),
          throwsArgumentError);
      final bytes = await buildReceiptPdf(
        serverInvoice: {
          'invoice_number': 'INV-0001',
          'status': 'paid',
          'subtotal': 200,
          'discount': 0,
          'tax_total': 0,
          'total': 200,
          'amount_paid': 200,
          'items': [
            {'description': 'Consultation', 'quantity': 1, 'unit_price': 200},
          ],
          'payments': [
            {'method': 'upi', 'amount': 200, 'status': 'settled'},
          ],
        },
        clinicName: 'आदित्य Clinic',
        compress: false,
      );
      expect(text(bytes), contains('INV-0001'));
      expect(pdfSafe('आदित्य Clinic'), '?????? Clinic');
    });

    testWidgets('Draft PDF button shares a watermarked preview',
        (tester) async {
      big(tester);
      final out = RecordingPdfOutput();
      final graph = await boot(
          FakeTransport.routes({'GET /auth/me': json({'role': 'doctor'})}),
          pdf: out);
      await graph.drafts.addDraft(
          localRef: 'rx1',
          patientRef: 'p0',
          patientLabel: 'P0000 Synthetic Patient 0',
          diagnosis: 'Fever',
          items: const [
            {'drug_name': 'Paracetamol', 'dose': '500 mg', 'frequency': 'TDS',
              'duration_days': 5},
          ]);
      graph.outbox.enqueue(
          entity: 'prescription',
          method: 'POST',
          path: '/prescriptions',
          payload: {},
          dedupeKey: 'rx',
          localRef: 'rx1');
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Rx'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('rx-pdf-rx1')));
      await tester.tap(find.byKey(const Key('rx-pdf-rx1')));
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 300)));
      await tester.pumpAndSettle();
      expect(out.shared.single.$1, 'rx-draft.pdf');
      expect(out.shared.single.$2, isNotEmpty);
    });
  });

  test('status labels exist in all three languages for every status', () {
    for (final code in ['en', 'mr', 'hi']) {
      final l = lookupAppLocalizations(Locale(code));
      final labels = {for (final s in SyncStatus.values) syncStatusLabel(l, s)};
      expect(labels, hasLength(SyncStatus.values.length), reason: code);
    }
  });
}
