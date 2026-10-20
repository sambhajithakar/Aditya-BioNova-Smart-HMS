/// The app's object graph: session + transport + client + **encrypted
/// local store** + directory cache + outbox + sync engine + app lock.
///
/// Constructed once (see `boot.dart`) so screens and the sync engine always
/// see the same session, directory and outbox. On the device the store and
/// the session live in Android Keystore-backed storage, so an app restart
/// resumes exactly where it stopped (pending ops, cached directory, id map).
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'api/client.dart';
import 'api/transport.dart';
import 'auth/app_lock.dart';
import 'auth/session.dart';
import 'data/directory.dart';
import 'data/rx_drafts.dart';
import 'settings/app_settings.dart';
import 'store/local_store.dart';
import 'sync/engine.dart';
import 'sync/idmap.dart';
import 'sync/outbox.dart';
import 'sync/scheduler.dart';

class AppGraph {
  AppGraph({
    required this.baseUrl,
    TokenStore? tokenStore,
    ApiTransport? transportOverride,
    LocalStore? store,
    AppLock? appLock,
    bool autoSync = false,
  })  : store = store ?? MemoryLocalStore(),
        session = Session(tokenStore ?? MemoryTokenStore()) {
    transport = transportOverride ?? HttpTransport(baseUrl: baseUrl);
    client = HmsClient(
      transport: transport,
      session: session,
      onUnauthorized: () => sessionExpired.value = true,
    );
    this.appLock = appLock ?? AppLock(session.store);
    settings = AppSettings(this.store);
    directory = DirectoryCache(this.store)..load();
    drafts = RxDraftBook(this.store)..load();
    idMap = _readIdMap(this.store.doc);
    outbox = _readOutbox(this.store.doc);
    // Crash recovery (D14): an op persisted mid-push goes back to pending
    // with the same Idempotency-Key.
    final recovered = outbox.recoverInFlight();
    outbox.onChanged = _outboxChanged;
    if (recovered > 0) _outboxChanged();
    engine = SyncEngine(
      transport: transport,
      session: session,
      outbox: outbox,
      idMap: idMap,
      refresh: client.refresh,
      onPersist: () async {
        await _persistOutbox();
        await this.store.saveSection('idmap', idMap.toJson());
      },
    );
    scheduler = SyncScheduler(
      engine: engine,
      outbox: outbox,
      enabled: autoSync,
      onResult: (result) {
        lastSync.value = result;
        if (result.stoppedUnauthorized) sessionExpired.value = true;
        drafts.adoptSynced(idMap);
      },
    );
  }

  /// Open [store] (decrypting the offline document) and restore everything
  /// a restart must keep: pending ops, directory cache, id map, and who is
  /// signed in. Throws when the store cannot be unlocked — the caller must
  /// show the recovery screen, never fall back to a memory-only store.
  static Future<AppGraph> open({
    required String baseUrl,
    TokenStore? tokenStore,
    ApiTransport? transportOverride,
    LocalStore? store,
    AppLock? appLock,
    bool autoSync = false,
  }) async {
    final resolved = store ?? MemoryLocalStore();
    await resolved.open();
    final graph = AppGraph(
      baseUrl: baseUrl,
      tokenStore: tokenStore,
      transportOverride: transportOverride,
      store: resolved,
      appLock: appLock,
      autoSync: autoSync,
    );
    await graph.restoreSession();
    return graph;
  }

  final String baseUrl;
  final Session session;
  final LocalStore store;
  late final AppLock appLock;

  /// Language + Rural Clinic mode (kept across sign-out; no PHI).
  late final AppSettings settings;
  late final DirectoryCache directory;
  late final RxDraftBook drafts;
  late final IdMap idMap;
  late final Outbox outbox;
  late final ApiTransport transport;
  late final HmsClient client;
  late final SyncEngine engine;
  late final SyncScheduler scheduler;

  /// Bumped on every outbox change (screens listen to refresh counts).
  final ValueNotifier<int> revision = ValueNotifier<int>(0);

  /// Result of the latest sync run (manual or automatic).
  final ValueNotifier<SyncResult?> lastSync = ValueNotifier<SyncResult?>(null);

  /// True when the server session is gone (refresh rejected): online-only
  /// actions need a new sign-in; offline work continues and is kept.
  final ValueNotifier<bool> sessionExpired = ValueNotifier<bool>(false);

  /// True while the signed-in shell (PHI) is on screen — the lifecycle
  /// handler only locks / syncs then.
  bool shellActive = false;

  /// Last error while sealing the outbox to storage (D19), if any.
  final ValueNotifier<String?> persistError = ValueNotifier<String?>(null);

  void _outboxChanged() {
    revision.value += 1;
    _persistOutbox().then<void>(
      (_) {
        persistError.value = null;
      },
      onError: (Object err) {
        persistError.value = err.toString();
      },
    );
  }

  Future<void> _persistOutbox() =>
      store.saveSection('outbox', jsonDecode(outbox.toJson()));

  /// Load the stored profile and stamp new ops with its user id.
  Future<SessionProfile?> restoreSession() async {
    final profile = await session.profile();
    outbox.ownerId = profile?.userId;
    return profile;
  }

  /// After an online sign-in (password or MFA).
  Future<void> onSignedIn(SessionProfile? profile) async {
    outbox.ownerId = profile?.userId;
    sessionExpired.value = false;
  }

  /// Sign out: revoke the server session (best effort) and wipe EVERYTHING
  /// this user left on the device — outbox, directory cache (PHI), id map,
  /// Rx drafts, tokens, profile and PIN (audit H20 / D7). The caller must
  /// have obtained explicit confirmation when [Outbox.unsynced] > 0.
  Future<void> signOut() async {
    scheduler.stop();
    await client.logout();
    await wipeLocalData();
  }

  /// Delete all local offline data and credentials.
  Future<void> wipeLocalData() async {
    outbox.clear();
    idMap.clear();
    await store.saveSection('idmap', null);
    await directory.clear();
    await drafts.clear();
    await session.clear();
    await appLock.clear();
    outbox.ownerId = null;
    lastSync.value = null;
    sessionExpired.value = false;
    await flush();
  }

  /// Wait until every queued local write has been sealed to storage —
  /// call before the app can be killed (backgrounding, tests, sign-out).
  Future<void> flush() => store.flush();

  static Outbox _readOutbox(Map<String, dynamic> doc) {
    final raw = doc['outbox'];
    return Outbox.fromJson(jsonEncode(raw is Map ? raw : const {'ops': []}));
  }

  static IdMap _readIdMap(Map<String, dynamic> doc) {
    final raw = doc['idmap'];
    return raw is Map<String, dynamic> ? IdMap.fromJson(raw) : IdMap();
  }
}
