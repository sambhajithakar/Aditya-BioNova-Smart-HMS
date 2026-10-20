/// Device preferences: UI language and "Rural Clinic" simplified mode.
///
/// Kept in the `prefs` section of the app's local store (the same sealed
/// document as the outbox), so they survive restarts. They hold no PHI and
/// are deliberately NOT wiped on sign-out — the next person at the same
/// clinic phone keeps the language and mode the clinic chose. A store
/// reset (recovery screen) does clear them.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart' show Locale;

import '../store/local_store.dart';

/// Minimum touch-target size in Rural Clinic mode (dp).
const double kRuralTouchTarget = 56;

/// Minimum text scale in Rural Clinic mode (the phone's own larger setting
/// still wins).
const double kRuralTextScale = 1.25;

class AppSettings extends ChangeNotifier {
  AppSettings(this._store) {
    final raw = _store.doc[section];
    if (raw is Map) {
      final lang = raw['language'];
      if (lang is String && supportedLanguages.contains(lang)) {
        _language = lang;
      }
      _rural = raw['ruralMode'] == true;
    }
  }

  static const String section = 'prefs';
  static const List<String> supportedLanguages = ['en', 'mr', 'hi'];

  final LocalStore _store;
  String? _language;
  bool _rural = false;

  /// Explicit language code, or null to follow the device language.
  String? get language => _language;

  /// Locale for `MaterialApp.locale`; null = device locale (resolved
  /// against the supported locales, English when unsupported).
  Locale? get locale => _language == null ? null : Locale(_language!);

  /// Rural Clinic mode: large touch targets, larger text, the four-step
  /// Register → Queue → Fast Rx → Bill navigation and quick-pick chips.
  bool get ruralMode => _rural;

  Future<void> setLanguage(String? code) async {
    if (code != null && !supportedLanguages.contains(code)) {
      throw ArgumentError.value(code, 'code', 'unsupported language');
    }
    if (code == _language) return;
    _language = code;
    notifyListeners();
    await _save();
  }

  Future<void> setRuralMode(bool enabled) async {
    if (enabled == _rural) return;
    _rural = enabled;
    notifyListeners();
    await _save();
  }

  Future<void> _save() => _store.saveSection(section, {
        'language': ?_language,
        'ruralMode': _rural,
      });
}
