/// Secure sign-in: email + password (+ optional clinic slug), exactly the
/// `POST /auth/login` contract of the API, with the second step when the
/// account has MFA (`mfa_required` → 6-digit authenticator code or a
/// recovery code → `POST /auth/mfa/verify`).
///
/// Failures show the server's `detail`; rate limiting (429) shows how long
/// to wait. Success → set the app PIN (first sign-in on this device, or a
/// different user) → role-aware home shell. Signing in again after the
/// session expired keeps everything queued on the device.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/transport.dart';
import '../app_graph.dart';
import '../auth/session.dart';
import '../boot.dart' show changeDemoServer;
import '../demo/demo_server.dart' show kDemoLan;
import '../main.dart' show HmsRoot;
import '../l10n/l10n.dart';
import 'home_screen.dart';
import 'lock_screen.dart';
import 'widgets.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.graph, this.notice});

  final AppGraph graph;

  /// Optional message shown above the form (e.g. "session expired").
  final String? notice;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _slug = TextEditingController();
  final _code = TextEditingController();
  String? _error;
  bool _busy = false;
  MfaChallenge? _mfa;
  SessionProfile? _previous;

  @override
  void initState() {
    super.initState();
    final known = widget.graph.session.cachedProfile;
    if (known != null) {
      _email.text = known.email;
    } else {
      // After a revocation only the quarantine remembers who it belongs to.
      _email.text = widget.graph.quarantine.info?.email ?? '';
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _slug.dispose();
    _code.dispose();
    super.dispose();
  }

  String _message(Object err) {
    final l = context.l10n;
    if (err is ApiException) {
      if (err.status == 429) return rateLimitedMessage(l, err.retryAfter);
      if (_mfa != null && err.status == 401) return l.loginMfaRejected;
      // The server's own detail, verbatim (it is the source of truth).
      return err.detail;
    }
    return l.loginUnreachable;
  }

  Future<void> _signIn() async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      _previous = await widget.graph.session.profile();
      final outcome = await widget.graph.client.login(
        email: _email.text.trim(),
        password: _password.text,
        organizationSlug: _slug.text.trim(),
      );
      switch (outcome) {
        case MfaChallenge():
          _password.clear();
          setState(() => _mfa = outcome);
        case LoginSucceeded(:final profile):
          await _completed(profile);
      }
    } catch (err) {
      if (mounted) setState(() => _error = _message(err));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    final challenge = _mfa;
    if (challenge == null) return;
    final code = _code.text.trim();
    if (code.isEmpty) {
      setState(() => _error = context.l10n.loginMfaMissing);
      return;
    }
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      final done = await widget.graph.client
          .verifyMfa(mfaToken: challenge.mfaToken, code: code);
      await _completed(done.profile);
    } catch (err) {
      if (mounted) setState(() => _error = _message(err));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _completed(SessionProfile? profile) async {
    final graph = widget.graph;
    await graph.onSignedIn(profile);
    final previous = _previous;
    final samePerson = previous != null &&
        profile != null &&
        previous.userId == profile.userId;
    // A PIN belongs to the person who set it.
    if (!samePerson) await graph.appLock.clear();
    if (!mounted) return;
    if (await graph.appLock.hasPin()) {
      graph.appLock.markUnlocked();
      graph.scheduler.requestSync(force: true);
      if (mounted) openHome(context, graph);
      return;
    }
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => LockScreen(
          graph: graph,
          mode: LockMode.setPin,
          onDone: (ctx) {
            graph.scheduler.requestSync(force: true);
            openHome(ctx, graph);
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final mfa = _mfa != null;
    final l = context.l10n;
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        actions: [LanguageMenuButton(settings: widget.graph.settings)],
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  l.appTitle,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 4),
                Text(
                  l.appSubtitle,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                if (kDemoLan) ...[
                  const SizedBox(height: 12),
                  Text(
                    l.demoServerCurrent(widget.graph.baseUrl),
                    key: const Key('login-demo-server'),
                    textAlign: TextAlign.center,
                  ),
                  TextButton(
                    key: const Key('login-demo-change'),
                    onPressed: _busy
                        ? null
                        : () async {
                            final next = await changeDemoServer();
                            if (context.mounted) HmsRoot.replace(context, next);
                          },
                    child: Text(l.demoServerChange),
                  ),
                ],
                if (widget.notice != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(
                      widget.notice!,
                      key: const Key('login-notice'),
                      textAlign: TextAlign.center,
                    ),
                  ),
                const SizedBox(height: 24),
                if (!mfa) ...[
                  TextField(
                    key: const Key('login-email'),
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.email],
                    decoration: InputDecoration(labelText: l.loginEmail),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('login-password'),
                    controller: _password,
                    obscureText: true,
                    autofillHints: const [AutofillHints.password],
                    decoration: InputDecoration(labelText: l.loginPassword),
                    onSubmitted: (_) => _signIn(),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('login-slug'),
                    controller: _slug,
                    decoration: InputDecoration(labelText: l.loginSlug),
                  ),
                ] else ...[
                  Text(
                    l.loginMfaTitle,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(l.loginMfaHelp),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('login-mfa-code'),
                    controller: _code,
                    autofillHints: const [AutofillHints.oneTimeCode],
                    decoration: InputDecoration(labelText: l.loginMfaCode),
                    onSubmitted: (_) => _verify(),
                  ),
                ],
                const SizedBox(height: 20),
                if (_error != null)
                  Text(
                    _error!,
                    key: const Key('login-error'),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                const SizedBox(height: 8),
                if (!mfa)
                  FilledButton(
                    key: const Key('login-submit'),
                    onPressed: _busy ? null : _signIn,
                    child: Text(_busy ? l.loginSigningIn : l.loginSubmit),
                  )
                else ...[
                  FilledButton(
                    key: const Key('login-mfa-submit'),
                    onPressed: _busy ? null : _verify,
                    child: Text(_busy ? l.loginVerifying : l.loginVerify),
                  ),
                  TextButton(
                    key: const Key('login-mfa-back'),
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                              _mfa = null;
                              _code.clear();
                              _error = null;
                            }),
                    child: Text(l.back),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
