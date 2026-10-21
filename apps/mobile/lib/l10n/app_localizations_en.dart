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
  String get openSourceLicences => 'Open-source licences';

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

  @override
  String get statusOnline => 'Online';

  @override
  String get statusOffline => 'Offline';

  @override
  String get statusSavedOnDevice => 'Saved on device';

  @override
  String get statusPendingSync => 'Pending sync';

  @override
  String get statusSyncing => 'Syncing';

  @override
  String get statusSynced => 'Synced';

  @override
  String get statusConflict => 'Conflict';

  @override
  String get statusActionRequired => 'Action required';

  @override
  String statusCount(String status, int count) {
    return '$status: $count';
  }

  @override
  String globalToSync(int count) {
    return '$count to sync';
  }

  @override
  String globalConflicts(int count) {
    return '$count in conflict';
  }

  @override
  String globalNeedAction(int count) {
    return '$count need action';
  }

  @override
  String globalOfflineSaved(int count) {
    return 'Offline · $count saved on device';
  }

  @override
  String get globalAllSynced => 'All synced';

  @override
  String get needsConnection =>
      'Needs connection — will not be finalised offline';

  @override
  String get needsConnectionTitle => 'Needs connection';

  @override
  String get needsConnectionReports =>
      'Reports are calculated by the server and are not stored on this device.';

  @override
  String get errNetwork => 'No connection — it will be retried automatically.';

  @override
  String get errServer => 'Server problem — it will be retried automatically.';

  @override
  String get errBusy => 'Server busy — it will be retried a little later.';

  @override
  String errForbidden(String detail) {
    return 'Not permitted for your account: $detail';
  }

  @override
  String errInvalid(String detail) {
    return 'The server did not accept the data: $detail';
  }

  @override
  String errMaxAttempts(int count) {
    return 'Tried $count times without success — automatic retries stopped. Tap Retry now.';
  }

  @override
  String get retryNow => 'Retry now';

  @override
  String waitingFor(String entity) {
    return 'Waiting for the $entity to sync first';
  }

  @override
  String blockedBy(String entity) {
    return 'Blocked: the $entity it depends on needs your action';
  }

  @override
  String get orphanedExplain =>
      'It refers to a record that was discarded — it can never be sent as it is.';

  @override
  String get syncAttention => 'Needs your attention';

  @override
  String get storageTitle => 'Storage on this device';

  @override
  String storageUsage(int kb, int patients, int queued) {
    return 'About $kb KB encrypted · $patients cached patients · $queued queued changes';
  }

  @override
  String get clearCacheAction => 'Clear cached patient data';

  @override
  String get clearCacheTitle => 'Clear cached patients?';

  @override
  String get clearCacheBody =>
      'Patients downloaded from the server are removed from this device. Patients registered here and not yet synced are kept. They download again next time you are online.';

  @override
  String clearCacheDone(int count) {
    return '$count cached patients removed from this device.';
  }

  @override
  String get deviceSignedOutByAdmin =>
      'This device was signed out by an administrator. Patient data was removed from it; unsynced work is sealed on the device and comes back when the same user signs in again.';

  @override
  String quarantineTitle(int count) {
    return '$count unsynced items from a signed-out user are sealed on this device';
  }

  @override
  String get quarantineBody =>
      'They cannot be viewed. They sync when that user signs in again on this device.';

  @override
  String get quarantineDiscardAction => 'Discard sealed items';

  @override
  String quarantineDiscardTitle(int count) {
    return 'Discard $count sealed items?';
  }

  @override
  String get quarantineDiscardBody =>
      'They were never sent to the server and cannot be recovered after this.';

  @override
  String get quarantineDiscarded => 'Sealed items discarded.';

  @override
  String get conflictReview => 'Review';

  @override
  String get conflictMine => 'Saved on this device';

  @override
  String get conflictServer => 'On the server';

  @override
  String get conflictSendMine => 'Send mine again';

  @override
  String get conflictSendMineTitle => 'Send your version again?';

  @override
  String get conflictSendMineBody =>
      'The server record changed after you saved this. Sending again does not overwrite silently — the server checks it again and may refuse it.';

  @override
  String get conflictSentAgain => 'Queued to send again.';

  @override
  String get useServerVersion => 'Use the server version';

  @override
  String get versionTitle => 'Changed on the server';

  @override
  String get versionExplain =>
      'Someone changed this record on the server after you saved your change. Compare and choose — nothing is overwritten automatically.';

  @override
  String get dupTitle => 'Possible duplicate patient';

  @override
  String get dupExplain =>
      'The server already has a similar patient. Choose: keep yours as a new patient, use the existing record, or merge by reviewing each field.';

  @override
  String dupMatchedOn(String fields) {
    return 'Matched on: $fields';
  }

  @override
  String get keepMineNew => 'Keep mine as a new patient';

  @override
  String get useServerAction => 'Use this record';

  @override
  String useServerTitle(String patient) {
    return 'Use $patient?';
  }

  @override
  String useServerBody(int count) {
    return 'Your registration will not be sent. $count queued changes for this patient will be linked to the existing record instead.';
  }

  @override
  String useServerDone(String patient) {
    return 'Linked to $patient.';
  }

  @override
  String get mergeAction => 'Merge by review';

  @override
  String get mergeTitle => 'Merge by review';

  @override
  String get mergeExplain =>
      'The server record was just read again. Tick only the fields to copy from your registration; nothing is selected for you.';

  @override
  String get mergeNothing =>
      'No differing fields — the existing record will be used.';

  @override
  String mergeFieldLine(String server, String mine) {
    return 'Server: $server → Mine: $mine';
  }

  @override
  String mergeApply(int count) {
    return 'Copy $count fields and use the record';
  }

  @override
  String mergeDone(int count, String uhid) {
    return '$count fields copied to $uhid.';
  }

  @override
  String get fieldDob => 'Date of birth';

  @override
  String get fieldAddress => 'Address';

  @override
  String get fieldBloodGroup => 'Blood group';

  @override
  String get detailRequest => 'Request';

  @override
  String get detailState => 'State';

  @override
  String get detailCreated => 'Saved at';

  @override
  String get detailAttempts => 'Attempts';

  @override
  String get detailNextRetry => 'Next retry';

  @override
  String get detailKey => 'Idempotency key';

  @override
  String get detailHttp => 'Server answer';

  @override
  String get detailError => 'Last problem';

  @override
  String get detailDepends => 'Depends on';

  @override
  String get detailNoLongerQueued => 'This change is no longer in the queue.';

  @override
  String get tabOverview => 'Overview';

  @override
  String get tabConsult => 'Consult';

  @override
  String get tabPatients => 'Patients';

  @override
  String get tabAppointments => 'Appointments';

  @override
  String get tabStock => 'Stock';

  @override
  String get noTabsForRole =>
      'Nothing is enabled for your role on mobile. Ask your administrator.';

  @override
  String get patientsSearch => 'Search name, UHID or phone';

  @override
  String get patientsSearchServer => 'Search the server';

  @override
  String patientsCachedNote(int count) {
    return '$count patients on this device (only ones you have opened online; encrypted)';
  }

  @override
  String get consultTitle => 'Consultation note (draft — works offline)';

  @override
  String get consultComplaint => 'Chief complaint';

  @override
  String get consultHistory => 'History';

  @override
  String get consultExam => 'Examination';

  @override
  String get consultSave => 'Save note draft';

  @override
  String get consultUpdate => 'Update draft';

  @override
  String get consultEdit => 'Edit';

  @override
  String get consultSaved => 'Note draft saved on device — pending sync.';

  @override
  String get consultDuplicate =>
      'A note draft for this patient today is already queued (duplicate prevented).';

  @override
  String get consultComplaintRequired => 'Enter the chief complaint.';

  @override
  String get consultNoBranch =>
      'No branch on this device yet — open Queue once while online.';

  @override
  String get consultAlreadySent =>
      'This draft was already sent — it can no longer be edited on the device.';

  @override
  String get consultDrafts => 'Note drafts';

  @override
  String get consultNoDrafts => 'No note drafts on this device.';

  @override
  String get consultComplete => 'Complete consultation';

  @override
  String get consultCompleteAfterSync => 'Complete (after sync)';

  @override
  String get consultCompleted => 'Consultation completed on the server.';

  @override
  String get appointmentsTitle => 'Book appointment (works offline)';

  @override
  String appointmentDay(String day) {
    return 'Day: $day';
  }

  @override
  String get appointmentReason => 'Reason';

  @override
  String get appointmentSave => 'Save appointment draft';

  @override
  String get appointmentSaved =>
      'Appointment saved on device — pending sync. The server checks the slot when it syncs.';

  @override
  String get appointmentDuplicate =>
      'This appointment is already queued (duplicate prevented).';

  @override
  String get appointmentDrafts => 'Appointment drafts';

  @override
  String get appointmentsToday => 'Today\'s appointments (server)';

  @override
  String get appointmentsNone => 'No appointments today.';

  @override
  String get queueToday => 'Today\'s queue (server)';

  @override
  String get queueTodayShow => 'Show';

  @override
  String get checkInScan => 'Scan check-in QR';

  @override
  String get checkInSaved => 'Check-in saved on device — pending sync.';

  @override
  String get checkInDuplicate =>
      'This code was already scanned today (duplicate prevented).';

  @override
  String get checkInInvalid => 'This is not a clinic check-in code.';

  @override
  String get scanCheckInTitle => 'Scan check-in code';

  @override
  String get scanBatchTitle => 'Scan medicine pack';

  @override
  String get scanCheckInHelp =>
      'Point the camera at the QR code at the desk or on the slip.';

  @override
  String get scanBatchHelp =>
      'Point the camera at the barcode on the strip or box (batch and expiry are read from it).';

  @override
  String get scanTypeCode => 'Type the code';

  @override
  String get scanUse => 'Use';

  @override
  String get rxDraftPdf => 'Draft PDF';

  @override
  String get rxDraftPdfDone =>
      'Draft preview created (watermarked — not valid until signed online).';

  @override
  String get rxPrintSigned => 'Print signed Rx';

  @override
  String get billingRecent => 'Recent invoices (server)';

  @override
  String get billingRecentShow => 'Show';

  @override
  String invoiceAmounts(String total, String paid, String status) {
    return 'Total $total · paid $paid · $status';
  }

  @override
  String get invoiceReceipt => 'Receipt PDF';

  @override
  String get paymentConfirm => 'Confirm payment';

  @override
  String paymentTitle(String invoice) {
    return 'Payment for $invoice';
  }

  @override
  String get paymentAmount => 'Amount received';

  @override
  String get paymentServerNote =>
      'Recorded by the server now. It is never saved offline.';

  @override
  String get paymentRecorded => 'Payment recorded by the server.';

  @override
  String get reportsTitle => 'Today\'s summary';

  @override
  String get reportsToday => 'Today (from the server)';

  @override
  String get reportsCollections => 'Collections';

  @override
  String get reportsRefunds => 'Refunds';

  @override
  String get reportsNet => 'Net';

  @override
  String get reportsAppointments => 'Appointments';

  @override
  String get reportsAdmitted => 'Admitted now';

  @override
  String get reportsLowStock => 'Low-stock items';

  @override
  String get reportsServerNote =>
      'Calculated by the server from its ledger; nothing is stored on this device.';

  @override
  String get reportsForbidden => 'Your role cannot view reports.';

  @override
  String get syncHealthTitle => 'Sync health of this device';

  @override
  String get stockTitle => 'Stock count (draft — works offline)';

  @override
  String get stockScan => 'Scan batch barcode';

  @override
  String get stockPickItem => 'Pick an item';

  @override
  String get stockCounted => 'Counted quantity';

  @override
  String get stockSave => 'Save count draft';

  @override
  String get stockSaved =>
      'Count saved on device. Post it online after review.';

  @override
  String get stockQtyInvalid => 'Enter a whole number (0 or more).';

  @override
  String stockNoMatch(String code) {
    return 'No inventory item matches $code. Pick the item by hand.';
  }

  @override
  String stockScanned(String batch, String expiry) {
    return 'Batch $batch · expiry $expiry';
  }

  @override
  String get stockDrafts => 'Count drafts';

  @override
  String stockBatch(String batch) {
    return 'Batch $batch';
  }

  @override
  String stockExpiry(String expiry) {
    return 'Expiry $expiry';
  }

  @override
  String get stockPostAction => 'Post adjustment';

  @override
  String stockPostTitle(String item) {
    return 'Adjust $item?';
  }

  @override
  String stockPostBody(int onHand, int counted, int delta) {
    return 'Server on hand: $onHand. Counted: $counted. Adjustment: $delta.';
  }

  @override
  String get stockPosted => 'Posted';

  @override
  String get stockNoDifference =>
      'No difference from the server — nothing to post.';

  @override
  String get entityEncounter => 'consultation note';

  @override
  String get entityAppointment => 'appointment';

  @override
  String get entityCheckIn => 'check-in';

  @override
  String get devicesTitle => 'Medical devices';

  @override
  String get devicesIntro =>
      'Bluetooth BP monitors and pulse oximeters registered by the clinic. Every reading is reviewed by a clinician before it enters the record.';

  @override
  String get devicesNotValidated =>
      'No device model has been validated on real hardware yet. Simulated devices produce synthetic readings only.';

  @override
  String get devicesNone => 'No devices registered yet.';

  @override
  String get devicesRefresh => 'Refresh list';

  @override
  String get devicePaired => 'Paired with this phone';

  @override
  String get deviceNotPaired => 'Not paired with this phone';

  @override
  String get devicePair => 'Pair';

  @override
  String get deviceUnpair => 'Unpair';

  @override
  String get devicePairMismatch => 'That is not the registered device.';

  @override
  String get devicePairDone => 'Paired.';

  @override
  String get deviceRegister => 'Register a new device';

  @override
  String get deviceScan => 'Scan for devices';

  @override
  String get deviceScanNone => 'No device found nearby.';

  @override
  String get deviceLabel => 'Name (e.g. OPD room 1 BP monitor)';

  @override
  String get deviceRegistered => 'Registered and paired.';

  @override
  String get deviceSimulated => 'SIMULATED';

  @override
  String get deviceKindBp => 'BP monitor';

  @override
  String get deviceKindOximeter => 'Pulse oximeter';

  @override
  String get measureWithDevice => 'Measure with device';

  @override
  String measureFor(String patient) {
    return 'Measuring for: $patient';
  }

  @override
  String get measureNoPairedDevice =>
      'No paired device of this type. Pair one under Settings → Medical devices.';

  @override
  String get measureStart => 'Start measurement';

  @override
  String get measureWaiting =>
      'Waiting for the device… take the measurement on the device.';

  @override
  String get measureScenario => 'Simulator scenario';

  @override
  String measureRefused(String reason) {
    return 'Not saved: $reason';
  }

  @override
  String get measureSave => 'Save for clinician review';

  @override
  String get measureSaved =>
      'Saved on this phone; it will be sent for clinician review.';

  @override
  String measureFlags(String flags) {
    return 'Device notes: $flags';
  }

  @override
  String measureError(String error) {
    return 'Measurement failed: $error';
  }

  @override
  String get measureNotRecord =>
      'Not yet part of the record — a clinician must accept it.';

  @override
  String get reviewTitle => 'Device readings to review';

  @override
  String get reviewOpen => 'Review device readings';

  @override
  String get reviewNone => 'No readings waiting for review.';

  @override
  String get reviewAccept => 'Accept into record';

  @override
  String get reviewReject => 'Reject';

  @override
  String reviewConfirm(String patient) {
    return 'This reading belongs to $patient and was measured just now.';
  }

  @override
  String get reviewReason => 'Reason for rejecting';

  @override
  String get reviewAccepted => 'Accepted into the consultation\'s vitals.';

  @override
  String get reviewRejected => 'Rejected.';

  @override
  String reviewFailed(String error) {
    return 'Could not complete the review: $error';
  }

  @override
  String readingBp(String sys, String dia) {
    return 'BP $sys/$dia mmHg';
  }

  @override
  String readingPulse(String pulse) {
    return 'Pulse $pulse/min';
  }

  @override
  String readingSpo2(String spo2) {
    return 'SpO2 $spo2 %';
  }

  @override
  String get readingClockSkew => 'The device clock differs from the phone\'s.';
}
