/// App lock (H22): salted PBKDF2 PIN hash in the secure store, relock after
/// inactivity, lockout after repeated failures, and the resume handler
/// (lock screen after a long absence, sync attempt after a short one).
library;

import 'dart:convert';

import 'package:aditya_bionova_mobile/auth/app_lock.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

void main() {
  test('the PIN is stored only as a salted PBKDF2 hash', () async {
    final store = MemoryTokenStore();
    final lock = AppLock(store, iterations: 1000);
    await lock.setPin('2468');
    final first = jsonDecode((await store.read(AppLock.pinKey))!) as Map;
    expect(first['alg'], 'pbkdf2-hmac-sha256');
    expect(first['iter'], 1000);
    expect((first['salt'] as String).length, 32); // 16 bytes
    expect(jsonEncode(first).contains('2468'), isFalse);

    await lock.setPin('2468');
    final second = jsonDecode((await store.read(AppLock.pinKey))!) as Map;
    expect(second['hash'], isNot(first['hash']), reason: 'fresh salt');

    lock.lock();
    expect(await lock.unlock('1357'), UnlockResult.wrongPin);
    expect(await lock.unlock('2468'), UnlockResult.unlocked);
    expect(lock.isUnlocked, isTrue);
    expect(() => lock.setPin('12'), throwsArgumentError);
  });

  test('the default work factor is a real one', () {
    expect(AppLock(MemoryTokenStore()).iterations, greaterThanOrEqualTo(100000));
  });

  test('relocks only after the inactivity timeout', () async {
    var now = DateTime(2026, 10, 20, 10);
    final lock = AppLock(MemoryTokenStore(),
        iterations: 1000, clock: () => now);
    await lock.setPin('2468');

    lock.onBackground();
    now = now.add(const Duration(minutes: 2));
    expect(lock.onResume(), isFalse, reason: 'short absence: stay unlocked');

    lock.onBackground();
    now = now.add(const Duration(minutes: 5));
    expect(lock.onResume(), isTrue, reason: 'long absence: PIN again');
    expect(lock.isUnlocked, isFalse);
  });

  test('lockout after 5 wrong PINs erases the PIN and the session',
      () async {
    final store = MemoryTokenStore();
    await Session(store).save(
        accessToken: 'AT',
        refreshToken: 'RT',
        profile: const SessionProfile(userId: 'u1'));
    final lock = AppLock(store, iterations: 1000);
    await lock.setPin('2468');
    for (var i = 0; i < 4; i++) {
      expect(await lock.unlock('0000'), UnlockResult.wrongPin);
    }
    expect(await lock.remainingAttempts(), 1);
    expect(await lock.unlock('0000'), UnlockResult.lockedOut);
    expect(await lock.hasPin(), isFalse);
    expect(await Session(store).hasStoredSession(), isFalse);
    // the profile stays: the same user re-authenticates online
    expect((await Session(store).profile())!.userId, 'u1');
  });

  testWidgets('resume after inactivity shows the lock; a short absence '
      'triggers a sync attempt instead', (tester) async {
    var now = DateTime(2026, 10, 20, 10);
    final tokens = MemoryTokenStore();
    await Session(tokens).save(
      accessToken: 'AT',
      refreshToken: 'RT',
      profile: const SessionProfile(userId: 'u1', role: 'receptionist'),
    );
    final lock = AppLock(tokens, iterations: 1000, clock: () => now);
    await lock.setPin('2468');

    final fake = FakeTransport.routes({
      'GET /auth/me': json({'role': 'receptionist'}),
      'GET /patients': json({'items': <dynamic>[], 'total': 0}),
      'GET /branches': json(<dynamic>[]),
      'POST /opd/queue': json({'id': 'q1'}, status: 201),
    });
    final graph = AppGraph(
      baseUrl: 'http://test',
      transportOverride: fake,
      tokenStore: tokens,
      appLock: lock,
      autoSync: true,
    );
    await graph.restoreSession();

    await tester.pumpWidget(HmsApp(graph: graph));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('pin-entry')), '2468');
    await tester.tap(find.byKey(const Key('pin-submit')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('queue-add')), findsOneWidget);

    graph.outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {'patient_id': 'p1', 'branch_id': 'b1'},
      dedupeKey: 'k',
      userId: 'u1',
    );

    // short absence → no lock, the resume pushes the outbox
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    now = now.add(const Duration(minutes: 1));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('Enter your app PIN'), findsNothing);
    expect(fake.calls.where((c) => c.route == 'POST /opd/queue'), hasLength(1));
    expect(graph.outbox.total, 0);

    // long absence → PIN again before any PHI
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    now = now.add(const Duration(minutes: 10));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('Enter your app PIN'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('pin-entry')), '2468');
    await tester.tap(find.byKey(const Key('pin-submit')));
    await tester.pumpAndSettle();
    expect(find.text('Enter your app PIN'), findsNothing);
    expect(find.byKey(const Key('queue-add')), findsOneWidget);
    graph.scheduler.stop();
  });
}
