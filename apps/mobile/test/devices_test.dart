// M8.2c: simulated devices, pairing, capture from a consultation (patient
// context first), offline queueing, and clinician review on Android.
// SYNTHETIC readings only; no real Bluetooth.
import 'dart:convert';

import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/devices/device_book.dart';
import 'package:aditya_bionova_mobile/devices/gatt.dart';
import 'package:aditya_bionova_mobile/devices/simulator.dart';
import 'package:aditya_bionova_mobile/devices/transport.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/device_review_screen.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:aditya_bionova_mobile/sync/idmap.dart';
import 'package:aditya_bionova_mobile/sync/outbox.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

const _perms = [
  'encounter.read', 'encounter.write', 'patient.read',
  'device.read', 'device.capture', 'device.review',
];

Map<String, dynamic> _me({List<String> perms = _perms, bool feature = true}) => {
      'role': 'doctor',
      'features': ['consultation', 'mobile_offline', if (feature) 'medical_devices'],
      'permissions': perms,
    };

final _bpDevice = {
  'id': 'dev-bp',
  'kind': DeviceKinds.bp,
  'label': 'OPD 1 BP (sim)',
  'is_simulator': true,
  'status': 'active',
};

MemoryLocalStore _store({bool paired = true, String? serverId = 'enc-1'}) =>
    MemoryLocalStore({
      'directory': {
        'patients': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Aarti Patil'},
        ],
        'branches': [
          {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
        ],
      },
      'consult_drafts': {
        'drafts': [
          {
            'localRef': 'L1',
            'serverId': serverId,
            'patientLabel': 'Aarti Patil (P0001)',
            'complaint': 'Headache',
          },
        ],
      },
      'devices': {
        'devices': [_bpDevice],
        'pairings': paired
            ? {
                'dev-bp': {'address': 'SIM-0000B001', 'pairedAt': 'x'},
              }
            : <String, dynamic>{},
      },
    });

Future<AppGraph> _boot(FakeTransport t, MemoryLocalStore store) async {
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: t,
    tokenStore: MemoryTokenStore(),
    store: store,
    deviceTransport: SimulatedDeviceTransport(),
  );
  await graph.session.save(accessToken: 'tok', refreshToken: 'r');
  return graph;
}

Future<void> _pump(WidgetTester tester, AppGraph graph) async {
  tester.view.physicalSize = const Size(1080, 3200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
      HmsMaterialApp(settings: graph.settings, home: HomeScreen(graph: graph)));
  await tester.pumpAndSettle();
}

Future<void> _openConsult(WidgetTester tester) async {
  await tester.tap(find.text('Consult').last);
  await tester.pumpAndSettle();
}

