/// Sync status model, device revocation (wipe + quarantine + same-user
/// release) and role interfaces.
library;

import 'package:aditya_bionova_mobile/api/client.dart';
import 'package:aditya_bionova_mobile/api/transport.dart';
import 'package:aditya_bionova_mobile/auth/app_lock.dart';
import 'package:aditya_bionova_mobile/auth/features.dart';
import 'package:aditya_bionova_mobile/auth/revocation.dart';
import 'package:aditya_bionova_mobile/auth/roles.dart';
import 'package:aditya_bionova_mobile/auth/session.dart';
import 'package:aditya_bionova_mobile/main.dart';
import 'package:aditya_bionova_mobile/screens/home_screen.dart';
import 'package:aditya_bionova_mobile/store/local_store.dart';
import 'package:aditya_bionova_mobile/sync/network.dart';
import 'package:aditya_bionova_mobile/sync/outbox.dart';
import 'package:aditya_bionova_mobile/sync/planner.dart';
import 'package:aditya_bionova_mobile/sync/idmap.dart';
import 'package:aditya_bionova_mobile/sync/sync_status.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Map<String, dynamic> seed() => {
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
    };

Future<(AppGraph, MemoryTokenStore)> boot(ApiTransport t,
    {String userId = 'u1', String org = 'o1', String role = 'doctor'}) async {
  final tokens = MemoryTokenStore();
  final graph = await AppGraph.open(
    baseUrl: 'http://test',
    transportOverride: t,
    tokenStore: tokens,
    store: MemoryLocalStore(seed()),
    appLock: AppLock(tokens, iterations: 1000),
  );
  await graph.session.save(
    accessToken: 'tok',
    refreshToken: 'r',
    profile: SessionProfile(
        userId: userId, organizationId: org, email: 'u@clinic.test', role: role),
  );
  await graph.restoreSession();
  await graph.appLock.setPin('2468');
  return (graph, tokens);
}

/// Server that has revoked this device's session.
FakeTransport revokedServer() => FakeTransport((c) async {
      if (c.route == 'POST /auth/refresh') {
        return json({'detail': 'Invalid credentials'}, status: 401);
      }
      return json({'detail': 'Session is no longer valid'}, status: 401);
    });

