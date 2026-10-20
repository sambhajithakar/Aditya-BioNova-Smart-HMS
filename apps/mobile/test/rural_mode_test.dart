/// Rural Clinic simplified mode: a persisted device setting that enlarges
/// touch targets (>= 56 dp) and text, reduces navigation to
/// Register -> Queue -> Fast Rx -> Bill (Sync centre in the app bar) and adds
/// quick-pick chips on Fast Rx — on the SAME screens, outbox and engine.
library;

import 'package:aditya_bionova_mobile/auth/features.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/settings/app_settings.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Future<AppGraph> bootGraph({
  MemoryLocalStore? store,
  String role = 'doctor',
  FakeTransport? transport,
}) async {
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: transport ??
        FakeTransport.routes({
          'GET /auth/me': json({'role': role}),
        }),
    tokenStore: MemoryTokenStore(),
    store: store ??
        MemoryLocalStore({
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
        }),
  );
  await graph.session.save(accessToken: 'tok', refreshToken: 'r');
  return graph;
}

Future<void> pumpHome(WidgetTester tester, AppGraph graph) async {
  tester.view.physicalSize = const Size(1080, 3200);
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

void expectTall(WidgetTester tester, Finder finder, {String? reason}) {
  expect(finder, findsWidgets, reason: reason);
  final size = tester.getSize(finder.first);
  expect(size.height, greaterThanOrEqualTo(kRuralTouchTarget),
      reason: '${reason ?? finder} is ${size.height} dp tall');
}

void main() {
  test('pure tab order: rural = Register, Queue, Rx, Billing (no Sync tab)',
      () {
    expect(
      visibleTabs(
          canPrescribe: true, features: ServerFeatures.all, rural: true),
      [HomeTab.register, HomeTab.queue, HomeTab.rx, HomeTab.billing],
    );
    expect(
      visibleTabs(
          canPrescribe: false, features: ServerFeatures.all, rural: true),
      [HomeTab.register, HomeTab.queue, HomeTab.billing],
    );
    expect(
      visibleTabs(
          canPrescribe: true, features: ServerFeatures.all, rural: false),
      [HomeTab.queue, HomeTab.register, HomeTab.rx, HomeTab.billing,
        HomeTab.sync],
    );
  });

  testWidgets('toggle from the settings menu: four-step navigation, Sync in '
      'the app bar, setting persisted', (tester) async {
    final store = MemoryLocalStore({
      'directory': {
        'patients': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Aarti Patil'},
        ],
        'branches': [
          {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
        ],
      },
    });
    final graph = await bootGraph(store: store);
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['Queue', 'Consult', 'Rx', 'Patients', 'Sync']);
    expect(find.byKey(const Key('rural-sync')), findsNothing);

    await tester.tap(find.byKey(const Key('settings-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('rural-toggle')));
    await tester.pumpAndSettle();

    expect(graph.settings.ruralMode, isTrue);
    expect(navLabels(tester), ['Register', 'Queue', 'Fast Rx', 'Bill']);
    // first step is Register
    expect(find.byKey(const Key('register-add')), findsOneWidget);
    // persisted in the device store; a restart reads it back
    expect((store.doc['prefs'] as Map)['ruralMode'], isTrue);
    expect(AppSettings(store).ruralMode, isTrue);

    // Sync centre is one tap away in the app bar
    expectTall(tester, find.byKey(const Key('rural-sync')));
    await tester.tap(find.byKey(const Key('rural-sync')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('sync-run')), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    // and it can be switched off again
    await tester.tap(find.byKey(const Key('settings-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('rural-toggle')));
    await tester.pumpAndSettle();
    expect(graph.settings.ruralMode, isFalse);
    expect(navLabels(tester), ['Queue', 'Consult', 'Rx', 'Patients', 'Sync']);
  });

  testWidgets('large touch targets and larger text on every step',
      (tester) async {
    final graph = await bootGraph();
    await graph.settings.setRuralMode(true);
    await pumpHome(tester, graph);

    // text scale at least 1.25x
    final ctx = tester.element(find.byKey(const Key('register-add')));
    expect(MediaQuery.textScalerOf(ctx).scale(10),
        greaterThanOrEqualTo(10 * kRuralTextScale));

    expectTall(tester, find.byKey(const Key('register-add')));
    expectTall(tester, find.byType(NavigationBar));
    expectTall(tester, find.byKey(const Key('sign-out')));
    expectTall(tester, find.byKey(const Key('language-menu')));

    await tester.tap(find.text('Queue'));
    await tester.pumpAndSettle();
    expectTall(tester, find.byKey(const Key('queue-add')));
    expectTall(tester, find.byKey(const Key('queue-patient')));

    await tester.tap(find.text('Fast Rx'));
    await tester.pumpAndSettle();
    expectTall(tester, find.byKey(const Key('rx-save')));
    expectTall(tester, find.byKey(const Key('rx-add-item')));
    expectTall(tester, find.byKey(const Key('rx-freq-BD')));
    expectTall(tester, find.byKey(const Key('rx-days-5')));

    await tester.tap(find.text('Bill'));
    await tester.pumpAndSettle();
    expectTall(tester, find.byKey(const Key('billing-add')));
    expectTall(tester, find.byKey(const Key('billing-item-type')));
  });

  testWidgets('quick-pick chips fill frequency and days; the draft goes '
      'through the same outbox op as normal mode', (tester) async {
    final graph = await bootGraph();
    await graph.settings.setRuralMode(true);
    await pumpHome(tester, graph);
    await tester.tap(find.text('Fast Rx'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('rx-dose')), '500 mg');
    await tester.tap(find.byKey(const Key('rx-freq-TDS')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('rx-days-7')));
    await tester.pump();
    expect(
        tester
            .widget<TextField>(find.byKey(const Key('rx-frequency')))
            .controller!
            .text,
        'TDS');
    expect(
        tester
            .widget<TextField>(find.byKey(const Key('rx-duration')))
            .controller!
            .text,
        '7');
    // tooltip explains the code in the UI language
    expect(
        tester
            .widget<ChoiceChip>(find.descendant(
                of: find.byKey(const Key('rx-freq-TDS')),
                matching: find.byType(ChoiceChip)))
            .tooltip,
        'three times a day');

    await tester.tap(find.byKey(const Key('rx-add-item')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('rx-save')));
    await tester.pump();

    final op = graph.outbox.ops.single;
    expect(op.entity, 'prescription');
    expect(op.path, '/prescriptions');
    expect(op.payload['items'][0],
        containsPair('frequency', 'TDS'));
    expect(op.payload['items'][0], containsPair('duration_days', 7));
    expect(op.payload['items'][0], containsPair('dose', '500 mg'));
    expect(op.dedupeKey, startsWith('rx:p1:'));
  });

  testWidgets('normal mode: standard sizes and no chips', (tester) async {
    final graph = await bootGraph();
    await pumpHome(tester, graph);
    // sanity check that the rural assertions above are not vacuous
    expect(tester.getSize(find.byKey(const Key('queue-add'))).height,
        lessThan(kRuralTouchTarget));
    final ctx = tester.element(find.byKey(const Key('queue-add')));
    expect(MediaQuery.textScalerOf(ctx).scale(10), 10);
    await tester.tap(find.text('Rx'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('rx-save')), findsOneWidget);
    expect(find.byKey(const Key('rx-freq-BD')), findsNothing);
    expect(find.byKey(const Key('rx-days-5')), findsNothing);
  });

  testWidgets('rural mode in Marathi: four steps are translated',
      (tester) async {
    final graph = await bootGraph();
    await graph.settings.setRuralMode(true);
    await graph.settings.setLanguage('mr');
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['नोंदणी', 'रांग', 'जलद Rx', 'बिल']);
  });

  testWidgets('a reception role in rural mode gets Register, Queue, Bill',
      (tester) async {
    final graph = await bootGraph(role: 'receptionist');
    await graph.settings.setRuralMode(true);
    await pumpHome(tester, graph);
    expect(navLabels(tester), ['Register', 'Queue', 'Bill']);
  });
}
