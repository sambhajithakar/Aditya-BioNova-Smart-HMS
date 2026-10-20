// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Aditya BioNova Smart HMS';

  @override
  String get appSubtitle => 'Doctor & field staff app';

  @override
  String get languageMenu => 'Language';

  @override
  String get languageDevice => 'Device language';

  @override
  String get settingsMenu => 'Settings';

  @override
  String get refresh => 'Refresh';

  @override
  String get cancel => 'Cancel';

  @override
  String get back => 'Back';

  @override
  String get patient => 'Patient';

  @override
  String get branch => 'Branch';

  @override
  String get pickPatientFirst => 'Pick a patient first.';

  @override
  String outboxCounts(int pending, int failed, int conflicted) {
    return 'Outbox — pending: $pending, failed: $failed, conflicted: $conflicted';
  }

  @override
  String outboxCountsShort(int pending, int conflicted) {
    return 'Outbox — pending: $pending, conflicted: $conflicted';
  }

  @override
  String get pendingSyncTag => '(pending sync)';

  @override
  String get syncedTag => '(synced)';

  @override
  String get loginEmail => 'Email';

  @override
  String get loginPassword => 'Password';

  @override
  String get loginSlug => 'Clinic slug (optional)';

  @override
  String get loginSubmit => 'Sign in';

  @override
  String get loginSigningIn => 'Signing in…';

  @override
  String get loginMfaTitle => 'Two-step verification';

  @override
  String get loginMfaHelp =>
      'Enter the 6-digit code from your authenticator app, or one of your recovery codes (xxxx-xxxx).';

  @override
  String get loginMfaCode => 'Code';

  @override
  String get loginVerify => 'Verify';

  @override
  String get loginVerifying => 'Verifying…';

  @override
  String get loginMfaMissing => 'Enter the code from your authenticator app.';

  @override
  String get loginMfaRejected =>
      'That code was not accepted. Check the time on your phone or use a recovery code.';

  @override
  String get loginUnreachable =>
      'Could not reach the server. Check the connection and try again.';

  @override
  String get rateLimitedWait => 'Too many attempts. Please wait and try again.';

  @override
  String rateLimitedSeconds(int seconds) {
    return 'Too many attempts. Try again in $seconds seconds.';
  }

  @override
  String rateLimitedMinutes(int minutes) {
    String _temp0 = intl.Intl.pluralLogic(
      minutes,
      locale: localeName,
      other: '$minutes minutes',
      one: '1 minute',
    );
    return 'Too many attempts. Try again in $_temp0.';
  }

  @override
  String get sessionExpiredNotice =>
      'Your sign-in has expired. Work saved on this device is kept and syncs after you sign in.';

  @override
  String get lockedOutNotice =>
      'Too many wrong PINs. Sign in online again — work saved on this device is kept.';

  @override
  String get pinSetTitle => 'Set an app PIN';

  @override
  String get pinUnlockTitle => 'Enter your app PIN';

  @override
  String get pinSetHelp =>
      'Patient data on this device is protected by a PIN. You will need it to open the app, even with no network.';

  @override
  String get worksOffline => 'Works offline.';

  @override
  String get pinLabel => 'PIN';

  @override
  String get pinRepeat => 'Repeat PIN';

  @override
  String get pinSave => 'Save PIN';

  @override
  String get pinUnlock => 'Unlock';

  @override
  String get pinUsePassword => 'Sign in with password instead';

  @override
  String get pinRule => 'Use 4 to 8 digits.';

  @override
  String get pinMismatch => 'The two PINs do not match.';

  @override
  String pinWrong(int left) {
    String _temp0 = intl.Intl.pluralLogic(
      left,
      locale: localeName,
      other: '$left attempts',
      one: '1 attempt',
    );
    return 'Wrong PIN — $_temp0 left.';
  }

  @override
  String get recoveryTitle => 'Offline data could not be unlocked';

  @override
  String get recoveryTitleFatal => 'This build cannot start';

  @override
  String get recoveryBody =>
      'The work saved on this device is encrypted with a key kept in this phone\'s secure hardware. The key or the data could not be read — this happens after restoring the app onto a new phone, or if the stored file was damaged.\n\nThe app will not continue without its offline storage, because new work would silently be lost. Try again first; if it keeps failing, reset the local data.';

  @override
  String recoveryDetails(String details) {
    return 'Details: $details';
  }

  @override
  String get recoveryRetry => 'Try again';

  @override
  String get recoveryReset => 'Reset local data (unsynced items will be lost)';

  @override
  String get recoveryResetTitle => 'Reset local data?';

  @override
  String get recoveryResetBody =>
      'Everything stored on this device by the app is deleted: registrations, queue entries, invoices and prescription drafts that have not synced are LOST and cannot be recovered. Data already on the server is not affected. You will sign in again afterwards.';

  @override
  String get recoveryResetConfirm => 'Delete local data';

  @override
  String homeTitle(String role) {
    return 'HMS · $role';
  }

  @override
  String get signOut => 'Sign out';

  @override
  String get signOutTitle => 'Sign out of this device?';

  @override
  String get signOutTitleUnsynced => 'Unsynced changes will be lost';

  @override
  String get signOutBody =>
      'The cached patient list, drafts and your PIN are removed from this device.';

  @override
  String signOutBodyUnsynced(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          '$count changes saved on this device have NOT reached the server yet.',
      one: '1 change saved on this device has NOT reached the server yet.',
    );
    return '$_temp0 Signing out deletes them, together with the cached patient list and drafts. Sync first if you can.';
  }

  @override
  String get signOutDelete => 'Delete and sign out';

  @override
  String get sessionExpiredBanner =>
      'Signed out by the server. You can keep working offline; sign in again to sync.';

  @override
  String get tabQueue => 'Queue';

  @override
  String get tabRegister => 'Register';

  @override
  String get tabRx => 'Rx';

  @override
  String get tabFastRx => 'Fast Rx';

  @override
  String get tabBilling => 'Billing';

  @override
  String get tabBill => 'Bill';

  @override
  String get tabSync => 'Sync';

  @override
  String get ruralMode => 'Rural clinic mode';

  @override
  String get ruralModeHelp => 'Large buttons, bigger text, four steps';

  @override
  String editionLabel(String edition) {
    return 'Edition: $edition';
  }

  @override
  String get mobileNotEnabled =>
      'The mobile app is not part of your clinic\'s plan. Changes already saved on this device can still be synced from the Sync tab. Contact your administrator.';

  @override
  String get queueTitle => 'Offline queue entry';

  @override
  String get queuePickBoth => 'Pick a patient and a branch (need one sync).';

  @override
  String get queueDuplicate =>
      'Already queued for today — duplicate prevented.';

  @override
  String queueSaved(int count) {
    return 'Saved on device — pending sync ($count in the outbox).';
  }

  @override
  String get queueAdd => 'Add to queue (works offline)';

  @override
  String get loadingPatients => 'Loading patients…';

  @override
  String get noPatientsCached =>
      'No patients cached yet — connect once to pull the directory, after which queue entries work offline.';

  @override
  String get registerTitle => 'Register patient (works offline)';

  @override
  String get registerName => 'Full name';

  @override
  String get registerGender => 'Gender';

  @override
  String get genderFemale => 'Female';

  @override
  String get genderMale => 'Male';

  @override
  String get genderOther => 'Other';

  @override
  String get genderUnknown => 'Unknown';

  @override
  String get registerPhone => 'Phone (optional)';

  @override
  String get registerDobUnknown => 'Date of birth — not known (estimated)';

  @override
  String registerDob(String date) {
    return 'Date of birth — $date';
  }

  @override
  String get pick => 'Pick';

  @override
  String get registerAllergies =>
      'Known allergies (write what the family reports)';

  @override
  String get registerAdd => 'Register (works offline)';

  @override
  String get registerNameRequired => 'Enter the patient’s full name.';

  @override
  String get registerLooksDuplicate =>
      'Looks like an existing patient — duplicate prevented (pick them from the list, or edit the details to register anyway).';

  @override
  String get registerDuplicateQueued =>
      'Identical registration already queued — duplicate prevented.';

  @override
  String get registerSaved =>
      'Saved on device — pending sync. Assigned to today’s queue as soon as it syncs.';

  @override
  String get billingTitle => 'Raise invoice (works offline)';

  @override
  String get billingLineType => 'Line type';

  @override
  String get itemConsultation => 'Consultation';

  @override
  String get itemProcedure => 'Procedure';

  @override
  String get itemPharmacy => 'Pharmacy';

  @override
  String get itemLab => 'Lab';

  @override
  String get itemOther => 'Other';

  @override
  String get billingDescription => 'Description';

  @override
  String get billingQuantity => 'Quantity';

  @override
  String get billingUnitPrice => 'Unit price';

  @override
  String get billingAdd => 'Save invoice (works offline)';

  @override
  String get billingDescribe => 'Describe the line being billed.';

  @override
  String get billingQtyPrice => 'Quantity and unit price are required.';

  @override
  String get billingDuplicate =>
      'Identical invoice already queued — duplicate prevented.';

  @override
  String get billingSaved =>
      'Invoice saved on device — pending sync. Totals and the invoice number are computed by the server.';

  @override
  String get rxTitle => 'Fast Rx draft (works offline)';

  @override
  String get rxMedicine => 'Medicine (validated catalog)';

  @override
  String get rxDose => 'Dose (500 mg)';

  @override
  String get rxFrequency => 'Frequency (BD)';

  @override
  String get rxDays => 'Days';

  @override
  String get rxDispense => 'Units to dispense (optional)';

  @override
  String get rxDispenseHelp =>
      'Pharmacy cannot hand out more than this in total';

  @override
  String get rxAddItem => 'Add medicine';

  @override
  String rxItemLine(String drug, String dose, String frequency, String days) {
    return '$drug — $dose, $frequency, $days days';
  }

  @override
  String rxItemDispense(String quantity) {
    return ' · dispense $quantity';
  }

  @override
  String get rxDiagnosis => 'Diagnosis (text)';

  @override
  String get rxSave => 'Save draft (works offline)';

  @override
  String get rxDrafts => 'Drafts on this device';

  @override
  String get rxNoDrafts =>
      'No drafts yet — they are kept here with their sync state.';

  @override
  String get rxNoCatalog => 'No drug catalog cached yet — connect once.';

  @override
  String get rxRequired => 'Dose, frequency and duration are required.';

  @override
  String get rxDispenseRange =>
      'Quantity to dispense must be 1–10000 units (or leave it blank).';

  @override
  String get rxAddOne => 'Add at least one medicine.';

  @override
  String get rxDuplicate =>
      'Identical draft already queued — duplicate prevented.';

  @override
  String get rxSaved =>
      'Draft saved on device — pending sync. Sign it after it syncs (the allergy check runs on the server).';

  @override
  String get rxSigned => 'Prescription signed.';

  @override
  String get rxSign => 'Sign';

  @override
  String get rxSignAfterSync => 'Sign (after sync)';

  @override
  String rxDraftLine(String drug, String dose, String frequency, String days) {
    return '$drug $dose $frequency ${days}d';
  }

  @override
  String get rxQuickFrequency => 'Tap a frequency';

  @override
  String get rxQuickDuration => 'Tap the number of days';

  @override
  String get freqOD => 'once a day';

  @override
  String get freqBD => 'twice a day';

  @override
  String get freqTDS => 'three times a day';

  @override
  String get freqQID => 'four times a day';

  @override
  String get freqHS => 'at bedtime';

  @override
  String get freqSOS => 'only when needed';

  @override
  String daysCount(int days) {
    String _temp0 = intl.Intl.pluralLogic(
      days,
      locale: localeName,
      other: '$days days',
      one: '1 day',
    );
    return '$_temp0';
  }

  @override
  String get stateSigned => 'Signed';

  @override
  String get stateConflict => 'Conflict — needs you';

  @override
  String get stateSavedPending => 'Saved on device · Pending sync';

  @override
  String get stateDiscarded => 'Discarded — not sent';

  @override
  String get stateSynced => 'Synced';

  @override
  String get opPending => 'Pending sync';

  @override
  String opPendingRetry(int attempt) {
    return 'Pending sync · retry $attempt';
  }

  @override
  String get opSyncing => 'Syncing…';

  @override
  String get opFailed => 'Not sent yet — retries automatically';

  @override
  String opFailedAttempt(int attempt) {
    return 'Not sent yet — retries automatically (attempt $attempt)';
  }

  @override
  String savedOnDevice(String state) {
    return 'Saved on device · $state';
  }

  @override
  String get syncTitle => 'Sync centre';

  @override
  String syncCounts(int pending, int failed, int conflicted) {
    return 'pending: $pending · failed: $failed · conflicted: $conflicted';
  }

  @override
  String syncNextRetry(String time) {
    return 'Automatic retry from $time';
  }

  @override
  String get syncNow => 'Sync now';

  @override
  String get syncRetryFailed => 'Retry failed now';

  @override
  String syncResult(int pushed, int conflicts, int failed) {
    return 'pushed $pushed · conflicts $conflicts · failed $failed';
  }

  @override
  String syncWaiting(int count) {
    return ' · waiting $count';
  }

  @override
  String get syncStopped => ' · stopped (sign in again)';

  @override
  String syncedEntity(String entity) {
    return 'Synced · $entity';
  }

  @override
  String syncPersistError(String error) {
    return 'Could not save to device storage: $error';
  }

  @override
  String get syncQueued => 'Queued on this device';

  @override
  String get syncNothingQueued =>
      'Nothing queued — every change has reached the server.';

  @override
  String get syncNoConflicts => 'No conflicts — local and server agree.';

  @override
  String get conflictDiscard => 'Discard (server wins here)';

  @override
  String get conflictRegisterAnyway => 'Keep local (register anyway)';

  @override
  String get conflictClaim => 'Keep local (send as me)';

  @override
  String get conflictKeep => 'Keep local (re-send)';

  @override
  String get registerAnywayTitle => 'Register as a NEW patient?';

  @override
  String registerAnywayBody(String name) {
    return 'The server found existing patient(s) that look like $name. Only continue if you have checked this is a different person — a duplicate record splits the patient\'s history.';
  }

  @override
  String get registerAnywayAction => 'Register anyway';

  @override
  String registerAnywayNotice(String name) {
    return 'Will register $name as a new patient on the next sync.';
  }

  @override
  String get thisPatient => 'this patient';

  @override
  String get claimTitle => 'Send under your account?';

  @override
  String get claimBody =>
      'This change was saved before the app recorded who made it. Send it only if you made it.';

  @override
  String get claimAction => 'Send as me';

  @override
  String discardTitle(String entity, int count) {
    return 'Discard $entity and $count more?';
  }

  @override
  String discardBody(int count, String what, String entity) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          '$count queued changes ($what) refer to this $entity and can never be sent without it. They will be discarded too.',
      one:
          '1 queued change ($what) refers to this $entity and can never be sent without it. It will be discarded too.',
    );
    return '$_temp0';
  }

  @override
  String get discardAll => 'Discard all';

  @override
  String discardedOne(String entity) {
    return 'Discarded: $entity.';
  }

  @override
  String discardedMany(String entity, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count dependent changes',
      one: '1 dependent change',
    );
    return 'Discarded: $entity and $_temp0.';
  }

  @override
  String get entityPatient => 'patient';

  @override
  String get entityQueueEntry => 'queue entry';

  @override
  String get entityInvoice => 'invoice';

  @override
  String get entityPrescription => 'prescription';

  @override
  String get conflictVersion => 'The record changed on the server';

  @override
  String get conflictPolicy => 'The server refused this change';

  @override
  String get conflictAuth => 'Sign in again to continue';

  @override
  String get conflictDuplicate => 'Possible duplicate registration';

  @override
  String get conflictWrongUser => 'Created by another user on this device';
}
