/// Aditya BioNova Smart HMS — offline-first mobile app.
///
/// `main()` opens the encrypted offline store ([bootDevice]) and either
/// starts the app or — if the store cannot be unlocked — shows the
/// recovery screen. It never falls back to a memory-only store (H23).
///
/// Start-up routing (H22): with a stored session and a PIN the app opens
/// at the PIN lock and then Home — no network needed; otherwise at the
/// online sign-in. The PIN is asked again after [AppLock.inactivityTimeout]
/// in the background. Resuming also triggers a sync attempt.
///
/// The API base defaults to the Android emulator loopback (`10.0.2.2`, a
/// debug-only cleartext host) and is set per build:
///
///   flutter run --dart-define=API_BASE=http://192.168.1.50:8000
///   flutter build apk --release --dart-define=API_BASE=https://api.example
library;

import 'package:flutter/material.dart';

import 'app_graph.dart';
import 'auth/app_lock.dart' show AppLock;
import 'boot.dart';
import 'screens/home_screen.dart' show openHome;
import 'screens/lock_screen.dart';
import 'screens/login_screen.dart';
import 'screens/recovery_screen.dart';

export 'app_graph.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(HmsRoot(initial: await bootDevice()));
}

ThemeData hmsTheme() => ThemeData(
      colorSchemeSeed: const Color(0xFF0B3B5C),
      useMaterial3: true,
    );

/// Chooses between the app and the store-recovery screen.
class HmsRoot extends StatefulWidget {
  const HmsRoot({super.key, required this.initial});

  final BootOutcome initial;

  @override
  State<HmsRoot> createState() => _HmsRootState();
}

class _HmsRootState extends State<HmsRoot> {
  late BootOutcome _outcome = widget.initial;

  @override
  Widget build(BuildContext context) {
    return switch (_outcome) {
      BootReady(:final graph) => HmsApp(graph: graph),
      final BootFailed failure => MaterialApp(
          title: 'Aditya BioNova Smart HMS',
          debugShowCheckedModeBanner: false,
          theme: hmsTheme(),
          home: StoreRecoveryScreen(
            failure: failure,
            onOutcome: (next) => setState(() => _outcome = next),
          ),
        ),
    };
  }
}

class HmsApp extends StatefulWidget {
  const HmsApp({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<HmsApp> createState() => _HmsAppState();
}

class _HmsAppState extends State<HmsApp> with WidgetsBindingObserver {
  final GlobalKey<NavigatorState> _navigator = GlobalKey<NavigatorState>();
  bool _lockShown = false;

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    graph.scheduler.stop();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
        graph.appLock.onBackground();
        graph.flush();
      case AppLifecycleState.resumed:
        _onResume();
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
        break;
    }
  }

  Future<void> _onResume() async {
    if (!graph.shellActive) return;
    final mustLock = graph.appLock.onResume();
    if (mustLock && !_lockShown && await graph.appLock.hasPin()) {
      _lockShown = true;
      await _navigator.currentState?.push(
        MaterialPageRoute<void>(
          fullscreenDialog: true,
          builder: (_) => LockScreen(
            graph: graph,
            mode: LockMode.unlock,
            onDone: (ctx) => Navigator.of(ctx).pop(),
          ),
        ),
      );
      _lockShown = false;
      return;
    }
    if (graph.appLock.isUnlocked) graph.scheduler.requestSync(force: true);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigator,
      title: 'Aditya BioNova Smart HMS',
      debugShowCheckedModeBanner: false,
      theme: hmsTheme(),
      home: StartScreen(graph: graph),
    );
  }
}

/// Cold-start routing: PIN lock → Home when a session is stored on the
/// device (works with no network), online sign-in otherwise.
class StartScreen extends StatefulWidget {
  const StartScreen({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<StartScreen> createState() => _StartScreenState();
}

class _StartScreenState extends State<StartScreen> {
  late final Future<bool> _canResume = _resumable();

  Future<bool> _resumable() async {
    final g = widget.graph;
    return await g.session.hasStoredSession() &&
        await g.session.profile() != null &&
        await g.appLock.hasPin();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<bool>(
      future: _canResume,
      builder: (context, snap) {
        if (!snap.hasData) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (snap.data!) {
          widget.graph.appLock.lock();
          return LockScreen(
            graph: widget.graph,
            mode: LockMode.unlock,
            onDone: (ctx) => openHome(ctx, widget.graph),
          );
        }
        return LoginScreen(graph: widget.graph);
      },
    );
  }
}
