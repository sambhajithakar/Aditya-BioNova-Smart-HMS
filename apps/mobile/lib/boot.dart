/// Start-up: open the encrypted offline store, or FAIL CLOSED.
///
/// Audit H23 / D3: the M4 build caught any decryption / Keystore error and
/// silently continued with an in-memory store — the user saw an empty app
/// and every new offline change was lost on the next kill. Now a failure
/// produces a [BootFailed] and the app shows the recovery screen, which
/// explains that the offline data could not be unlocked and offers an
/// explicit, confirmed "Reset local data (unsynced items will be lost)".
/// There is no memory-only mode on the device.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path_provider/path_provider.dart';

import 'app_graph.dart';
import 'auth/app_lock.dart';
import 'auth/session.dart';
import 'store/local_store.dart';
import 'store/platform_stores.dart';

sealed class BootOutcome {
  const BootOutcome();
}

class BootReady extends BootOutcome {
  const BootReady(this.graph);

  final AppGraph graph;
}

class BootFailed extends BootOutcome {
  const BootFailed({
    required this.error,
    required this.retry,
    this.reset,
  });

  /// What went wrong (shown in a "details" line for support).
  final Object error;

  /// Try to open the store again unchanged (e.g. Keystore was busy).
  final Future<BootOutcome> Function() retry;

  /// Delete the local offline data and start empty. Null when a reset
  /// cannot help (a build configuration error).
  final Future<BootOutcome> Function()? reset;
}

/// Try [open]; on any error return a [BootFailed] whose `reset` runs
/// [wipe] and tries again. Never substitutes a different store.
Future<BootOutcome> bootGraph({
  required Future<AppGraph> Function() open,
  required Future<void> Function() wipe,
}) async {
  try {
    return BootReady(await open());
  } catch (err) {
    return BootFailed(
      error: err,
      retry: () => bootGraph(open: open, wipe: wipe),
      reset: () async {
        try {
          await wipe();
        } catch (wipeErr) {
          return BootFailed(
            error: wipeErr,
            retry: () => bootGraph(open: open, wipe: wipe),
            reset: () => bootGraph(open: open, wipe: wipe),
          );
        }
        return bootGraph(open: open, wipe: wipe);
      },
    );
  }
}

/// API base for this build. Release builds must use HTTPS (the network
/// security config refuses cleartext anyway; this makes it explicit).
const String kApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://10.0.2.2:8000',
);

/// Device wiring: Keystore-backed session + AES-sealed offline store under
/// the app documents directory.
Future<BootOutcome> bootDevice() async {
  if (kReleaseMode && !kApiBase.startsWith('https://')) {
    final err = StateError(
      'This release build points at a non-HTTPS server ($kApiBase). '
      'Rebuild with --dart-define=API_BASE=https://…',
    );
    Future<BootOutcome> fail() async => BootFailed(error: err, retry: fail);
    return fail();
  }

  const storage = FlutterSecureStorage();
  final tokenStore = SecureTokenStore(storage: storage);

  Future<File> storeFile() async {
    final docs = await getApplicationDocumentsDirectory();
    return File('${docs.path}/hms_offline.json');
  }

  return bootGraph(
    open: () async => AppGraph.open(
      baseUrl: kApiBase,
      tokenStore: tokenStore,
      store: EncryptedFileStore(
        file: await storeFile(),
        keys: SecureKeyProvider(storage: storage),
      ),
      appLock: AppLock(tokenStore, useIsolate: true),
      autoSync: true,
    ),
    wipe: () async {
      final file = await storeFile();
      await resetLocalStore(
        file: file,
        deleteKey: () => storage.delete(key: SecureKeyProvider.keyName),
        tokenStore: tokenStore,
      );
    },
  );
}

/// Delete the sealed offline file (and its temp sibling), the store key,
/// and the session + PIN that belonged to it. The next open starts empty
/// with a fresh key; the user signs in again online.
Future<void> resetLocalStore({
  required File file,
  required Future<void> Function() deleteKey,
  required TokenStore tokenStore,
}) async {
  for (final f in [file, File('${file.path}.tmp')]) {
    if (await f.exists()) await f.delete();
  }
  await deleteKey();
  await Session(tokenStore).clear();
  await AppLock(tokenStore).clear();
}
