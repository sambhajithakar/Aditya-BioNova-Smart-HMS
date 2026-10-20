/// Role-aware, feature-aware home shell.
///
/// One binary, four interfaces (see `auth/roles.dart`), chosen from the
/// role `/auth/me` reports (stored with the profile, so an offline start
/// gets the same interface):
/// * **Doctor** — Queue · Consult · Rx · Patients · Sync;
/// * **Reception / staff** — Queue · Register · Appointments · Billing · Sync;
/// * **Hospital administrator** — Overview (today's server reports + sync
///   health) · Queue · Register · (Rx) · Billing · Sync;
/// * **Pharmacy** — Stock (count drafts, barcode scan) · Patients · Sync;
/// * **Rural Clinic mode** (device setting, any role) — the four-step
///   Register → Queue → Fast Rx → Bill with the Sync centre in the app bar.
///
/// Feature awareness: a tab whose server feature is absent is hidden
/// (Queue ← `opd_queue`, Consult / Rx ← `consultation`, Billing ←
/// `billing`, Stock ← `pharmacy`). Without `mobile_offline` only the Sync
/// centre stays. When the server reports `permissions`, a tab whose
/// permission is missing is hidden too. Hiding is a convenience; the API
/// authorises every request.
///
/// Low-cost phones: a tab is built the first time it is opened (not all at
/// start-up) and kept alive afterwards; the global sync bar rebuilds alone.
///
/// Device revocation: when the server revokes this device's session the
/// shell is replaced by the sign-in screen with "This device was signed out
/// by an administrator".
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../auth/features.dart';
import '../auth/roles.dart';
import '../l10n/l10n.dart';
import 'appointments_tab.dart';
import 'billing_tab.dart';
import 'consult_tab.dart';
import 'login_screen.dart';
import 'overview_tab.dart';
import 'patients_tab.dart';
import 'queue_tab.dart';
import 'register_tab.dart';
import 'rx_tab.dart';
import 'stock_tab.dart';
import 'sync_tab.dart';
import 'sync_widgets.dart';
import 'widgets.dart';

/// Roles allowed to write prescriptions (mirrors `prescription.sign` /
/// `prescription.write` on the server).
const Set<String> kPrescribingRoles = {'doctor', 'owner', 'admin'};

/// Replace the whole stack with the signed-in shell.
void openHome(BuildContext context, AppGraph graph) {
  Navigator.of(context).pushAndRemoveUntil(
    MaterialPageRoute<void>(builder: (_) => HomeScreen(graph: graph)),
    (_) => false,
  );
}

enum HomeTab {
  overview,
  queue,
  register,
  appointments,
  consult,
  rx,
  patients,
  billing,
  stock,
  sync,
}