void main() {
  group('simulator', () {
    final sim = SimulatedDeviceTransport();

    test('every scenario parses; unusable ones are refused by policy', () async {
      for (final s in simScenarios) {
        final ad = simulatedDevices.firstWhere((d) => d.kind == s.kind);
        final r = parseMeasurement(
            await sim.measure(ad.address, kind: s.kind, scenario: s.key));
        final refused = s.key == 'spo2_from_storage' || s.key == 'spo2_invalid';
        expect(r.refusal != null, refused, reason: s.key);
      }
    });

    test('values and flags come through exactly', () async {
      final bp = parseMeasurement(await sim.measure('SIM-0000B001',
          kind: DeviceKinds.bp, scenario: 'bp_high_irregular'));
      expect(bp.reading.values,
          {'systolic': 168, 'diastolic': 102, 'mean_arterial': 124, 'pulse': 96});
      expect(bp.reading.flags, ['body_movement', 'irregular_pulse']);
      final clock = parseMeasurement(await sim.measure('SIM-0000B001',
          kind: DeviceKinds.bp, scenario: 'bp_no_clock'));
      expect(clock.reading.flags, ['device_clock_not_set']);
      final low = parseMeasurement(await sim.measure('SIM-0000A001',
          kind: DeviceKinds.oximeter, scenario: 'spo2_low'));
      expect(low.reading.values, {'spo2': 86, 'pulse': 112});
      expect(() => sim.measure('SIM-0000A001', kind: DeviceKinds.bp),
          throwsA(isA<DeviceException>()));
    });
  });

  group('queueing and access', () {
    test('queueReading sends the RAW payload with the phone parse', () async {
      final outbox = Outbox();
      final m = await SimulatedDeviceTransport()
          .measure('SIM-0000B001', kind: DeviceKinds.bp);
      final op = queueReading(outbox,
          result: parseMeasurement(m),
          device: _bpDevice,
          address: 'SIM-0000B001',
          encounterRef: IdMap.placeholder('L1'),
          appVersion: 't',
          captureId: '11111111-1111-4111-8111-111111111111');
      expect(op.path, '/device-readings');
      expect(op.payload['raw_hex'], bytesToHex(m.bytes));
      expect(op.payload['source'], 'simulator');
      expect(op.payload['encounter_id'], r'$ref:L1');
      expect((op.payload['client_parsed'] as Map)['values'],
          {'systolic': 122, 'diastolic': 78, 'mean_arterial': 93, 'pulse': 72});
      // the same capture is queued once
      final again = queueReading(outbox,
          result: parseMeasurement(m),
          device: _bpDevice,
          address: 'SIM-0000B001',
          encounterRef: 'x',
          appVersion: 't',
          captureId: '11111111-1111-4111-8111-111111111111');
      expect(identical(op, again), isTrue);
      final refused = parseMeasurement(await SimulatedDeviceTransport().measure(
          'SIM-0000A001',
          kind: DeviceKinds.oximeter,
          scenario: 'spo2_invalid'));
      expect(
          () => queueReading(outbox,
              result: refused,
              device: _bpDevice,
              address: 'a',
              encounterRef: 'e',
              appVersion: 't'),
          throwsStateError);
    });

    test('device access needs the explicit feature; review needs encounter.write',
        () {
      expect(
          DeviceAccess.from(featureReported: false, permissions: _perms.toSet()).any,
          isFalse);
      expect(DeviceAccess.from(featureReported: true, permissions: null).any, isFalse);
      final noWrite = DeviceAccess.from(
          featureReported: true, permissions: {'device.review', 'device.capture'});
      expect((noWrite.capture, noWrite.review), (true, false));
    });
  });

  testWidgets('capture from a consultation: patient shown, saved for review, '
      'nothing written to the record', (tester) async {
    final t = FakeTransport.routes({'GET /auth/me': json(_me())});
    final graph = await _boot(t, _store());
    await _pump(tester, graph);
    await _openConsult(tester);
    await tester.tap(find.byKey(const Key('consult-measure-L1')));
    await tester.pumpAndSettle();
    expect(find.text('Measuring for: Aarti Patil (P0001)'), findsOneWidget);
    expect(find.byKey(const Key('simulated-badge')), findsWidgets);
    await tester.tap(find.byKey(const Key('measure-start')));
    await tester.pumpAndSettle();
    expect(find.text('BP 122/78 mmHg'), findsOneWidget);
    expect(find.textContaining('a clinician must accept'), findsOneWidget);
    await tester.tap(find.byKey(const Key('measure-save')));
    await tester.pumpAndSettle();
    final op = graph.outbox.ops.single;
    expect((op.path, op.payload['encounter_id'], op.payload['device_id']),
        ('/device-readings', 'enc-1', 'dev-bp'));
    expect(t.calls.where((c) => c.path.contains('vitals')), isEmpty);
  });

  testWidgets('a reading the device marks unusable cannot be saved', (tester) async {
    final graph = await _boot(
        FakeTransport.routes({'GET /auth/me': json(_me())}),
        MemoryLocalStore(jsonDecode(jsonEncode(_store().doc)) as Map<String, dynamic>
          ..['devices'] = {
            'devices': [
              {..._bpDevice, 'id': 'dev-ox', 'kind': DeviceKinds.oximeter},
            ],
            'pairings': {
              'dev-ox': {'address': 'SIM-0000A001', 'pairedAt': 'x'},
            },
          }));
    await _pump(tester, graph);
    await _openConsult(tester);
    await tester.tap(find.byKey(const Key('consult-measure-L1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pulse oximeter'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('measure-scenario')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('from device memory').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('measure-start')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('measure-refused')), findsOneWidget);
    expect(find.byKey(const Key('measure-save')), findsNothing);
    expect(graph.outbox.ops, isEmpty);
  });

  testWidgets('no device buttons when the server does not report the feature',
      (tester) async {
    final graph = await _boot(
        FakeTransport.routes({'GET /auth/me': json(_me(feature: false))}), _store());
    await _pump(tester, graph);
    await _openConsult(tester);
    expect(find.byKey(const Key('consult-measure-L1')), findsNothing);
    expect(find.byKey(const Key('consult-review-L1')), findsNothing);
  });

  testWidgets('register a simulated device and pair; a wrong device is refused',
      (tester) async {
    final calls = <String, Map<String, dynamic>?>{};
    final t = FakeTransport((c) async {
      calls[c.route] = c.body;
      switch (c.route) {
        case 'GET /auth/me':
          return json(_me(perms: [..._perms, 'device.manage']));
        case 'GET /devices':
          return json([_bpDevice]);
        case 'POST /devices':
          return json({...c.body!, 'id': 'dev-new', 'status': 'active'},
              status: 201);
        case 'POST /devices/dev-bp/verify-address':
          return json({
            'match': c.body!['ble_address'] == 'SIM-0000B002',
            'active': true,
          });
      }
      return json({'detail': 'no stub'}, status: 404);
    });
    final graph = await _boot(t, _store(paired: false));
    await _pump(tester, graph);
    await tester.tap(find.byKey(const Key('settings-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('menu-devices')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('devices-not-validated')), findsOneWidget);
    // pairing the registered BP monitor with the wrong simulated device
    await tester.tap(find.byKey(const Key('device-pair-dev-bp')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('found-SIM-0000A001')), findsNothing,
        reason: 'only devices of the same kind are offered');
    await tester.tap(find.byKey(const Key('found-SIM-0000B001')));
    await tester.pumpAndSettle();
    expect(find.text('That is not the registered device.'), findsOneWidget);
    expect(graph.devices.isPaired('dev-bp'), isFalse);
    await tester.tap(find.byKey(const Key('device-pair-dev-bp')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('found-SIM-0000B002')));
    await tester.pumpAndSettle();
    expect(graph.devices.addressOf('dev-bp'), 'SIM-0000B002');
    // registering a new simulated oximeter (device.manage)
    await tester.tap(find.byKey(const Key('devices-register')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('found-SIM-0000A001')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('device-label')), 'Ward oximeter');
    await tester.tap(find.byKey(const Key('device-label-ok')));
    await tester.pumpAndSettle();
    final body = calls['POST /devices']!;
    expect((body['kind'], body['ble_address'], body['is_simulator'], body['label']),
        (DeviceKinds.oximeter, 'SIM-0000A001', true, 'Ward oximeter'));
    expect(graph.devices.addressOf('dev-new'), 'SIM-0000A001');
  });

  testWidgets('review on Android: accept needs the patient confirmation; '
      'reject needs a reason', (tester) async {
    final posted = <String, Map<String, dynamic>?>{};
    var pending = [
      {
        'id': 'r1', 'device_label': 'OPD 1 BP (sim)', 'device_is_simulator': true,
        'kind': 'blood_pressure', 'clock_skew': true,
        'values': {'systolic': 133, 'diastolic': 85, 'pulse': 72},
        'flags': ['irregular_pulse'],
      },
      {
        'id': 'r2', 'device_label': 'OPD 1 BP (sim)', 'device_is_simulator': true,
        'kind': 'blood_pressure', 'clock_skew': false,
        'values': {'systolic': 120, 'diastolic': 80},
        'flags': <String>[],
      },
    ];
    final t = FakeTransport((c) async {
      if (c.route == 'GET /device-readings') return json(pending);
      if (c.method == 'POST') {
        posted[c.path] = c.body;
        final id = c.path.split('/')[2];
        pending = [for (final r in pending) if (r['id'] != id) r];
        return json({'id': id, 'status': 'done'});
      }
      return json(_me());
    });
    final graph = await _boot(t, _store());
    tester.view.physicalSize = const Size(1080, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(HmsMaterialApp(
        settings: graph.settings,
        home: DeviceReviewScreen(
            graph: graph, encounterId: 'enc-1', patientLabel: 'Aarti Patil')));
    await tester.pumpAndSettle();
    expect(find.text('Device notes: irregular_pulse'), findsOneWidget);
    expect(find.text("The device clock differs from the phone's."), findsOneWidget);
    await tester.tap(find.byKey(const Key('review-accept-r1')));
    await tester.pumpAndSettle();
    // cannot accept without ticking the confirmation
    expect(tester.widget<FilledButton>(find.byKey(const Key('review-accept-ok')))
        .onPressed, isNull);
    await tester.tap(find.byKey(const Key('review-confirm-patient')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('review-accept-ok')));
    await tester.pumpAndSettle();
    expect(posted['/device-readings/r1/accept'],
        {'surface': 'android', 'confirm_patient': true});
    await tester.tap(find.byKey(const Key('review-reject-r2')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('review-reason')), 'ok');
    await tester.tap(find.byKey(const Key('review-reject-ok')));
    await tester.pumpAndSettle();
    expect(posted.containsKey('/device-readings/r2/reject'), isFalse,
        reason: 'reason too short');
    await tester.enterText(
        find.byKey(const Key('review-reason')), 'cuff on the wrong arm');
    await tester.tap(find.byKey(const Key('review-reject-ok')));
    await tester.pumpAndSettle();
    expect(posted['/device-readings/r2/reject'],
        {'surface': 'android', 'reason': 'cuff on the wrong arm'});
    expect(find.byKey(const Key('review-none')), findsOneWidget);
  });

  test('offline: a reading for an unsynced consultation waits for it, then '
      'is sent with the server encounter id', () async {
    final sent = <String>[];
    final t = FakeTransport((c) async {
      sent.add(c.route);
      if (c.route == 'POST /encounters') {
        return json({'id': 'enc-srv'}, status: 201);
      }
      if (c.route == 'POST /device-readings') {
        expect(c.body!['encounter_id'], 'enc-srv');
        return json({'id': 'r1', 'status': 'pending_review'}, status: 201);
      }
      return json(_me());
    });
    final graph = await _boot(t, _store(serverId: null));
    final m = await graph.deviceTransport.measure('SIM-0000B001', kind: DeviceKinds.bp);
    // the reading is captured first …
    queueReading(graph.outbox,
        result: parseMeasurement(m),
        device: _bpDevice,
        address: 'SIM-0000B001',
        encounterRef: IdMap.placeholder('L1'),
        appVersion: 't');
    // … its consultation draft is queued afterwards (same local ref)
    graph.outbox.enqueue(
        entity: 'encounter',
        method: 'POST',
        path: '/encounters',
        payload: {'patient_id': 'p1', 'branch_id': 'b1', 'chief_complaint': 'x'},
        dedupeKey: 'encounter:p1:test',
        localRef: 'L1');
    final result = await graph.engine.sync();
    expect(result.conflicts, isEmpty);
    expect(sent.where((r) => r.startsWith('POST')).toList(),
        ['POST /encounters', 'POST /device-readings']);
    expect(graph.outbox.ops, isEmpty);
  });
}
