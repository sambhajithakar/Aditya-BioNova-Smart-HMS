/// Role-aware home shell.
///
/// One binary serves both apps the blueprint asks for: the **Staff app**
/// (register → queue → billing) and the **Doctor app** (queue → Fast Rx),
/// switched by the role the server reports on `/auth/me`. Queue and Sync
/// are common to both.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import 'billing_tab.dart';
import 'login_screen.dart';
import 'queue_tab.dart';
import 'register_tab.dart';
import 'rx_tab.dart';
import 'sync_tab.dart';

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

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  String? _role;

  @override
  void initState() {
    super.initState();
    widget.graph.shellActive = true;
    _loadRole();
  }

  @override
  void dispose() {
    widget.graph.shellActive = false;
    super.dispose();
  }

  bool get _canPrescribe =>
      _role != null && kPrescribingRoles.contains(_role);

  Future<void> _loadRole() async {
    try {
      final me = await widget.graph.client.me();
      if (!mounted) return;
      setState(() => _role = (me['role'] as String?) ?? 'member');
    } catch (_) {
      // Offline: the shell still works with the role stored at sign-in.
      final stored = (await widget.graph.session.profile())?.role ?? '';
      if (!mounted) return;
      setState(() => _role = stored.isNotEmpty ? stored : 'offline');
    }
  }

  /// Sign-out wipes this user's data from the device (H20). Unsynced work
  /// would be lost, so that needs an explicit confirmation.
  Future<void> _signOut() async {
    final graph = widget.graph;
    final unsynced = graph.outbox.unsynced;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(unsynced > 0
            ? 'Unsynced changes will be lost'
            : 'Sign out of this device?'),
        content: Text(unsynced > 0
            ? '$unsynced change${unsynced == 1 ? '' : 's'} saved on this '
                'device ha${unsynced == 1 ? 's' : 've'} NOT reached the '
                'server yet. Signing out deletes them, together with the '
                'cached patient list and drafts. Sync first if you can.'
            : 'The cached patient list, drafts and your PIN are removed '
                'from this device.'),
        actions: [
          TextButton(
            key: const Key('sign-out-cancel'),
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const Key('sign-out-confirm'),
            style: unsynced > 0
                ? FilledButton.styleFrom(
                    backgroundColor: Theme.of(ctx).colorScheme.error)
                : null,
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(unsynced > 0 ? 'Delete and sign out' : 'Sign out'),
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
          graph: widget.graph,
          notice: 'Your sign-in has expired. Work saved on this device is '
              'kept and syncs after you sign in.',
        ),
      ),
      (_) => false,
    );
  }

  List<Widget> get _tabs => [
        QueueTab(graph: widget.graph),
        RegisterTab(graph: widget.graph),
        if (_canPrescribe) RxTab(graph: widget.graph),
        BillingTab(graph: widget.graph),
        SyncTab(graph: widget.graph),
      ];

  List<NavigationDestination> get _destinations => [
        const NavigationDestination(
          icon: Icon(Icons.queue_outlined),
          label: 'Queue',
        ),
        const NavigationDestination(
          icon: Icon(Icons.person_add_outlined),
          label: 'Register',
        ),
        if (_canPrescribe)
          const NavigationDestination(
            icon: Icon(Icons.medication_outlined),
            label: 'Rx',
          ),
        const NavigationDestination(
          icon: Icon(Icons.receipt_long_outlined),
          label: 'Billing',
        ),
        const NavigationDestination(
          icon: Icon(Icons.sync_outlined),
          label: 'Sync',
        ),
      ];

  @override
  Widget build(BuildContext context) {
    final tabs = _tabs;
    final index = _index < tabs.length ? _index : 0;
    return Scaffold(
      appBar: AppBar(
        title: Text('HMS · ${_role ?? '…'}'),
        actions: [
          IconButton(
            key: const Key('sign-out'),
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => _signOut(),
          ),
        ],
      ),
      body: Column(
        children: [
          ValueListenableBuilder<bool>(
            valueListenable: widget.graph.sessionExpired,
            builder: (context, expired, _) => !expired
                ? const SizedBox.shrink()
                : MaterialBanner(
                    key: const Key('session-expired'),
                    content: const Text(
                      'Signed out by the server. You can keep working '
                      'offline; sign in again to sync.',
                    ),
                    actions: [
                      TextButton(
                        onPressed: _signInAgain,
                        child: const Text('Sign in'),
                      ),
                    ],
                  ),
          ),
          Expanded(
            child: IndexedStack(
              index: index,
              children: tabs,
            ),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: _destinations,
      ),
    );
  }
}
