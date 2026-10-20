/// The app's object graph: session + transport + client + **encrypted
/// local store** + directory cache + drafts + outbox + sync engine +
/// scheduler + network monitor + app lock.
///
/// Constructed once (see `boot.dart`) so screens and the sync engine always
/// see the same session, directory and outbox. On the device the store and
/// the session live in Android Keystore-backed storage, so an app restart
/// resumes exactly where it stopped (pending ops, cached directory, id map).
///
/// Start-up is deliberately light (low-cost phones): everything here is a
/// synchronous read of the already-decrypted document; no network call,
/// no timer and no isolate is started until a screen asks for one.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'api/client.dart';
import 'api/transport.dart';
import 'auth/app_lock.dart';
import 'auth/revocation.dart';
import 'auth/session.dart';
import 'data/directory.dart';
import 'data/draft_book.dart';
import 'data/rx_drafts.dart';
import 'data/stock_counts.dart';
import 'pdf/pdf_output.dart';
import 'scan/checkin.dart';
import 'scan/scanner.dart';
import 'screens/scan_screen.dart' show CameraCodeScanner;
import 'settings/app_settings.dart';
import 'store/local_store.dart';
import 'sync/engine.dart';
import 'sync/idmap.dart';
import 'sync/network.dart';
import 'sync/outbox.dart';
import 'sync/planner.dart';
import 'sync/scheduler.dart';
import 'sync/sync_status.dart';

