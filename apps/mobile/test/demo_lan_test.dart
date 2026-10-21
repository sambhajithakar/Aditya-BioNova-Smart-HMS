/// LAN demo build (docs/DEMO.md): which server addresses are accepted, the
/// server-choice screen, and the static Android guards that keep the
/// cleartext policy out of every other build.
library;

import 'dart:io';

import 'package:aditya_bionova_mobile/boot.dart';
import 'package:aditya_bionova_mobile/demo/demo_server.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/demo_server_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('normalizeDemoServer', () {
    test('private LAN addresses get http and the default port', () {
      expect(normalizeDemoServer('192.168.1.20'), 'http://192.168.1.20:8000');
      expect(normalizeDemoServer(' 192.168.1.20:8100 '),
          'http://192.168.1.20:8100');
      expect(normalizeDemoServer('http://10.0.0.5:8000/'),
          'http://10.0.0.5:8000');
      expect(normalizeDemoServer('172.16.4.2'), 'http://172.16.4.2:8000');
      expect(normalizeDemoServer('172.31.255.1:80'), 'http://172.31.255.1:80');
      expect(normalizeDemoServer('my-laptop.local'),
          'http://my-laptop.local:8000');
    });

    test('cleartext to a public or loopback host is refused', () {
      for (final bad in [
        '8.8.8.8',
        'http://demo.example.com',
        '172.32.0.1',
        '172.15.0.1',
        '192.169.1.1',
        '127.0.0.1',
        '.local',
        '192.168.1',
        '192.168.1.300',
      ]) {
        expect(normalizeDemoServer(bad), isNull, reason: bad);
      }
    });

    test('https is accepted for any host', () {
      expect(normalizeDemoServer('https://demo.example.com'),
          'https://demo.example.com:443');
    });

    test('junk, paths, credentials and other schemes are refused', () {
      for (final bad in [
        '',
        '   ',
        'ftp://192.168.1.2',
        'http://user:pw@192.168.1.2',
        'http://192.168.1.2:8000/api',
        'http://192.168.1.2?x=1',
        'http://192.168.1.2:99999',
        'http://[::1]:8000',
        'http://192.168.1.2:0',
      ]) {
        expect(normalizeDemoServer(bad), isNull, reason: bad);
      }
    });
  });

  group('DemoServerScreen', () {
    Future<List<String>> pump(
      WidgetTester tester,
      DemoProbeResult result, {
      List<BootOutcome>? outcomes,
    }) async {
      final connected = <String>[];
      final next = BootNeedsDemoServer(connect: (_) async => throw 'unused');
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: kLocalizationsDelegates,
        supportedLocales: kSupportedLocales,
        home: DemoServerScreen(
          request: BootNeedsDemoServer(connect: (url) async {
            connected.add(url);
            return next;
          }),
          onOutcome: (o) => outcomes?.add(o),
          probe: (_) async => result,
        ),
      ));
      return connected;
    }

    Future<void> submit(WidgetTester tester, String address) async {
      await tester.enterText(
          find.byKey(const Key('demo-server-address')), address);
      await tester.tap(find.byKey(const Key('demo-server-connect')));
      await tester.pumpAndSettle();
    }

    testWidgets('a reachable demo server is stored and the app boots',
        (tester) async {
      final outcomes = <BootOutcome>[];
      final connected =
          await pump(tester, DemoProbeResult.ok, outcomes: outcomes);
      await submit(tester, '192.168.1.20');
      expect(connected, ['http://192.168.1.20:8000']);
      expect(outcomes, hasLength(1));
    });

    testWidgets('an invalid address is explained and nothing is stored',
        (tester) async {
      final connected = await pump(tester, DemoProbeResult.ok);
      await submit(tester, 'demo.example.com');
      expect(connected, isEmpty);
      expect(find.byKey(const Key('demo-server-error')), findsOneWidget);
    });

    testWidgets('a production server is refused', (tester) async {
      final connected = await pump(tester, DemoProbeResult.production);
      await submit(tester, '192.168.1.20');
      expect(connected, isEmpty);
      expect(find.textContaining('never connects to production'),
          findsOneWidget);
    });

    testWidgets('an unreachable server is explained', (tester) async {
      final connected = await pump(tester, DemoProbeResult.unreachable);
      await submit(tester, '10.0.0.9:8000');
      expect(connected, isEmpty);
      expect(find.textContaining('http://10.0.0.9:8000'), findsOneWidget);
    });
  });

  test('ordinary builds are not demo builds', () {
    expect(kDemoLan, isFalse);
  }, skip: kDemoLan ? 'run with HMS_DEMO_LAN=true' : false);

  group('Android guards', () {
    String read(String p) => File(p).readAsStringSync();

    test('the cleartext overlay is used only by the HMS_DEMO_LAN build', () {
      const overlay =
          'android/app/src/demoLan/res/xml/network_security_config.xml';
      expect(read(overlay), contains('cleartextTrafficPermitted="true"'));
      final gradle = read('android/app/build.gradle.kts');
      expect(gradle, contains('"HMS_DEMO_LAN=true"'));
      expect(
        gradle,
        contains('if (demoLan) {\n'
            '        sourceSets.getByName("release").res.srcDir("src/demoLan/res")'),
      );
      // never signed with the owner's key
      expect(gradle, contains('releaseRequested && demoLan && keystorePropertiesFile.exists()'));
      // the main policy stays HTTPS-only
      expect(read('android/app/src/main/res/xml/network_security_config.xml'),
          contains('cleartextTrafficPermitted="false"'));
    });
  });
}
