/// UI language support: English (template), मराठी and हिंदी.
///
/// The strings live in `lib/l10n/app_{en,mr,hi}.arb`; `flutter gen-l10n`
/// (run automatically by `flutter pub get` / `flutter run`, because
/// `generate: true` is set in pubspec.yaml) turns them into
/// `app_localizations*.dart`. Screens read them with `context.l10n`.
///
/// Clinical identifiers are never translated: drug names, doses, UHIDs,
/// frequency codes (OD / BD / TDS …), server error details and patient
/// names are shown exactly as entered or as the server sent them.
library;

import 'package:flutter/widgets.dart';

import '../sync/conflict.dart';
import 'app_localizations.dart';

export 'app_localizations.dart';

/// Languages offered by the in-app picker, each named in its own script.
const Map<String, String> kLanguageNames = {
  'en': 'English',
  'mr': 'मराठी',
  'hi': 'हिंदी',
};

final AppLocalizations _english = lookupAppLocalizations(const Locale('en'));

extension L10nContext on BuildContext {
  /// The strings for the active locale. Falls back to English when no
  /// localizations delegate is installed above this context (e.g. a bare
  /// `MaterialApp` in a unit-style widget test).
  AppLocalizations get l10n =>
      Localizations.of<AppLocalizations>(this, AppLocalizations) ?? _english;
}

/// Human name for an outbox entity (`patient`, `queue_entry`, …).
String entityLabel(AppLocalizations l, String entity) => switch (entity) {
      'patient' => l.entityPatient,
      'queue_entry' => l.entityQueueEntry,
      'invoice' => l.entityInvoice,
      'prescription' => l.entityPrescription,
      _ => entity.replaceAll('_', ' '),
    };

/// Label for a patient's recorded gender value (the stored value stays the
/// API enum).
String genderLabel(AppLocalizations l, String value) => switch (value) {
      'female' => l.genderFemale,
      'male' => l.genderMale,
      'other' => l.genderOther,
      _ => l.genderUnknown,
    };

/// Label for an invoice line type (the stored value stays the API enum).
String itemTypeLabel(AppLocalizations l, String value) => switch (value) {
      'consultation' => l.itemConsultation,
      'procedure' => l.itemProcedure,
      'pharmacy' => l.itemPharmacy,
      'lab' => l.itemLab,
      _ => l.itemOther,
    };

/// Why an op is parked as a conflict.
String conflictLabel(AppLocalizations l, ConflictKind kind) => switch (kind) {
      ConflictKind.versionMismatch => l.conflictVersion,
      ConflictKind.rejectedByPolicy => l.conflictPolicy,
      ConflictKind.authRequired => l.conflictAuth,
      ConflictKind.duplicatePatient => l.conflictDuplicate,
      ConflictKind.wrongUser => l.conflictWrongUser,
    };

/// Localized 429 message ("try again in N minutes") from `Retry-After`.
String rateLimitedMessage(AppLocalizations l, Duration? wait) {
  if (wait == null) return l.rateLimitedWait;
  if (wait.inSeconds < 60) return l.rateLimitedSeconds(wait.inSeconds);
  return l.rateLimitedMinutes((wait.inSeconds / 60).ceil());
}
