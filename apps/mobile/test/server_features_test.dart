/// Server feature awareness: `GET /auth/me` reports `features` and
/// `edition`; a tab whose feature is absent is hidden. A missing field
/// means "all enabled" (older servers). All through the fake transport.
library;

import 'package:aditya_bionova_mobile/auth/features.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

const allKeys = [
  'opd_queue',
  'consultation',
  'billing',
  'pharmacy',
  'mobile_offline',
];

MemoryLocalStore seededStore() => MemoryLocalStore({
      'directory': {
        'patients': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Aarti Patil'},
        ],
        'branches': [
          {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
        ],
        'drugs': [
          {'id': 'd1', 'generic_name': 'Paracetamol'},
        ],
      },
    });

Future<AppGraph> bootGraph(
  FakeTransport transport, {
  MemoryTokenStore? tokens,
  MemoryLocalStore? store,
}) async {
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: transport,
    tokenStore: tokens ?? MemoryTokenStore(),
    store: store ?? seededStore(),
  );
  if (await graph.session.profile() == null) {
    await graph.session.save(
      accessToken: 'tok',
      refreshToken: 'r',
      profile: const SessionProfile(userId: 'u1', role: 'doctor'),
    );
  }
  return graph;
}

FakeTransport meSays(Map<String, dynamic> me) =>
    FakeTransport.routes({'GET /auth/me': json(me)});

Future<void> pumpHome(WidgetTester tester, AppGraph graph) async {
  tester.view.physicalSize = const Size(1080, 2600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(HmsMaterialApp(
    settings: graph.settings,
    home: HomeScreen(graph: graph),
  ));
  await tester.pumpAndSettle();
}

List<String> navLabels(WidgetTester tester) => tester
    .widgetList<NavigationDestination>(find.byType(NavigationDestination))
    .map((d) => d.label)
    .toList();

void main() {
  group('ServerFeatures.fromJson', () {
    test('missing field = everything enabled (backward compatible)', () {
      final f = ServerFeatures.fromJson({'role': 'doctor'});
      expect(f.keys, isNull);
      for (final key in allKeys) {
        expect(f.has(key), isTrue, reason: key);
      }
      expect(f.edition, isNull);
    });

    test('malformed field is treated as missing, not as "nothing"', () {
      final f = ServerFeatures.fromJson({'features': 'billing'});
      expect(f.has(FeatureKeys.opdQueue), isTrue);
    });

    test('explicit list gates exactly those keys; edition kept', () {
      final f = ServerFeatures.fromJson({
        'features': ['opd_queue', 'mobile_offline', 42],
        'edition': 'clinic_basic',
      });
      expect(f.has(FeatureKeys.opdQueue), isTrue);
      expect(f.has(FeatureKeys.billing), isFalse);
      expect(f.has(FeatureKeys.consultation), isFalse);
      expect(f.edition, 'clinic_basic');
    });

    test('profile round-trip keeps features and edition; absent stays null',
        () {
      const p = SessionProfile(
          userId: 'u1', features: ['billing'], edition: 'pro');
      final back = SessionProfile.fromJson(p.toJson());
      expect(back.features, ['billing']);
      expect(back.edition, 'pro');
      final legacy = SessionProfile.fromJson({'userId': 'u1'});
      expect(legacy.features, isNull);
      expect(legacy.serverFeatures.has(FeatureKeys.billing), isTrue);
    });
  });

  testWidgets('old server (no features field): every tab is shown',
      (tester) async {
    final graph = await bootGraph(meSays({'role': 'doctor'}));
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['Queue', 'Consult', 'Rx', 'Patients', 'Sync']);
    expect(find.byKey(const Key('mobile-not-enabled')), findsNothing);
  });

  testWidgets('all features reported: every tab is shown, edition in menu',
      (tester) async {
    final graph = await bootGraph(meSays({
      'role': 'doctor',
      'features': allKeys,
      'edition': 'clinic_pro',
    }));
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['Queue', 'Consult', 'Rx', 'Patients', 'Sync']);

    await tester.tap(find.byKey(const Key('settings-menu')));
    await tester.pumpAndSettle();
    expect(find.text('Edition: clinic_pro'), findsOneWidget);
  });

  testWidgets('no billing feature: Billing tab hidden', (tester) async {
    final graph = await bootGraph(meSays({
      'role': 'receptionist',
      'features': ['opd_queue', 'consultation', 'pharmacy', 'mobile_offline'],
    }));
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['Queue', 'Register', 'Appointments', 'Sync']);
    expect(find.byKey(const Key('billing-add')), findsNothing);
  });

  testWidgets('no consultation feature: no Rx even for a doctor; no '
      'opd_queue: no Queue', (tester) async {
    final graph = await bootGraph(meSays({
      'role': 'doctor',
      'features': ['billing', 'mobile_offline'],
    }));
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['Patients', 'Sync']);
    expect(find.byKey(const Key('rx-save')), findsNothing);
    expect(find.byKey(const Key('queue-add')), findsNothing);
  });

  testWidgets('no pharmacy feature: dispense-quantity field hidden on Rx',
      (tester) async {
    final graph = await bootGraph(meSays({
      'role': 'doctor',
      'features': ['opd_queue', 'consultation', 'mobile_offline'],
    }));
    await pumpHome(tester, graph);
    await tester.tap(find.text('Rx'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('rx-save')), findsOneWidget);
    expect(find.byKey(const Key('rx-dispense-qty')), findsNothing);
  });

  testWidgets('no mobile_offline: banner, only the Sync centre remains so '
      'saved work can still be sent', (tester) async {
    final graph = await bootGraph(meSays({
      'role': 'doctor',
      'features': ['opd_queue', 'consultation', 'billing'],
    }));
    graph.outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': 'p1', 'branch_id': 'b1'},
      dedupeKey: 'q',
    );
    await pumpHome(tester, graph);
    expect(find.byKey(const Key('mobile-not-enabled')), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byKey(const Key('queue-add')), findsNothing);
    expect(find.byKey(const Key('register-add')), findsNothing);
    expect(find.byKey(const Key('sync-run')), findsOneWidget);
    expect(find.textContaining('pending: 1'), findsOneWidget);
  });

  testWidgets('features reported online are remembered for an offline start',
      (tester) async {
    final tokens = MemoryTokenStore();
    final store = seededStore();
    final online = await bootGraph(
      meSays({
        'role': 'doctor',
        'features': ['opd_queue', 'mobile_offline'],
        'edition': 'basic',
      }),
      tokens: tokens,
      store: store,
    );
    await pumpHome(tester, online);
    expect(navLabels(tester), ['Queue', 'Patients', 'Sync']);
    final stored = await online.session.profile();
    expect(stored!.features, ['opd_queue', 'mobile_offline']);
    expect(stored.edition, 'basic');
    expect(stored.role, 'doctor');

    // restart in airplane mode: /auth/me fails, the stored set still applies
    await tester.pumpWidget(const SizedBox.shrink());
    final offline = await bootGraph(
      FakeTransport((c) async => throw Exception('no network')),
      tokens: tokens,
      store: store,
    );
    await pumpHome(tester, offline);
    expect(navLabels(tester), ['Queue', 'Patients', 'Sync']);
    expect(find.text('HMS · doctor'), findsOneWidget);
  });

  testWidgets('rural mode respects the feature set too', (tester) async {
    final graph = await bootGraph(meSays({
      'role': 'doctor',
      'features': ['opd_queue', 'consultation', 'mobile_offline'],
    }));
    await graph.settings.setRuralMode(true);
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['Register', 'Queue', 'Fast Rx']);
  });
}
