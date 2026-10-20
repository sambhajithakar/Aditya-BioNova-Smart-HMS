/// Role-aware, feature-aware home shell.
///
/// One binary serves both apps the blueprint asks for: the **Staff app**
/// (register → queue → billing) and the **Doctor app** (queue → Fast Rx),
/// switched by the role the server reports on `/auth/me`. Queue and Sync
/// are common to both.
///
/// Feature awareness: `/auth/me` may report `features: [feature_key]` and
/// `edition`. A tab whose feature is absent is hidden (Queue ← `opd_queue`,
/// Rx ← `consultation`, Billing ← `billing`; the dispense quantity field ←
/// `pharmacy`). Without `mobile_offline` only the Sync centre stays, so work
/// already saved on the device can still be sent. A server that does not
/// send `features` keeps every tab (backward compatible). The last reported
/// set is stored with the profile, so an offline start honours it.
///
/// Rural Clinic mode reuses the same tabs (no fork) in the four-step order
/// Register → Queue → Fast Rx → Bill; the Sync centre moves to the app bar.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../auth/features.dart';
import '../l10n/l10n.dart';
import 'billing_tab.dart';
import 'login_screen.dart';
import 'queue_tab.dart';
import 'register_tab.dart';
import 'rx_tab.dart';
import 'sync_tab.dart';
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

enum HomeTab { queue, register, rx, billing, sync }

/// Which tabs the shell shows, in order — pure, so it is unit-testable.
List<HomeTab> visibleTabs({
  required bool canPrescribe,
  required ServerFeatures features,
  required bool rural,
}) {
  if (!features.has(FeatureKeys.mobileOffline)) {
    return const [HomeTab.sync];
  }
  final queue = features.has(FeatureKeys.opdQueue);
  final rx = canPrescribe && features.has(FeatureKeys.consultation);
  final billing = features.has(FeatureKeys.billing);
  if (rural) {
    // Four steps; the Sync centre is an app-bar action.
    return [
      HomeTab.register,
      if (queue) HomeTab.queue,
      if (rx) HomeTab.rx,
      if (billing) HomeTab.billing,
    ];
  }
  return [
    if (queue) HomeTab.queue,
    HomeTab.register,
    if (rx) HomeTab.rx,
    if (billing) HomeTab.billing,
    HomeTab.sync,
  ];
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

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    graph.shellActive = true;
    _features =
        graph.session.cachedProfile?.serverFeatures ?? ServerFeatures.all;
    graph.settings.addListener(_changed);
    graph.revision.addListener(_changed);
    _loadRole();
  }

  @override
  void dispose() {
    graph.settings.removeListener(_changed);
    graph.revision.removeListener(_changed);
    graph.shellActive = false;
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  bool get _canPrescribe =>
      _role != null && kPrescribingRoles.contains(_role);

  Future<void> _loadRole() async {
    try {
      final me = await graph.client.me();
      final role = (me['role'] as String?) ?? 'member';
      final features = ServerFeatures.fromJson(me);
      final stored = await graph.session.profile();
      if (stored != null) {
        // Remember what the server reported for the next offline start.
        await graph.session.updateProfile(
            stored.withServerInfo(role: role, features: features));
      }
      if (!mounted) return;
      setState(() {
        _role = role;
        _features = features;
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

  /// Rural mode: the Sync centre opens as its own page.
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

  Widget _tabBody(HomeTab tab) => switch (tab) {
        HomeTab.queue => QueueTab(key: const ValueKey('tab-queue'), graph: graph),
        HomeTab.register =>
          RegisterTab(key: const ValueKey('tab-register'), graph: graph),
        HomeTab.rx => RxTab(
            key: const ValueKey('tab-rx'),
            graph: graph,
            showDispenseQuantity: _features.has(FeatureKeys.pharmacy),
          ),
        HomeTab.billing =>
          BillingTab(key: const ValueKey('tab-billing'), graph: graph),
        HomeTab.sync => SyncTab(key: const ValueKey('tab-sync'), graph: graph),
      };

  NavigationDestination _destination(HomeTab tab, bool rural) {
    final l = context.l10n;
    final (IconData icon, String label) = switch (tab) {
      HomeTab.queue => (Icons.queue_outlined, l.tabQueue),
      HomeTab.register => (Icons.person_add_outlined, l.tabRegister),
      HomeTab.rx => (Icons.medication_outlined, rural ? l.tabFastRx : l.tabRx),
      HomeTab.billing =>
        (Icons.receipt_long_outlined, rural ? l.tabBill : l.tabBilling),
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
    );
    final current =
        tabs.contains(_current) ? _current! : tabs.first;
    final index = tabs.indexOf(current);
    final unsynced = graph.outbox.unsynced;
    final mobileEnabled = _features.has(FeatureKeys.mobileOffline);

    return Scaffold(
      appBar: AppBar(
        title: Text(l.homeTitle(_role ?? '…')),
        actions: [
          if (rural && mobileEnabled)
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
            child: IndexedStack(
              index: index,
              children: [for (final tab in tabs) _tabBody(tab)],
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
