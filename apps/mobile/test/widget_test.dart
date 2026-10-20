/// Login / MFA / app-lock widget tests: the form posts the real
/// `POST /auth/login` contract through the fake transport; an MFA account
/// gets the code step (`POST /auth/mfa/verify`); 429 shows how long to
/// wait; the first sign-in sets a PIN; a cold start with a stored session
/// opens at the PIN lock and reaches Home with NO network (H22).
library;

import 'package:aditya_bionova_mobile/api/transport.dart';
import 'package:aditya_bionova_mobile/auth/app_lock.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

AppGraph graphWith(FakeTransport fake, {MemoryTokenStore? tokens}) {
  final store = tokens ?? MemoryTokenStore();
  return AppGraph(
    baseUrl: 'http://test',
    transportOverride: fake,
    tokenStore: store,
    appLock: AppLock(store, iterations: 1000),
  );
}

Map<String, dynamic> authSession({String userId = 'u1', String role = 'doctor'}) => {
      'user': {
        'id': userId,
        'email': 'dr@clinic.test',
        'full_name': 'Dr X',
        'status': 'active',
      },
      'organization': {'id': 'o1', 'name': 'Clinic', 'slug': 'clinic'},
      'role': role,
      'permissions': <String>[],
      'tokens': {
        'access_token': 'AT',
        'refresh_token': 'RT',
        'token_type': 'bearer',
        'expires_in': 1800,
      },
    };

Map<String, ApiResponse> shellRoutes() => {
      'GET /auth/me': json({'role': 'doctor', 'user': {'full_name': 'Dr X'}}),
      'GET /patients': json({
        'items': [
          {'id': 'p1', 'uhid': 'P0001', 'full_name': 'Walk In'},
        ],
        'total': 1,
      }),
      'GET /branches': json([
        {'id': 'b1', 'name': 'Main', 'code': 'MAIN'},
      ]),
    };

Future<void> enterCredentials(WidgetTester tester) async {
  await tester.enterText(
      find.byKey(const Key('login-email')), 'dr@clinic.test');
  await tester.enterText(find.byKey(const Key('login-password')), 'secret');
  await tester.tap(find.byKey(const Key('login-submit')));
  await tester.pumpAndSettle();
}