class AppGraph {
  AppGraph({
    required this.baseUrl,
    TokenStore? tokenStore,
    ApiTransport? transportOverride,
    LocalStore? store,
    AppLock? appLock,
    bool autoSync = false,
    CodeScanner? scanner,
    PdfOutput? pdfOutput,
    NetworkMonitor? network,
  })  : store = store ?? MemoryLocalStore(),
        session = Session(tokenStore ?? MemoryTokenStore()),
        network = network ?? NetworkMonitor(),
        scanner = scanner ?? const CameraCodeScanner(),
        pdfOutput = pdfOutput ?? const PrintingPdfOutput() {
    transport = ReachabilityTransport(
      transportOverride ?? HttpTransport(baseUrl: baseUrl),
      this.network,
    );
    client = HmsClient(
      transport: transport,
      session: session,
      onUnauthorized: () => sessionExpired.value = true,
      onSessionEnded: _onSessionEnded,
    );
    this.appLock = appLock ?? AppLock(session.store);
    settings = AppSettings(this.store);
    directory = DirectoryCache(this.store)..load();
    drafts = RxDraftBook(this.store)..load();
    consults = DraftBook(this.store, 'consult_drafts')..load();
    appointments = DraftBook(this.store, 'appointment_drafts')..load();
    stock = StockCountBook(this.store)..load();
    quarantine = Quarantine(this.store);
    idMap = _readIdMap(this.store.doc);
    outbox = _readOutbox(this.store.doc);
    // Crash recovery (D14): an op persisted mid-push goes back to pending
    // with the same Idempotency-Key.
    final recovered = outbox.recoverInFlight();
    outbox.onChanged = _outboxChanged;
    if (recovered > 0) _outboxChanged();
    checkIn = OutboxCheckInClient(outbox);
    engine = SyncEngine(
      transport: transport,
      session: session,
      outbox: outbox,
      idMap: idMap,
      refresh: client.refresh,
      onAccessDenied: client.noteAccessDenied,
      onPersist: () async {
        await _persistOutbox();
        await this.store.saveSection('idmap', idMap.toJson());
      },
    );
    scheduler = SyncScheduler(
      engine: engine,
      outbox: outbox,
      enabled: autoSync,
      network: this.network,
      onResult: (result) {
        lastSync.value = result;
        if (result.stoppedUnauthorized && !deviceRevoked.value) {
          sessionExpired.value = true;
        }
        adoptSynced();
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
    CodeScanner? scanner,
    PdfOutput? pdfOutput,
    NetworkMonitor? network,
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
      scanner: scanner,
      pdfOutput: pdfOutput,
      network: network,
    );
    await graph.restoreSession();
    return graph;
  }

  final String baseUrl;
  final Session session;
  final LocalStore store;
  final NetworkMonitor network;
  final CodeScanner scanner;
  final PdfOutput pdfOutput;
  late final AppLock appLock;

  /// Language + Rural Clinic mode (kept across sign-out; no PHI).
  late final AppSettings settings;
  late final DirectoryCache directory;
  late final RxDraftBook drafts;
  late final DraftBook consults;
  late final DraftBook appointments;
  late final StockCountBook stock;
  late final Quarantine quarantine;
  late final IdMap idMap;
  late final Outbox outbox;
  late final ApiTransport transport;
  late final HmsClient client;
  late final SyncEngine engine;
  late final SyncScheduler scheduler;
  late final CheckInClient checkIn;

  /// Bumped on every outbox change (screens listen to refresh counts).
  final ValueNotifier<int> revision = ValueNotifier<int>(0);

  /// Result of the latest sync run (manual or automatic).
  final ValueNotifier<SyncResult?> lastSync = ValueNotifier<SyncResult?>(null);

  /// True when the server session is gone (refresh rejected): online-only
  /// actions need a new sign-in; offline work continues and is kept.
  final ValueNotifier<bool> sessionExpired = ValueNotifier<bool>(false);

  /// True after an administrator (or the user, from another device)
  /// revoked this device's session: PHI wiped, drafts quarantined, the
  /// app is back at the sign-in screen.
  final ValueNotifier<bool> deviceRevoked = ValueNotifier<bool>(false);

  /// True while the signed-in shell (PHI) is on screen — the lifecycle
  /// handler only locks / syncs then.
  bool shellActive = false;

  /// Last error while sealing the outbox to storage (D19), if any.
  final ValueNotifier<String?> persistError = ValueNotifier<String?>(null);

  Future<void>? _pendingPersist;

  /// Coalesced persistence: changes made in one event-loop turn produce
  /// ONE re-seal of the store. [flush] waits for it.
  void _outboxChanged() {
    revision.value += 1;
    if (_pendingPersist != null) return;
    final done = Completer<void>();
    _pendingPersist = done.future;
    scheduleMicrotask(() {
      _pendingPersist = null;
      _persistOutbox().then<void>(
        (_) {
          persistError.value = null;
          done.complete();
        },
        onError: (Object err) {
          persistError.value = err.toString();
          done.complete();
        },
      );
    });
  }

  Future<void> _persistOutbox() =>
      store.saveSection('outbox', jsonDecode(outbox.toJson()));

  /// Load the stored profile and stamp new ops with its user id.
  Future<SessionProfile?> restoreSession() async {
    final profile = await session.profile();
    outbox.ownerId = profile?.userId;
    deviceRevoked.value = quarantine.isActive &&
        !(await session.hasStoredSession());
    return profile;
  }

  /// After an online sign-in (password or MFA). The engine and scheduler
  /// resume; a quarantine owned by THIS user (same id and organisation) is
  /// released back into the live sections.
  Future<int> onSignedIn(SessionProfile? profile) async {
    outbox.ownerId = profile?.userId;
    sessionExpired.value = false;
    deviceRevoked.value = false;
    engine.resume();
    scheduler.start();
    final info = quarantine.info;
    if (info != null && info.ownedBy(profile?.userId, profile?.organizationId)) {
      return releaseQuarantine();
    }
    return 0;
  }

  /// Merge the latest server ids into every draft list.
  Future<void> adoptSynced() async {
    await drafts.adoptSynced(idMap);
    await consults.adoptSynced(idMap);
    await appointments.adoptSynced(idMap);
  }

  // --- device revocation --------------------------------------------------

  void _onSessionEnded(SessionEnd end) {
    if (end == SessionEnd.revoked) {
      handleRevocation();
    } else {
      sessionExpired.value = true;
    }
  }

  Future<void>? _revoking;

  /// Device revoked server-side (see `auth/revocation.dart`): stop syncing,
  /// move unsynced work into the sealed quarantine, wipe cached PHI, tokens
  /// and the PIN. Idempotent.
  Future<void> handleRevocation() => _revoking ??= _revoke().whenComplete(() {
        _revoking = null;
      });

  Future<void> _revoke() async {
    engine.halt();
    scheduler.stop();
    final profile = session.cachedProfile ?? await session.profile();
    final ops = outbox.takeAll();
    final localPatients = directory.localPatients;
    final rx = drafts.unsynced;
    final consultDrafts = consults.unsynced;
    final appointmentDrafts = appointments.unsynced;
    final counts = stock.unposted;
    final items = ops.length +
        rx.length +
        consultDrafts.length +
        appointmentDrafts.length +
        counts.length;
    if (items > 0 || quarantine.isActive) {
      await quarantine.seal(
        QuarantineInfo(
          userId: profile?.userId ?? outbox.ownerId ?? '',
          organizationId: profile?.organizationId ?? '',
          email: profile?.email ?? '',
          at: DateTime.now().toUtc(),
          items: items + (quarantine.info?.items ?? 0),
        ),
        {
          'ops': [for (final o in ops) o.toJson()],
          'patients': localPatients,
          'rx': rx,
          'consults': consultDrafts,
          'appointments': appointmentDrafts,
          'stock': counts,
        },
      );
    }
    // PHI the device may no longer show: cached server records, synced
    // drafts. The id map holds only opaque ids and is kept, so released
    // ops still resolve their parents.
    await directory.clear();
    await drafts.clear();
    await consults.clear();
    await appointments.clear();
    await stock.clear();
    // Tokens, profile and the PIN: the next person must sign in online.
    // (The quarantine keeps the owner's e-mail to pre-fill the form.)
    await session.clear();
    await appLock.clear();
    outbox.ownerId = null;
    sessionExpired.value = false;
    deviceRevoked.value = true;
    await flush();
  }

  /// Bring quarantined work back for its owner (after their sign-in).
  Future<int> releaseQuarantine() async {
    final content = await quarantine.release();
    List<Map<String, dynamic>> list(String key) =>
        DirectoryCache.listOf(content[key]);
    final ops = [for (final raw in list('ops')) OutboxOp.fromJson(raw)];
    for (final op in ops) {
      if (op.status == OpStatus.inFlight) {
        op.status = OpStatus.pending;
        op.everSent = true;
      }
    }
    outbox.adopt(ops);
    await directory.restoreLocalPatients(list('patients'));
    await drafts.restore(list('rx'));
    await consults.restore(list('consults'));
    await appointments.restore(list('appointments'));
    await stock.restore(list('stock'));
    await flush();
    return ops.length;
  }

  /// Explicit, confirmed discard of somebody else's quarantined work.
  Future<void> discardQuarantine() async {
    await quarantine.discard();
    await flush();
  }

  // --- status / storage ---------------------------------------------------

  /// Counts per [SyncStatus] for the queued ops right now.
  Map<SyncStatus, int> statusCounts() => countByStatus(
        outbox,
        SyncPlanner(outbox.ops, idMap),
        network: network.value,
      );

  SyncStatus globalSyncStatus() => globalStatus(
        counts: statusCounts(),
        network: network.value,
        running: engine.isRunning,
        lastRunClean: lastSync.value?.clean ?? false,
      );

  /// Approximate bytes per store section (JSON size before encryption).
  Map<String, int> storageUsage() {
    final out = <String, int>{};
    store.doc.forEach((k, v) => out[k] = utf8.encode(jsonEncode(v)).length);
    return out;
  }

  // --- sign-out -----------------------------------------------------------

  /// Sign out: revoke the server session (best effort) and wipe EVERYTHING
  /// this user left on the device — outbox, directory cache (PHI), id map,
  /// drafts, tokens, profile and PIN (audit H20 / D7). The caller must
  /// have obtained explicit confirmation when [Outbox.unsynced] > 0.
  Future<void> signOut() async {
    scheduler.stop();
    await client.logout();
    await wipeLocalData();
  }

  /// Delete all local offline data and credentials. Another user's sealed
  /// quarantine is NOT this user's to delete; it stays until its owner
  /// signs in or someone explicitly discards it.
  Future<void> wipeLocalData() async {
    outbox.clear();
    idMap.clear();
    await store.saveSection('idmap', null);
    await directory.clear();
    await drafts.clear();
    await consults.clear();
    await appointments.clear();
    await stock.clear();
    await session.clear();
    await appLock.clear();
    outbox.ownerId = null;
    lastSync.value = null;
    sessionExpired.value = false;
    await flush();
  }

  /// Wait until every queued local write has been sealed to storage —
  /// call before the app can be killed (backgrounding, tests, sign-out).
  Future<void> flush() async {
    final pending = _pendingPersist;
    if (pending != null) await pending;
    await store.flush();
  }

  static Outbox _readOutbox(Map<String, dynamic> doc) {
    final raw = doc['outbox'];
    return Outbox.fromJson(jsonEncode(raw is Map ? raw : const {'ops': []}));
  }

  static IdMap _readIdMap(Map<String, dynamic> doc) {
    final raw = doc['idmap'];
    return raw is Map<String, dynamic> ? IdMap.fromJson(raw) : IdMap();
  }
}