/// Which tabs the shell shows, in order — pure, so it is unit-testable.
///
/// [role] null = the legacy all-in-one clinic layout (kept for callers that
/// do not know the role yet).
List<HomeTab> visibleTabs({
  required bool canPrescribe,
  required ServerFeatures features,
  required bool rural,
  String? role,
  Permissions permissions = Permissions.unknown,
}) {
  if (!features.has(FeatureKeys.mobileOffline)) {
    return const [HomeTab.sync];
  }
  final queue = features.has(FeatureKeys.opdQueue) &&
      permissions.any(TabPermissions.queue);
  final consultation = features.has(FeatureKeys.consultation);
  final rx = canPrescribe && consultation && permissions.any(TabPermissions.rx);
  final billing =
      features.has(FeatureKeys.billing) && permissions.any(TabPermissions.billing);
  final register = permissions.any(TabPermissions.register);
  if (rural) {
    // Four steps; the Sync centre is an app-bar action.
    return [
      if (register) HomeTab.register,
      if (queue) HomeTab.queue,
      if (rx) HomeTab.rx,
      if (billing) HomeTab.billing,
    ];
  }
  if (role == null) {
    return [
      if (queue) HomeTab.queue,
      if (register) HomeTab.register,
      if (rx) HomeTab.rx,
      if (billing) HomeTab.billing,
      HomeTab.sync,
    ];
  }
  final consult = consultation && permissions.any(TabPermissions.consult);
  final patients = permissions.any(TabPermissions.patients);
  return switch (roleInterfaceOf(role)) {
    RoleInterface.doctor => [
        if (queue) HomeTab.queue,
        if (consult) HomeTab.consult,
        if (rx) HomeTab.rx,
        if (patients) HomeTab.patients,
        HomeTab.sync,
      ],
    RoleInterface.reception => [
        if (queue) HomeTab.queue,
        if (register) HomeTab.register,
        if (permissions.any(TabPermissions.appointments)) HomeTab.appointments,
        if (billing) HomeTab.billing,
        HomeTab.sync,
      ],
    RoleInterface.administrator => [
        if (permissions.any(TabPermissions.overview)) HomeTab.overview,
        if (queue) HomeTab.queue,
        if (register) HomeTab.register,
        if (rx) HomeTab.rx,
        if (billing) HomeTab.billing,
        HomeTab.sync,
      ],
    RoleInterface.pharmacy => [
        if (features.has(FeatureKeys.pharmacy) &&
            permissions.any(TabPermissions.stock))
          HomeTab.stock,
        if (patients) HomeTab.patients,
        HomeTab.sync,
      ],
  };
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  HomeTab? _current;
  String? _role;
  late ServerFeatures _features;
  late Permissions _permissions;

  /// Tabs opened at least once (built lazily, then kept alive).
  final Set<HomeTab> _opened = <HomeTab>{};

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    graph.shellActive = true;
    final stored = graph.session.cachedProfile;
    _features = stored?.serverFeatures ?? ServerFeatures.all;
    _permissions = stored?.serverPermissions ?? Permissions.unknown;
    graph.settings.addListener(_changed);
    graph.revision.addListener(_changed);
    graph.deviceRevoked.addListener(_revoked);
    _loadRole();
  }

  @override
  void dispose() {
    graph.settings.removeListener(_changed);
    graph.revision.removeListener(_changed);
    graph.deviceRevoked.removeListener(_revoked);
    graph.shellActive = false;
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  void _revoked() {
    if (!mounted || !graph.deviceRevoked.value) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (ctx) => LoginScreen(
          graph: graph,
          notice: ctx.l10n.deviceSignedOutByAdmin,
        ),
      ),
      (_) => false,
    );
  }

  bool get _canPrescribe =>
      _role != null && kPrescribingRoles.contains(_role);

  Future<void> _loadRole() async {
    try {
      final me = await graph.client.me();
      final role = (me['role'] as String?) ?? 'member';
      final features = ServerFeatures.fromJson(me);
      final permissions = Permissions.fromJson(me);
      final stored = await graph.session.profile();
      if (stored != null) {
        // Remember what the server reported for the next offline start.
        await graph.session.updateProfile(stored.withServerInfo(
            role: role, features: features, permissions: permissions));
      }
      if (!mounted) return;
      setState(() {
        _role = role;
        _features = features;
        _permissions = permissions;
      });
    } catch (_) {
      // Offline: the shell still works with the role (and feature set)
      // stored at the last sign-in / online start.
      final stored = await graph.session.profile();
      if (!mounted) return;
      setState(() {
        final role = stored?.role ?? '';
        _role = role.isNotEmpty ? role : 'offline';
        _features = stored?.serverFeatures ?? ServerFeatures.all;
        _permissions = stored?.serverPermissions ?? Permissions.unknown;
      });
    }
  }

  /// Sign-out wipes this user's data from the device (H20). Unsynced work
  /// would be lost, so that needs an explicit confirmation.
  Future<void> _signOut() async {
    final unsynced = graph.outbox.unsynced;
    final l = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(unsynced > 0 ? l.signOutTitleUnsynced : l.signOutTitle),
        content: Text(
            unsynced > 0 ? l.signOutBodyUnsynced(unsynced) : l.signOutBody),
        actions: [
          TextButton(
            key: const Key('sign-out-cancel'),
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(l.cancel),
          ),
          FilledButton(
            key: const Key('sign-out-confirm'),
            style: unsynced > 0
                ? FilledButton.styleFrom(
                    backgroundColor: Theme.of(ctx).colorScheme.error)
                : null,
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(unsynced > 0 ? l.signOutDelete : l.signOut),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await graph.signOut();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => LoginScreen(graph: graph)),
      (_) => false,
    );
  }

  void _signInAgain() {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (_) => LoginScreen(
          graph: graph,
          notice: context.l10n.sessionExpiredNotice,
        ),
      ),
      (_) => false,
    );
  }

  /// Rural mode (or a tab-less layout): the Sync centre as its own page.
  void _openSyncCentre() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (ctx) => Scaffold(
          appBar: AppBar(title: Text(ctx.l10n.tabSync)),
          body: SyncTab(graph: graph),
        ),
      ),
    );
  }

  void _openReports() {
    Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => ReportsScreen(graph: graph)));
  }

  Widget _tabBody(HomeTab tab) => switch (tab) {
        HomeTab.overview =>
          OverviewTab(key: const ValueKey('tab-overview'), graph: graph),
        HomeTab.queue => QueueTab(
            key: const ValueKey('tab-queue'),
            graph: graph,
            checkIn: _features.hasExplicit(FeatureKeys.qrCheckin),
          ),
        HomeTab.register =>
          RegisterTab(key: const ValueKey('tab-register'), graph: graph),
        HomeTab.appointments => AppointmentsTab(
            key: const ValueKey('tab-appointments'), graph: graph),
        HomeTab.consult =>
          ConsultTab(key: const ValueKey('tab-consult'), graph: graph),
        HomeTab.rx => RxTab(
            key: const ValueKey('tab-rx'),
            graph: graph,
            showDispenseQuantity: _features.has(FeatureKeys.pharmacy),
          ),
        HomeTab.patients =>
          PatientsTab(key: const ValueKey('tab-patients'), graph: graph),
        HomeTab.billing =>
          BillingTab(key: const ValueKey('tab-billing'), graph: graph),
        HomeTab.stock => StockTab(key: const ValueKey('tab-stock'), graph: graph),
        HomeTab.sync => SyncTab(key: const ValueKey('tab-sync'), graph: graph),
      };

  NavigationDestination _destination(HomeTab tab, bool rural) {
    final l = context.l10n;
    final (IconData icon, String label) = switch (tab) {
      HomeTab.overview => (Icons.insights_outlined, l.tabOverview),
      HomeTab.queue => (Icons.queue_outlined, l.tabQueue),
      HomeTab.register => (Icons.person_add_outlined, l.tabRegister),
      HomeTab.appointments => (Icons.event_outlined, l.tabAppointments),
      HomeTab.consult => (Icons.edit_note_outlined, l.tabConsult),
      HomeTab.rx => (Icons.medication_outlined, rural ? l.tabFastRx : l.tabRx),
      HomeTab.patients => (Icons.people_outline, l.tabPatients),
      HomeTab.billing =>
        (Icons.receipt_long_outlined, rural ? l.tabBill : l.tabBilling),
      HomeTab.stock => (Icons.inventory_2_outlined, l.tabStock),
      HomeTab.sync => (Icons.sync_outlined, l.tabSync),
    };
    return NavigationDestination(
      key: Key('nav-${tab.name}'),
      icon: Icon(icon),
      label: label,
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final settings = graph.settings;
    final rural = settings.ruralMode;
    final tabs = visibleTabs(
      canPrescribe: _canPrescribe,
      features: _features,
      rural: rural,
      role: _role,
      permissions: _permissions,
    );
    final current = tabs.isEmpty
        ? null
        : (tabs.contains(_current) ? _current! : tabs.first);
    if (current != null) _opened.add(current);
    final index = current == null ? 0 : tabs.indexOf(current);
    final unsynced = graph.outbox.unsynced;
    final mobileEnabled = _features.has(FeatureKeys.mobileOffline);
    final syncInBar = !tabs.contains(HomeTab.sync);

    return Scaffold(
      appBar: AppBar(
        title: Text(l.homeTitle(_role ?? '…')),
        actions: [
          if (syncInBar && mobileEnabled)
            IconButton(
              key: const Key('rural-sync'),
              tooltip: l.tabSync,
              onPressed: _openSyncCentre,
              icon: Badge(
                isLabelVisible: unsynced > 0,
                label: Text('$unsynced'),
                child: const Icon(Icons.sync_outlined),
              ),
            ),
          LanguageMenuButton(settings: settings),
          PopupMenuButton<String>(
            key: const Key('settings-menu'),
            tooltip: l.settingsMenu,
            onSelected: (value) {
              if (value == 'rural') settings.setRuralMode(!rural);
              if (value == 'reports') _openReports();
            },
            itemBuilder: (_) => [
              CheckedPopupMenuItem<String>(
                key: const Key('rural-toggle'),
                value: 'rural',
                checked: rural,
                child: ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(l.ruralMode),
                  subtitle: Text(l.ruralModeHelp),
                ),
              ),
              if (_permissions.any(TabPermissions.overview))
                PopupMenuItem<String>(
                  key: const Key('menu-reports'),
                  value: 'reports',
                  child: Text(l.reportsTitle),
                ),
              if (_features.edition != null)
                PopupMenuItem<String>(
                  key: const Key('edition-label'),
                  enabled: false,
                  child: Text(l.editionLabel(_features.edition!)),
                ),
            ],
          ),
          IconButton(
            key: const Key('sign-out'),
            tooltip: l.signOut,
            icon: const Icon(Icons.logout),
            onPressed: () => _signOut(),
          ),
        ],
      ),
      body: Column(
        children: [
          GlobalSyncBar(
            graph: graph,
            onTap: tabs.contains(HomeTab.sync)
                ? () => setState(() => _current = HomeTab.sync)
                : _openSyncCentre,
          ),
          ValueListenableBuilder<bool>(
            valueListenable: graph.sessionExpired,
            builder: (context, expired, _) => !expired
                ? const SizedBox.shrink()
                : MaterialBanner(
                    key: const Key('session-expired'),
                    content: Text(l.sessionExpiredBanner),
                    actions: [
                      TextButton(
                        onPressed: _signInAgain,
                        child: Text(l.loginSubmit),
                      ),
                    ],
                  ),
          ),
          if (!mobileEnabled)
            MaterialBanner(
              key: const Key('mobile-not-enabled'),
              content: Text(l.mobileNotEnabled),
              actions: const [SizedBox.shrink()],
            ),
          Expanded(
            child: tabs.isEmpty
                ? Center(child: Text(l.noTabsForRole))
                : IndexedStack(
                    index: index,
                    children: [
                      for (final tab in tabs)
                        _opened.contains(tab)
                            ? _tabBody(tab)
                            : const SizedBox.shrink(),
                    ],
                  ),
          ),
        ],
      ),
      // A NavigationBar needs two or more destinations.
      bottomNavigationBar: tabs.length < 2
          ? null
          : NavigationBar(
              selectedIndex: index,
              onDestinationSelected: (i) => setState(() => _current = tabs[i]),
              destinations: [for (final tab in tabs) _destination(tab, rural)],
            ),
    );
  }
}
