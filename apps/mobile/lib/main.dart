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
import 'package:flutter_localizations/flutter_localizations.dart';

import 'app_graph.dart';
import 'auth/app_lock.dart' show AppLock;
import 'boot.dart';
import 'demo/demo_server.dart' show kDemoLan;
import 'l10n/l10n.dart';
import 'legal/licenses.dart' show registerAdditionalLicenses;
import 'screens/demo_server_screen.dart';
import 'screens/home_screen.dart' show openHome;
import 'screens/lock_screen.dart';
import 'screens/login_screen.dart';
import 'screens/recovery_screen.dart';
import 'settings/app_settings.dart';

export 'app_graph.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  registerAdditionalLicenses();
  runApp(HmsRoot(initial: await bootDevice()));
}

/// App theme. [rural] = Rural Clinic mode: every button, chip, icon
/// button, list row and navigation item is at least [kRuralTouchTarget]
/// (56 dp) tall, inputs get more padding. The larger text scale is applied
/// by [ruralTextScale] in `MaterialApp.builder`.
ThemeData hmsTheme({bool rural = false}) {
  final base = ThemeData(
    colorSchemeSeed: const Color(0xFF0B3B5C),
    useMaterial3: true,
  );
  if (!rural) return base;
  const tall = Size(kRuralTouchTarget, kRuralTouchTarget);
  return base.copyWith(
    materialTapTargetSize: MaterialTapTargetSize.padded,
    visualDensity: VisualDensity.standard,
    filledButtonTheme:
        FilledButtonThemeData(style: FilledButton.styleFrom(minimumSize: tall)),
    outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(minimumSize: tall)),
    textButtonTheme:
        TextButtonThemeData(style: TextButton.styleFrom(minimumSize: tall)),
    elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(minimumSize: tall)),
    iconButtonTheme:
        IconButtonThemeData(style: IconButton.styleFrom(minimumSize: tall)),
    inputDecorationTheme: const InputDecorationTheme(
      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 18),
    ),
    listTileTheme: const ListTileThemeData(minTileHeight: kRuralTouchTarget),
    navigationBarTheme: const NavigationBarThemeData(height: 80),
  );
}

/// `MaterialApp.builder` for Rural Clinic mode: text at least
/// [kRuralTextScale]× (a larger phone setting still wins).
Widget ruralTextScale(BuildContext context, Widget? child) {
  final media = MediaQuery.of(context);
  return MediaQuery(
    data: media.copyWith(
      textScaler: media.textScaler.clamp(minScaleFactor: kRuralTextScale),
    ),
    child: child ?? const SizedBox.shrink(),
  );
}

/// `MaterialApp.builder` for the LAN demo build: a permanent red strip
/// "DEMO · synthetic data only" above every screen (no-op in other builds).
Widget demoBanner(BuildContext context, Widget? child) {
  final body = child ?? const SizedBox.shrink();
  if (!kDemoLan) return body;
  final media = MediaQuery.of(context);
  return Column(
    children: [
      Material(
        key: const Key('demo-strip'),
        color: const Color(0xFFB00020),
        child: Padding(
          padding: EdgeInsets.only(top: media.padding.top),
          child: SizedBox(
            width: double.infinity,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                context.l10n.demoBanner,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ),
      ),
      Expanded(
        child: MediaQuery.removePadding(context: context, removeTop: true, child: body),
      ),
    ],
  );
}

/// Delegates for the app strings plus Material/Cupertino/Widgets in
/// English, मराठी and हिंदी.
const List<LocalizationsDelegate<dynamic>> kLocalizationsDelegates = [
  AppLocalizations.delegate,
  GlobalMaterialLocalizations.delegate,
  GlobalCupertinoLocalizations.delegate,
  GlobalWidgetsLocalizations.delegate,
];

/// English first: it is the fallback for an unsupported device language.
const List<Locale> kSupportedLocales = [Locale('en'), Locale('mr'), Locale('hi')];

/// Chooses between the app and the store-recovery screen.
class HmsRoot extends StatefulWidget {
  const HmsRoot({super.key, required this.initial});

  final BootOutcome initial;

  /// Replace the running app with [next] (LAN demo build: change server).
  static void replace(BuildContext context, BootOutcome next) =>
      context.findAncestorStateOfType<_HmsRootState>()?._replace(next);

  @override
  State<HmsRoot> createState() => _HmsRootState();
}

class _HmsRootState extends State<HmsRoot> {
  late BootOutcome _outcome = widget.initial;

  void _replace(BootOutcome next) => setState(() => _outcome = next);

  @override
  Widget build(BuildContext context) {
    return switch (_outcome) {
      BootReady(:final graph) => HmsApp(key: ObjectKey(graph), graph: graph),
      final BootNeedsDemoServer request => MaterialApp(
          onGenerateTitle: (ctx) => ctx.l10n.appTitle,
          debugShowCheckedModeBanner: false,
          theme: hmsTheme(),
          localizationsDelegates: kLocalizationsDelegates,
          supportedLocales: kSupportedLocales,
          builder: demoBanner,
          home: DemoServerScreen(request: request, onOutcome: _replace),
        ),
      final BootFailed failure => MaterialApp(
          onGenerateTitle: (ctx) => ctx.l10n.appTitle,
          debugShowCheckedModeBanner: false,
          theme: hmsTheme(),
          localizationsDelegates: kLocalizationsDelegates,
          supportedLocales: kSupportedLocales,
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
    return HmsMaterialApp(
      settings: graph.settings,
      navigatorKey: _navigator,
      home: StartScreen(graph: graph),
    );
  }
}

/// The `MaterialApp` with the device settings applied: UI language
/// (explicit choice, else the device language, else English) and Rural
/// Clinic mode (theme + text scale). Rebuilds when the settings change.
class HmsMaterialApp extends StatelessWidget {
  const HmsMaterialApp({
    super.key,
    required this.settings,
    required this.home,
    this.navigatorKey,
  });

  final AppSettings settings;
  final Widget home;
  final GlobalKey<NavigatorState>? navigatorKey;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: settings,
      builder: (context, _) {
        final rural = settings.ruralMode;
        return MaterialApp(
          navigatorKey: navigatorKey,
          onGenerateTitle: (ctx) => ctx.l10n.appTitle,
          debugShowCheckedModeBanner: false,
          theme: hmsTheme(rural: rural),
          // null = follow the device language (English if unsupported).
          locale: settings.locale,
          localizationsDelegates: kLocalizationsDelegates,
          supportedLocales: kSupportedLocales,
          builder: (ctx, child) => demoBanner(
            ctx,
            rural ? ruralTextScale(ctx, child) : child,
          ),
          home: home,
        );
      },
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
        return LoginScreen(
          graph: widget.graph,
          // Cold start after a remote sign-out: say why.
          notice: widget.graph.deviceRevoked.value
              ? context.l10n.deviceSignedOutByAdmin
              : null,
        );
      },
    );
  }
}