void main() {
  group('sync status model', () {
    final online = const NetworkState(reachability: Reachability.online);
    final offline = const NetworkState(reachability: Reachability.offline);

    test('per record', () {
      final outbox = Outbox();
      final op = outbox.enqueue(
          entity: 'patient',
          method: 'POST',
          path: '/patients',
          payload: {},
          dedupeKey: 'a',
          localRef: 'p');
      expect(statusOfOp(op, network: offline), SyncStatus.savedOnDevice);
      expect(statusOfOp(op, network: online), SyncStatus.pendingSync);
      op.status = OpStatus.inFlight;
      expect(statusOfOp(op, network: online), SyncStatus.syncing);
      op
        ..status = OpStatus.conflicted
        ..conflictReason = ConflictReason.duplicatePatient;
      expect(statusOfOp(op, network: online), SyncStatus.conflict);
      op.conflictReason = ConflictReason.rejectedByPolicy;
      expect(statusOfOp(op, network: online), SyncStatus.actionRequired);
      op.conflictReason = ConflictReason.maxAttempts;
      expect(statusOfOp(op, network: online), SyncStatus.actionRequired);

      // a child of a parked parent is Action required too
      final child = outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': IdMap.placeholder('p')},
          dedupeKey: 'b');
      final planner = SyncPlanner(outbox.ops, IdMap());
      expect(
          statusOfOp(child,
              network: online, dependency: planner.infoFor(child)),
          SyncStatus.actionRequired);
    });

    test('global precedence', () {
      Map<SyncStatus, int> c(Map<SyncStatus, int> m) =>
          {for (final s in SyncStatus.values) s: m[s] ?? 0};
      expect(
          globalStatus(
              counts: c({}), network: online, running: true, lastRunClean: true),
          SyncStatus.syncing);
      expect(
          globalStatus(
              counts: c({SyncStatus.conflict: 1, SyncStatus.actionRequired: 1}),
              network: offline,
              running: false,
              lastRunClean: false),
          SyncStatus.conflict);
      expect(
          globalStatus(
              counts: c({SyncStatus.savedOnDevice: 2}),
              network: offline,
              running: false,
              lastRunClean: false),
          SyncStatus.offline);
      expect(
          globalStatus(
              counts: c({SyncStatus.pendingSync: 2}),
              network: online,
              running: false,
              lastRunClean: false),
          SyncStatus.pendingSync);
      expect(
          globalStatus(
              counts: c({}), network: online, running: false, lastRunClean: true),
          SyncStatus.synced);
      expect(
          globalStatus(
              counts: c({}), network: online, running: false, lastRunClean: false),
          SyncStatus.online);
    });
  });

  group('session end classification', () {
    test('revoked vs expired', () {
      expect(
          classifySessionEnd(
              lastAccessDenial: 'Session is no longer valid', refreshStatus: 401),
          SessionEnd.revoked);
      expect(
          classifySessionEnd(
              refreshStatus: 403, refreshDetail: 'Membership is not active'),
          SessionEnd.revoked);
      expect(
          classifySessionEnd(
              lastAccessDenial: 'Invalid or expired token', refreshStatus: 401),
          SessionEnd.expired);
      expect(classifySessionEnd(refreshStatus: 401), SessionEnd.expired);
    });

    test('client reports revoked through onSessionEnded', () async {
      final session = Session(MemoryTokenStore());
      await session.save(accessToken: 'a', refreshToken: 'r');
      SessionEnd? ended;
      final client = HmsClient(
        transport: revokedServer(),
        session: session,
        onSessionEnded: (e) => ended = e,
      );
      final res = await client.sendRaw('GET', '/auth/me');
      expect(res.status, 401);
      expect(ended, SessionEnd.revoked);
      expect(await session.refreshToken(), isNull);
    });

    test('a plain expiry keeps the M7.0 behaviour (expired, nothing wiped)',
        () async {
      final fake = FakeTransport((c) async => c.route == 'POST /auth/refresh'
          ? json({'detail': 'Invalid credentials'}, status: 401)
          : json({'detail': 'Invalid or expired token'}, status: 401));
      final (graph, _) = await boot(fake);
      graph.outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': 'p1', 'branch_id': 'b1'},
          dedupeKey: 'q');
      await graph.engine.sync();
      expect(graph.deviceRevoked.value, isFalse);
      expect(graph.outbox.total, 1);
      expect(graph.directory.patients, isNotEmpty);
    });
  });

  group('device revocation', () {
    test('sync hitting a revoked session: stop, wipe PHI/tokens/PIN, seal '
        'unsynced work; same user signs in → released with the same keys',
        () async {
      final (graph, _) = await boot(revokedServer());
      await graph.directory.addLocalPatient(
          localRef: 'loc1', fullName: 'Sunita Patil', gender: 'female');
      final reg = graph.outbox.enqueue(
          entity: 'patient',
          method: 'POST',
          path: '/patients',
          payload: {'full_name': 'Sunita Patil', 'gender': 'female'},
          dedupeKey: 'p',
          localRef: 'loc1');
      await graph.drafts.addDraft(
          localRef: 'rx1',
          patientRef: r'$ref:loc1',
          patientLabel: 'Sunita Patil',
          diagnosis: 'Fever',
          items: const []);

      await graph.engine.sync();
      await graph.flush();

      expect(graph.deviceRevoked.value, isTrue);
      expect(graph.engine.isHalted, isTrue);
      expect(graph.outbox.total, 0, reason: 'nothing left in the live queue');
      expect(graph.directory.patients, isEmpty, reason: 'PHI cache wiped');
      expect(graph.drafts.drafts, isEmpty);
      expect(await graph.session.accessToken(), isNull);
      expect(await graph.session.refreshToken(), isNull);
      expect(await graph.appLock.hasPin(), isFalse);
      final info = graph.quarantine.info!;
      expect(info.userId, 'u1');
      expect(info.items, 2);
      // nothing more is sent
      final calls = (graph.transport as ReachabilityTransport).inner
          as FakeTransport;
      final before = calls.calls.length;
      await graph.scheduler.requestSync(force: true);
      expect(calls.calls.length, before);

      // a different user signs in: nothing released
      await graph.onSignedIn(
          const SessionProfile(userId: 'u2', organizationId: 'o1'));
      expect(graph.outbox.total, 0);
      expect(graph.quarantine.isActive, isTrue);

      // the owner signs in again: everything is back, same idempotency key
      final released = await graph.onSignedIn(
          const SessionProfile(userId: 'u1', organizationId: 'o1'));
      expect(released, 1);
      expect(graph.outbox.ops.single.id, reg.id);
      expect(graph.directory.patientById('loc1'), isNotNull);
      expect(graph.drafts.drafts.single['localRef'], 'rx1');
      expect(graph.quarantine.isActive, isFalse);
      expect(graph.engine.isHalted, isFalse);
    });

    test('another user may explicitly discard the sealed items', () async {
      final (graph, _) = await boot(revokedServer());
      graph.outbox.enqueue(
          entity: 'queue_entry',
          method: 'POST',
          path: '/opd/queue',
          payload: {'patient_id': 'p1', 'branch_id': 'b1'},
          dedupeKey: 'q');
      await graph.handleRevocation();
      await graph.onSignedIn(const SessionProfile(userId: 'u2'));
      expect(graph.quarantine.isActive, isTrue);
      await graph.discardQuarantine();
      expect(graph.quarantine.isActive, isFalse);
      expect(graph.store.doc['quarantine'], isNull);
    });

    testWidgets('the home shell is replaced by the sign-in screen saying '
        'the device was signed out by an administrator', (tester) async {
      final (graph, _) = await boot(revokedServer());
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('login-submit')), findsOneWidget);
      expect(find.textContaining('signed out by an administrator'),
          findsOneWidget);
      expect(find.text('Aarti Patil'), findsNothing);
    });
  });

  group('role interfaces', () {
    List<HomeTab> tabs(String role,
            {ServerFeatures f = ServerFeatures.all,
            Permissions p = Permissions.unknown,
            bool rural = false}) =>
        visibleTabs(
          canPrescribe: kPrescribingRoles.contains(role),
          features: f,
          rural: rural,
          role: role,
          permissions: p,
        );

    test('doctor / reception / administrator / pharmacy / rural', () {
      expect(tabs('doctor'), [
        HomeTab.queue,
        HomeTab.consult,
        HomeTab.rx,
        HomeTab.patients,
        HomeTab.sync
      ]);
      expect(tabs('receptionist'), [
        HomeTab.queue,
        HomeTab.register,
        HomeTab.appointments,
        HomeTab.billing,
        HomeTab.sync
      ]);
      expect(tabs('nurse'), tabs('receptionist'));
      expect(tabs('owner'), [
        HomeTab.overview,
        HomeTab.queue,
        HomeTab.register,
        HomeTab.rx,
        HomeTab.billing,
        HomeTab.sync
      ]);
      expect(tabs('pharmacist'),
          [HomeTab.stock, HomeTab.patients, HomeTab.sync]);
      expect(tabs('doctor', rural: true),
          [HomeTab.register, HomeTab.queue, HomeTab.rx, HomeTab.billing]);
    });

    test('reported permissions hide tabs the user cannot use', () {
      const p = Permissions({'queue.read', 'patient.read'});
      expect(tabs('doctor', p: p),
          [HomeTab.queue, HomeTab.patients, HomeTab.sync]);
      expect(tabs('owner', p: const Permissions({'billing.invoice'})),
          [HomeTab.billing, HomeTab.sync]);
      expect(Permissions.fromJson({'permissions': <String>[]}).keys, isNull,
          reason: 'an empty list is treated as "not reported"');
    });

    testWidgets('receptionist home: Queue, Register, Appointments, Billing, '
        'Sync and a global sync status bar', (tester) async {
      final (graph, _) = await boot(
          FakeTransport.routes({'GET /auth/me': json({'role': 'receptionist'})}),
          role: 'receptionist');
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      final labels = tester
          .widgetList<NavigationDestination>(find.byType(NavigationDestination))
          .map((d) => d.label)
          .toList();
      expect(labels, ['Queue', 'Register', 'Appointments', 'Billing', 'Sync']);
      expect(find.byKey(const Key('global-sync-bar')), findsOneWidget);

      await tester.tap(find.text('Appointments'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('appt-save')));
      await tester.pump();
      expect(graph.outbox.ops.single.entity, 'appointment');
      expect(graph.outbox.ops.single.path, '/appointments');
      expect(find.byKey(const Key('needs-connection')), findsOneWidget,
          reason: "today's list is online-only");
    });

    testWidgets('administrator overview: today from the report endpoint; '
        'offline it says Needs connection', (tester) async {
      final (graph, _) = await boot(
          FakeTransport.routes({
            'GET /auth/me': json({'role': 'owner'}),
            'GET /reports/summary': json({
              'from_date': '2026-10-20',
              'to_date': '2026-10-20',
              'finance': {'revenue': 1500, 'refunds': 100, 'net': 1400},
              'ipd': {'currently_admitted': 3},
              'inventory': {
                'low_stock': [{}, {}]
              },
            }),
            'GET /appointments': json({'items': [], 'total': 7}),
          }),
          role: 'owner');
      await tester.pumpWidget(MaterialApp(home: HomeScreen(graph: graph)));
      await tester.pumpAndSettle();
      expect(find.text('Overview'), findsOneWidget);
      expect(find.text('₹1500.00'), findsOneWidget);
      expect(find.text('7'), findsOneWidget);
      expect(find.byKey(const Key('sync-health')), findsOneWidget);

      final (offline, _) = await boot(
          FakeTransport((c) async => throw Exception('no network')),
          role: 'owner');
      await tester.pumpWidget(
          MaterialApp(key: UniqueKey(), home: HomeScreen(graph: offline)));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('needs-connection')), findsOneWidget);
    });
  });
}
