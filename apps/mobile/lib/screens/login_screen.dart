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
import 'home_screen.dart';
import 'lock_screen.dart';

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
    if (known != null) _email.text = known.email;
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
    if (err is ApiException) {
      if (err.status == 429) return err.readable;
      if (_mfa != null && err.status == 401) {
        return 'That code was not accepted. Check the time on your phone '
            'or use a recovery code.';
      }
      return err.detail;
    }
    return 'Could not reach the server. Check the connection and try again.';
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
      setState(() => _error = 'Enter the code from your authenticator app.');
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
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Aditya BioNova Smart HMS',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 4),
                Text(
                  'Doctor & field staff app',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
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
                    decoration: const InputDecoration(labelText: 'Email'),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('login-password'),
                    controller: _password,
                    obscureText: true,
                    autofillHints: const [AutofillHints.password],
                    decoration: const InputDecoration(labelText: 'Password'),
                    onSubmitted: (_) => _signIn(),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('login-slug'),
                    controller: _slug,
                    decoration: const InputDecoration(
                      labelText: 'Clinic slug (optional)',
                    ),
                  ),
                ] else ...[
                  Text(
                    'Two-step verification',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Enter the 6-digit code from your authenticator app, or '
                    'one of your recovery codes (xxxx-xxxx).',
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('login-mfa-code'),
                    controller: _code,
                    autofillHints: const [AutofillHints.oneTimeCode],
                    decoration: const InputDecoration(labelText: 'Code'),
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
                    child: Text(_busy ? 'Signing in…' : 'Sign in'),
                  )
                else ...[
                  FilledButton(
                    key: const Key('login-mfa-submit'),
                    onPressed: _busy ? null : _verify,
                    child: Text(_busy ? 'Verifying…' : 'Verify'),
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
                    child: const Text('Back'),
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