Future<void> setPin(WidgetTester tester, String pin) async {
  expect(find.text('Set an app PIN'), findsOneWidget);
  await tester.enterText(find.byKey(const Key('pin-entry')), pin);
  await tester.enterText(find.byKey(const Key('pin-confirm')), pin);
  await tester.tap(find.byKey(const Key('pin-submit')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('first sign-in → set PIN → role-aware shell', (tester) async {
    final fake = FakeTransport.routes({
      'POST /auth/login': json(authSession()),
      ...shellRoutes(),
    });
    final graph = graphWith(fake);

    await tester.pumpWidget(HmsApp(graph: graph));
    await tester.pumpAndSettle();
    expect(find.text('Sign in'), findsOneWidget);

    await enterCredentials(tester);
    await setPin(tester, '2468');

    // landed on the shell with the role from /auth/me
    expect(find.text('HMS · doctor'), findsOneWidget);
    expect(find.byKey(const Key('queue-add')), findsOneWidget);

    // slug omitted when blank; login hit exactly once
    final logins =
        fake.calls.where((c) => c.path == '/auth/login').toList(growable: false);
    expect(logins, hasLength(1));
    expect(logins.single.body!.containsKey('organization_slug'), isFalse);

    // profile stored and stamped on new ops
    expect((await graph.session.profile())!.userId, 'u1');
    expect(graph.outbox.ownerId, 'u1');
    expect(await graph.appLock.hasPin(), isTrue);
  });

  testWidgets('failed sign-in shows the server detail and stays put',
      (tester) async {
    final fake = FakeTransport.routes({
      'POST /auth/login':
          json({'detail': 'Invalid email or password'}, status: 401),
    });

    await tester.pumpWidget(HmsApp(graph: graphWith(fake)));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const Key('login-email')), 'dr@clinic.test');
    await tester.enterText(find.byKey(const Key('login-password')), 'wrong');
    await tester.tap(find.byKey(const Key('login-submit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-error')), findsOneWidget);
    expect(find.textContaining('Invalid email or password'), findsOneWidget);
    // still on the login screen (no shell, no token stored)
    expect(find.byKey(const Key('login-submit')), findsOneWidget);
    expect(find.byKey(const Key('queue-add')), findsNothing);
  });

  testWidgets('429 on sign-in shows how long to wait', (tester) async {
    final fake = FakeTransport.routes({
      'POST /auth/login': json(
        {'detail': 'Too many attempts. Try again later.'},
        status: 429,
        headers: {'retry-after': '120'},
      ),
    });

    await tester.pumpWidget(HmsApp(graph: graphWith(fake)));
    await tester.pumpAndSettle();
    await enterCredentials(tester);

    expect(find.text('Too many attempts. Try again in 2 minutes.'),
        findsOneWidget);
    expect(find.byKey(const Key('login-submit')), findsOneWidget);
  });

  testWidgets('MFA account: code step → verify → PIN → shell',
      (tester) async {
    var verifyAttempts = 0;
    final routes = shellRoutes();
    final fake = FakeTransport((c) async {
      switch (c.route) {
        case 'POST /auth/login':
          return json({
            'mfa_required': true,
            'mfa_token': 'mfa-tok-1',
            'methods': ['totp'],
            'expires_in': 300,
          });
        case 'POST /auth/mfa/verify':
          verifyAttempts += 1;
          if (c.body!['code'] != '123456') {
            return json({'detail': 'Invalid code'}, status: 401);
          }
          return json(authSession(userId: 'u-mfa'));
      }
      return routes[c.route] ?? json({'detail': 'no stub'}, status: 404);
    });
    final graph = graphWith(fake);

    await tester.pumpWidget(HmsApp(graph: graph));
    await tester.pumpAndSettle();
    await enterCredentials(tester);

    // no session yet: second factor required
    expect(await graph.session.accessToken(), isNull);
    expect(find.text('Two-step verification'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('login-mfa-code')), '000000');
    await tester.tap(find.byKey(const Key('login-mfa-submit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('not accepted'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('login-mfa-code')), '123456');
    await tester.tap(find.byKey(const Key('login-mfa-submit')));
    await tester.pumpAndSettle();

    expect(verifyAttempts, 2);
    final verify = fake.calls.lastWhere((c) => c.path == '/auth/mfa/verify');
    expect(verify.body, {'mfa_token': 'mfa-tok-1', 'code': '123456'});
    expect(await graph.session.accessToken(), 'AT');

    await setPin(tester, '135790');
    expect(find.text('HMS · doctor'), findsOneWidget);
  });

  testWidgets('cold start with a stored session opens at the PIN lock and '
      'reaches Home with no network (H22)', (tester) async {
    final tokens = MemoryTokenStore();
    final seed = Session(tokens);
    await seed.save(
      accessToken: 'AT',
      refreshToken: 'RT',
      profile: const SessionProfile(
          userId: 'u1', email: 'dr@clinic.test', role: 'doctor'),
    );
    await AppLock(tokens, iterations: 1000).setPin('2468');

    // airplane mode: every request fails at the network layer
    final offline = FakeTransport((c) async => throw Exception('no network'));
    final graph = graphWith(offline, tokens: tokens);
    await graph.restoreSession();

    await tester.pumpWidget(HmsApp(graph: graph));
    await tester.pumpAndSettle();

    expect(find.text('Enter your app PIN'), findsOneWidget);
    expect(find.byKey(const Key('login-submit')), findsNothing);
    expect(find.byKey(const Key('queue-add')), findsNothing,
        reason: 'no PHI before the PIN');

    await tester.enterText(find.byKey(const Key('pin-entry')), '1111');
    await tester.tap(find.byKey(const Key('pin-submit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Wrong PIN — 4 attempts left'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('pin-entry')), '2468');
    await tester.tap(find.byKey(const Key('pin-submit')));
    await tester.pumpAndSettle();

    // Home, offline, role from the stored profile
    expect(find.byKey(const Key('queue-add')), findsOneWidget);
    expect(find.text('HMS · doctor'), findsOneWidget);
    expect(graph.outbox.ownerId, 'u1');
  });

  testWidgets('too many wrong PINs → online sign-in required, outbox kept',
      (tester) async {
    final tokens = MemoryTokenStore();
    await Session(tokens).save(
      accessToken: 'AT',
      refreshToken: 'RT',
      profile: const SessionProfile(userId: 'u1', email: 'dr@clinic.test'),
    );
    await AppLock(tokens, iterations: 1000).setPin('2468');
    final graph = graphWith(
        FakeTransport((c) async => throw Exception('no network')),
        tokens: tokens);
    await graph.restoreSession();
    graph.outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': 'p1', 'branch_id': 'b1'},
      dedupeKey: 'q',
    );

    await tester.pumpWidget(HmsApp(graph: graph));
    await tester.pumpAndSettle();
    for (var i = 0; i < 5; i++) {
      await tester.enterText(find.byKey(const Key('pin-entry')), '0000');
      await tester.tap(find.byKey(const Key('pin-submit')));
      await tester.pumpAndSettle();
    }

    expect(find.byKey(const Key('login-submit')), findsOneWidget);
    expect(find.byKey(const Key('login-notice')), findsOneWidget);
    expect(await graph.appLock.hasPin(), isFalse);
    expect(await graph.session.hasStoredSession(), isFalse);
    expect(graph.outbox.total, 1, reason: 'queued work is not destroyed');
  });

  testWidgets('a session without a PIN falls back to the online sign-in',
      (tester) async {
    final tokens = MemoryTokenStore();
    await Session(tokens).save(
      accessToken: 'AT',
      refreshToken: 'RT',
      profile: const SessionProfile(userId: 'u1'),
    );
    final graph = graphWith(FakeTransport.routes({}), tokens: tokens);

    await tester.pumpWidget(HmsApp(graph: graph));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('login-submit')), findsOneWidget);
  });
}
