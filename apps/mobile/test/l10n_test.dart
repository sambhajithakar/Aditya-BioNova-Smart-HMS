/// Multilingual UI (English / मराठी / हिंदी):
/// * the three ARB files carry exactly the same keys, no empty values and
///   the same placeholders;
/// * screens render in mr and hi (login, home shell, Rx) with drug names,
///   doses and UHIDs left untranslated;
/// * the language picker on the login and home screens persists the choice
///   on the device; with no choice the device language is used (English
///   when the device language is unsupported).
library;

import 'dart:convert';
import 'dart:io';

import 'package:aditya_bionova_mobile/auth/app_lock.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/l10n/l10n.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/settings/app_settings.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Map<String, dynamic> readArb(String locale) => jsonDecode(
      File('lib/l10n/app_$locale.arb').readAsStringSync(),
    ) as Map<String, dynamic>;

Set<String> messageKeys(Map<String, dynamic> arb) =>
    arb.keys.where((k) => !k.startsWith('@')).toSet();

/// Top-level `{name}` / `{name, plural, …}` placeholders of an ICU message.
Set<String> placeholders(String message) => RegExp(r'\{(\w+)[,}]')
    .allMatches(message)
    .map((m) => m.group(1)!)
    .toSet();

Future<AppGraph> bootGraph({
  FakeTransport? transport,
  MemoryLocalStore? store,
  String role = 'doctor',
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

void main() {
  group('ARB files', () {
    final en = readArb('en');
    final mr = readArb('mr');
    final hi = readArb('hi');

    test('en, mr and hi have identical key sets', () {
      final keys = messageKeys(en);
      expect(keys.length, greaterThan(150));
      expect(messageKeys(mr), keys, reason: 'mr must match en');
      expect(messageKeys(hi), keys, reason: 'hi must match en');
      expect(mr['@@locale'], 'mr');
      expect(hi['@@locale'], 'hi');
    });

    test('no empty values and the same placeholders in every language', () {
      for (final arb in [en, mr, hi]) {
        for (final key in messageKeys(arb)) {
          final value = arb[key];
          expect(value, isA<String>(), reason: '${arb['@@locale']}.$key');
          expect((value as String).trim(), isNotEmpty,
              reason: '${arb['@@locale']}.$key is empty');
        }
      }
      for (final key in messageKeys(en)) {
        final expected = placeholders(en[key] as String);
        expect(placeholders(mr[key] as String), expected, reason: 'mr.$key');
        expect(placeholders(hi[key] as String), expected, reason: 'hi.$key');
      }
    });

    test('translations are actually translated (Devanagari) where it matters',
        () {
      final devanagari = RegExp(r'[ऀ-ॿ]');
      for (final key in ['loginSubmit', 'tabQueue', 'tabRegister', 'rxSave',
          'syncNow', 'registerAllergies', 'stateConflict']) {
        expect(devanagari.hasMatch(mr[key] as String), isTrue, reason: 'mr.$key');
        expect(devanagari.hasMatch(hi[key] as String), isTrue, reason: 'hi.$key');
      }
    });

    test('plurals and placeholders format in all three languages', () {
      for (final code in AppSettings.supportedLanguages) {
        final l = lookupAppLocalizations(Locale(code));
        expect(l.pinWrong(1), contains('1'));
        expect(l.pinWrong(4), contains('4'));
        expect(l.rxItemLine('Paracetamol', '500 mg', 'TDS', '5'),
            allOf(contains('Paracetamol'), contains('500 mg'), contains('TDS')),
            reason: 'drug names / doses / codes are never translated');
      }
      final en = lookupAppLocalizations(const Locale('en'));
      expect(rateLimitedMessage(en, const Duration(seconds: 120)),
          'Too many attempts. Try again in 2 minutes.');
      expect(rateLimitedMessage(en, const Duration(seconds: 45)),
          'Too many attempts. Try again in 45 seconds.');
    });
  });

  group('rendering in मराठी and हिंदी', () {
    testWidgets('login screen in Marathi, then switched to Hindi via the '
        'picker; the choice survives a restart', (tester) async {
      final store = MemoryLocalStore();
      final tokens = MemoryTokenStore();
      final graph = AppGraph(
        baseUrl: 'http://test',
        transportOverride: FakeTransport.routes({}),
        tokenStore: tokens,
        store: store,
        appLock: AppLock(tokens, iterations: 1000),
      );
      await graph.settings.setLanguage('mr');

      await tester.pumpWidget(HmsApp(graph: graph));
      await tester.pumpAndSettle();
      expect(find.text('साइन इन करा'), findsOneWidget);
      expect(find.text('पासवर्ड'), findsOneWidget);
      expect(find.text('Sign in'), findsNothing);

      await tester.tap(find.byKey(const Key('language-menu')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('language-hi')).last);
      await tester.pumpAndSettle();
      expect(find.text('साइन इन करें'), findsOneWidget);
      expect(find.text('क्लिनिक कोड (वैकल्पिक)'), findsOneWidget);

      // persisted in the device store, not in memory only
      expect((store.doc['prefs'] as Map)['language'], 'hi');
      expect(AppSettings(store).language, 'hi', reason: 'restart keeps it');
    });

    testWidgets('home shell + Rx in Marathi keep drug name and UHID as-is',
        (tester) async {
      tester.view.physicalSize = const Size(1080, 2600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      final graph = await bootGraph();
      await graph.settings.setLanguage('mr');
      await tester.pumpWidget(HmsMaterialApp(
        settings: graph.settings,
        home: HomeScreen(graph: graph),
      ));
      await tester.pumpAndSettle();

      expect(find.text('रांग'), findsOneWidget); // Queue
      expect(find.text('सल्ला'), findsOneWidget); // Consult (doctor interface)
      expect(find.text('रुग्ण'), findsWidgets); // Patients
      expect(find.text('सिंक'), findsOneWidget);
      expect(find.text('रांगेत जोडा (ऑफलाइनही चालते)'), findsOneWidget);
      expect(find.textContaining('P0001 Aarti Patil'), findsWidgets,
          reason: 'UHID and patient name are shown untranslated');

      await tester.tap(find.text('Rx'));
      await tester.pumpAndSettle();
      expect(find.text('Paracetamol'), findsOneWidget,
          reason: 'drug names come from the catalog untranslated');
      expect(find.text('मसुदा जतन करा (ऑफलाइनही चालते)'), findsOneWidget);

      await tester.enterText(find.byKey(const Key('rx-dose')), '500 mg');
      await tester.enterText(find.byKey(const Key('rx-frequency')), 'TDS');
      await tester.tap(find.byKey(const Key('rx-add-item')));
      await tester.pump();
      expect(find.text('Paracetamol — 500 mg, TDS, 5 दिवस'), findsOneWidget);
    });

    testWidgets('home shell in Hindi; picker on home switches to English',
        (tester) async {
      final graph = await bootGraph(role: 'receptionist');
      await graph.settings.setLanguage('hi');
      await tester.pumpWidget(HmsMaterialApp(
        settings: graph.settings,
        home: HomeScreen(graph: graph),
      ));
      await tester.pumpAndSettle();

      expect(find.text('कतार'), findsOneWidget);
      expect(find.text('पंजीकरण'), findsOneWidget);
      expect(find.text('कतार में जोड़ें (ऑफ़लाइन भी चलता है)'), findsOneWidget);
      expect(find.text('Rx'), findsNothing, reason: 'role still gates Rx');

      await tester.tap(find.byKey(const Key('language-menu')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('language-en')).last);
      await tester.pumpAndSettle();
      expect(find.text('Queue'), findsOneWidget);
      expect(graph.settings.language, 'en');
    });
  });

  group('default language', () {
    testWidgets('follows a supported device locale (mr-IN)', (tester) async {
      tester.platformDispatcher.localesTestValue = const [Locale('mr', 'IN')];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final graph = AppGraph(
        baseUrl: 'http://test',
        transportOverride: FakeTransport.routes({}),
      );
      expect(graph.settings.language, isNull);

      await tester.pumpWidget(HmsApp(graph: graph));
      await tester.pumpAndSettle();
      expect(find.text('साइन इन करा'), findsOneWidget);
    });

    testWidgets('falls back to English for an unsupported device locale',
        (tester) async {
      tester.platformDispatcher.localesTestValue = const [Locale('fr', 'FR')];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final graph = AppGraph(
        baseUrl: 'http://test',
        transportOverride: FakeTransport.routes({}),
      );

      await tester.pumpWidget(HmsApp(graph: graph));
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);
    });

    testWidgets('"Device language" clears an explicit choice', (tester) async {
      tester.platformDispatcher.localesTestValue = const [Locale('hi', 'IN')];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final graph = AppGraph(
        baseUrl: 'http://test',
        transportOverride: FakeTransport.routes({}),
      );
      await graph.settings.setLanguage('en');

      await tester.pumpWidget(HmsApp(graph: graph));
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);

      await tester.tap(find.byKey(const Key('language-menu')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('language-device')).last);
      await tester.pumpAndSettle();
      expect(graph.settings.language, isNull);
      expect(find.text('साइन इन करें'), findsOneWidget);
    });
  });

  test('settings ignore an unknown stored language', () {
    final settings = AppSettings(MemoryLocalStore({
      'prefs': {'language': 'xx', 'ruralMode': true},
    }));
    expect(settings.language, isNull);
    expect(settings.ruralMode, isTrue);
    expect(() => settings.setLanguage('fr'), throwsArgumentError);
  });
}
