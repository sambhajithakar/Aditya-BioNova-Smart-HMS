/// H23 / D3: a store that cannot be unlocked must FAIL CLOSED — no silent
/// in-memory fallback. The recovery screen explains it and only an
/// explicit, confirmed reset deletes the local data.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:aditya_bionova_mobile/auth/app_lock.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/boot.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

void main() {
  late Directory tmpDir;
  late File file;

  setUp(() {
    tmpDir = Directory.systemTemp.createTempSync('hms_recovery');
    file = File('${tmpDir.path}/hms_offline.json');
  });

  tearDown(() {
    if (tmpDir.existsSync()) tmpDir.deleteSync(recursive: true);
  });

  Uint8List keyOf(int fill) =>
      Uint8List.fromList(List<int>.generate(32, (_) => fill));

  /// A device whose sealed file was written with key 1 but whose Keystore
  /// now hands out key 2 (the restore-onto-a-new-phone case).
  Future<({Future<BootOutcome> Function() boot, MemoryTokenStore tokens})>
      restoredDevice() async {
    final original = EncryptedFileStore(file: file, keys: FixedKeyProvider(keyOf(1)));
    await original.open();
    await original.saveSection('outbox', {
      'ops': [
        {'id': 'op1'}
      ],
    });

    final tokens = MemoryTokenStore();
    await Session(tokens).save(
      accessToken: 'AT',
      refreshToken: 'RT',
      profile: const SessionProfile(userId: 'u1'),
    );
    await AppLock(tokens, iterations: 1000).setPin('2468');

    var currentKey = keyOf(2);
    Future<BootOutcome> boot() => bootGraph(
          open: () => AppGraph.open(
            baseUrl: 'http://test',
            transportOverride: FakeTransport.routes({}),
            tokenStore: tokens,
            store: EncryptedFileStore(
              file: file,
              keys: FixedKeyProvider(currentKey),
            ),
            appLock: AppLock(tokens, iterations: 1000),
          ),
          wipe: () => resetLocalStore(
            file: file,
            deleteKey: () async => currentKey = keyOf(3),
            tokenStore: tokens,
          ),
        );
    return (boot: boot, tokens: tokens);
  }

  test('an undecryptable store yields BootFailed, never a memory graph',
      () async {
    final device = await restoredDevice();
    final outcome = await device.boot();

    expect(outcome, isA<BootFailed>());
    final failed = outcome as BootFailed;
    expect(failed.error, isA<StateError>());
    expect(failed.reset, isNotNull);
    // trying again changes nothing — still failed, file untouched
    expect(await failed.retry(), isA<BootFailed>());
    expect(file.existsSync(), isTrue);
  });

  testWidgets('recovery screen: cancel keeps the data, confirmed reset '
      'wipes it and starts at the online sign-in', (tester) async {
    final device = (await tester.runAsync(restoredDevice))!;
    final outcome = (await tester.runAsync(device.boot))!;

    await tester.pumpWidget(HmsRoot(initial: outcome));
    await tester.pumpAndSettle();

    expect(find.text('Offline data could not be unlocked'), findsOneWidget);
    expect(find.text('Reset local data (unsynced items will be lost)'),
        findsOneWidget);
    expect(find.byKey(const Key('queue-add')), findsNothing);
    expect(find.byKey(const Key('login-submit')), findsNothing);

    // first: cancel — nothing deleted
    await tester.tap(find.byKey(const Key('recovery-reset')));
    await tester.pumpAndSettle();
    expect(find.textContaining('cannot be recovered'), findsOneWidget);
    await tester.tap(find.byKey(const Key('recovery-reset-cancel')));
    await tester.pumpAndSettle();
    expect(file.existsSync(), isTrue);
    expect(find.text('Offline data could not be unlocked'), findsOneWidget);

    // then: confirm — file, key, session and PIN are gone; app starts
    await tester.tap(find.byKey(const Key('recovery-reset')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('recovery-reset-confirm')));
    await tester.pumpAndSettle();
    // let the real file I/O of the wipe + reopen complete
    for (var i = 0; i < 5 && file.existsSync(); i++) {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 50)));
      await tester.pump();
    }
    for (var i = 0; i < 5; i++) {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 20)));
      await tester.pumpAndSettle();
    }

    expect(file.existsSync(), isFalse);
    expect(find.byKey(const Key('login-submit')), findsOneWidget);
    expect(await Session(device.tokens).hasStoredSession(), isFalse);
    expect(await AppLock(device.tokens).hasPin(), isFalse);
  });
}
