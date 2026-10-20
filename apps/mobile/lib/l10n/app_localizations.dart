import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_hi.dart';
import 'app_localizations_mr.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('hi'),
    Locale('mr'),
  ];

  /// Product name — not translated
  ///
  /// In en, this message translates to:
  /// **'Aditya BioNova Smart HMS'**
  String get appTitle;

  /// No description provided for @appSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Doctor & field staff app'**
  String get appSubtitle;

  /// No description provided for @languageMenu.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageMenu;

  /// Follow the phone language setting
  ///
  /// In en, this message translates to:
  /// **'Device language'**
  String get languageDevice;

  /// No description provided for @settingsMenu.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsMenu;

  /// No description provided for @refresh.
  ///
  /// In en, this message translates to:
  /// **'Refresh'**
  String get refresh;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @back.
  ///
  /// In en, this message translates to:
  /// **'Back'**
  String get back;

  /// No description provided for @patient.
  ///
  /// In en, this message translates to:
  /// **'Patient'**
  String get patient;

  /// Clinic branch
  ///
  /// In en, this message translates to:
  /// **'Branch'**
  String get branch;

  /// No description provided for @pickPatientFirst.
  ///
  /// In en, this message translates to:
  /// **'Pick a patient first.'**
  String get pickPatientFirst;

  /// Counts of changes waiting on the device
  ///
  /// In en, this message translates to:
  /// **'Outbox — pending: {pending}, failed: {failed}, conflicted: {conflicted}'**
  String outboxCounts(int pending, int failed, int conflicted);

  /// No description provided for @outboxCountsShort.
  ///
  /// In en, this message translates to:
  /// **'Outbox — pending: {pending}, conflicted: {conflicted}'**
  String outboxCountsShort(int pending, int conflicted);

  /// Suffix after a patient registered offline
  ///
  /// In en, this message translates to:
  /// **'(pending sync)'**
  String get pendingSyncTag;

  /// No description provided for @syncedTag.
  ///
  /// In en, this message translates to:
  /// **'(synced)'**
  String get syncedTag;

  /// No description provided for @loginEmail.
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get loginEmail;

  /// No description provided for @loginPassword.
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get loginPassword;

  /// Organisation slug
  ///
  /// In en, this message translates to:
  /// **'Clinic slug (optional)'**
  String get loginSlug;

  /// No description provided for @loginSubmit.
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get loginSubmit;

  /// No description provided for @loginSigningIn.
  ///
  /// In en, this message translates to:
  /// **'Signing in…'**
  String get loginSigningIn;

  /// No description provided for @loginMfaTitle.
  ///
  /// In en, this message translates to:
  /// **'Two-step verification'**
  String get loginMfaTitle;

  /// No description provided for @loginMfaHelp.
  ///
  /// In en, this message translates to:
  /// **'Enter the 6-digit code from your authenticator app, or one of your recovery codes (xxxx-xxxx).'**
  String get loginMfaHelp;

  /// No description provided for @loginMfaCode.
  ///
  /// In en, this message translates to:
  /// **'Code'**
  String get loginMfaCode;

  /// No description provided for @loginVerify.
  ///
  /// In en, this message translates to:
  /// **'Verify'**
  String get loginVerify;

  /// No description provided for @loginVerifying.
  ///
  /// In en, this message translates to:
  /// **'Verifying…'**
  String get loginVerifying;

  /// No description provided for @loginMfaMissing.
  ///
  /// In en, this message translates to:
  /// **'Enter the code from your authenticator app.'**
  String get loginMfaMissing;

  /// No description provided for @loginMfaRejected.
  ///
  /// In en, this message translates to:
  /// **'That code was not accepted. Check the time on your phone or use a recovery code.'**
  String get loginMfaRejected;

  /// No description provided for @loginUnreachable.
  ///
  /// In en, this message translates to:
  /// **'Could not reach the server. Check the connection and try again.'**
  String get loginUnreachable;

  /// No description provided for @rateLimitedWait.
  ///
  /// In en, this message translates to:
  /// **'Too many attempts. Please wait and try again.'**
  String get rateLimitedWait;

  /// No description provided for @rateLimitedSeconds.
  ///
  /// In en, this message translates to:
  /// **'Too many attempts. Try again in {seconds} seconds.'**
  String rateLimitedSeconds(int seconds);

  /// No description provided for @rateLimitedMinutes.
  ///
  /// In en, this message translates to:
  /// **'Too many attempts. Try again in {minutes, plural, =1{1 minute} other{{minutes} minutes}}.'**
  String rateLimitedMinutes(int minutes);

  /// No description provided for @sessionExpiredNotice.
  ///
  /// In en, this message translates to:
  /// **'Your sign-in has expired. Work saved on this device is kept and syncs after you sign in.'**
  String get sessionExpiredNotice;

  /// No description provided for @lockedOutNotice.
  ///
  /// In en, this message translates to:
  /// **'Too many wrong PINs. Sign in online again — work saved on this device is kept.'**
  String get lockedOutNotice;

  /// No description provided for @pinSetTitle.
  ///
  /// In en, this message translates to:
  /// **'Set an app PIN'**
  String get pinSetTitle;

  /// No description provided for @pinUnlockTitle.
  ///
  /// In en, this message translates to:
  /// **'Enter your app PIN'**
  String get pinUnlockTitle;

  /// No description provided for @pinSetHelp.
  ///
  /// In en, this message translates to:
  /// **'Patient data on this device is protected by a PIN. You will need it to open the app, even with no network.'**
  String get pinSetHelp;

  /// No description provided for @worksOffline.
  ///
  /// In en, this message translates to:
  /// **'Works offline.'**
  String get worksOffline;

  /// No description provided for @pinLabel.
  ///
  /// In en, this message translates to:
  /// **'PIN'**
  String get pinLabel;

  /// No description provided for @pinRepeat.
  ///
  /// In en, this message translates to:
  /// **'Repeat PIN'**
  String get pinRepeat;

  /// No description provided for @pinSave.
  ///
  /// In en, this message translates to:
  /// **'Save PIN'**
  String get pinSave;

  /// No description provided for @pinUnlock.
  ///
  /// In en, this message translates to:
  /// **'Unlock'**
  String get pinUnlock;

  /// No description provided for @pinUsePassword.
  ///
  /// In en, this message translates to:
  /// **'Sign in with password instead'**
  String get pinUsePassword;

  /// No description provided for @pinRule.
  ///
  /// In en, this message translates to:
  /// **'Use 4 to 8 digits.'**
  String get pinRule;

  /// No description provided for @pinMismatch.
  ///
  /// In en, this message translates to:
  /// **'The two PINs do not match.'**
  String get pinMismatch;

  /// No description provided for @pinWrong.
  ///
  /// In en, this message translates to:
  /// **'Wrong PIN — {left, plural, =1{1 attempt} other{{left} attempts}} left.'**
  String pinWrong(int left);

  /// No description provided for @recoveryTitle.
  ///
  /// In en, this message translates to:
  /// **'Offline data could not be unlocked'**
  String get recoveryTitle;

  /// No description provided for @recoveryTitleFatal.
  ///
  /// In en, this message translates to:
  /// **'This build cannot start'**
  String get recoveryTitleFatal;

  /// No description provided for @recoveryBody.
  ///
  /// In en, this message translates to:
  /// **'The work saved on this device is encrypted with a key kept in this phone\'s secure hardware. The key or the data could not be read — this happens after restoring the app onto a new phone, or if the stored file was damaged.\n\nThe app will not continue without its offline storage, because new work would silently be lost. Try again first; if it keeps failing, reset the local data.'**
  String get recoveryBody;

  /// No description provided for @recoveryDetails.
  ///
  /// In en, this message translates to:
  /// **'Details: {details}'**
  String recoveryDetails(String details);

  /// No description provided for @recoveryRetry.
  ///
  /// In en, this message translates to:
  /// **'Try again'**
  String get recoveryRetry;

  /// No description provided for @recoveryReset.
  ///
  /// In en, this message translates to:
  /// **'Reset local data (unsynced items will be lost)'**
  String get recoveryReset;

  /// No description provided for @recoveryResetTitle.
  ///
  /// In en, this message translates to:
  /// **'Reset local data?'**
  String get recoveryResetTitle;

  /// No description provided for @recoveryResetBody.
  ///
  /// In en, this message translates to:
  /// **'Everything stored on this device by the app is deleted: registrations, queue entries, invoices and prescription drafts that have not synced are LOST and cannot be recovered. Data already on the server is not affected. You will sign in again afterwards.'**
  String get recoveryResetBody;

  /// No description provided for @recoveryResetConfirm.
  ///
  /// In en, this message translates to:
  /// **'Delete local data'**
  String get recoveryResetConfirm;

  /// Role as reported by the server (not translated)
  ///
  /// In en, this message translates to:
  /// **'HMS · {role}'**
  String homeTitle(String role);

  /// No description provided for @signOut.
  ///
  /// In en, this message translates to:
  /// **'Sign out'**
  String get signOut;

  /// No description provided for @signOutTitle.
  ///
  /// In en, this message translates to:
  /// **'Sign out of this device?'**
  String get signOutTitle;

  /// No description provided for @signOutTitleUnsynced.
  ///
  /// In en, this message translates to:
  /// **'Unsynced changes will be lost'**
  String get signOutTitleUnsynced;

  /// No description provided for @signOutBody.
  ///
  /// In en, this message translates to:
  /// **'The cached patient list, drafts and your PIN are removed from this device.'**
  String get signOutBody;

  /// No description provided for @signOutBodyUnsynced.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 change saved on this device has NOT reached the server yet.} other{{count} changes saved on this device have NOT reached the server yet.}} Signing out deletes them, together with the cached patient list and drafts. Sync first if you can.'**
  String signOutBodyUnsynced(int count);

  /// No description provided for @signOutDelete.
  ///
  /// In en, this message translates to:
  /// **'Delete and sign out'**
  String get signOutDelete;

  /// No description provided for @sessionExpiredBanner.
  ///
  /// In en, this message translates to:
  /// **'Signed out by the server. You can keep working offline; sign in again to sync.'**
  String get sessionExpiredBanner;

  /// OPD queue tab
  ///
  /// In en, this message translates to:
  /// **'Queue'**
  String get tabQueue;

  /// Patient registration tab
  ///
  /// In en, this message translates to:
  /// **'Register'**
  String get tabRegister;

  /// Prescription tab — Rx is understood by clinicians
  ///
  /// In en, this message translates to:
  /// **'Rx'**
  String get tabRx;

  /// No description provided for @tabFastRx.
  ///
  /// In en, this message translates to:
  /// **'Fast Rx'**
  String get tabFastRx;

  /// No description provided for @tabBilling.
  ///
  /// In en, this message translates to:
  /// **'Billing'**
  String get tabBilling;

  /// No description provided for @tabBill.
  ///
  /// In en, this message translates to:
  /// **'Bill'**
  String get tabBill;

  /// No description provided for @tabSync.
  ///
  /// In en, this message translates to:
  /// **'Sync'**
  String get tabSync;

  /// No description provided for @ruralMode.
  ///
  /// In en, this message translates to:
  /// **'Rural clinic mode'**
  String get ruralMode;

  /// No description provided for @ruralModeHelp.
  ///
  /// In en, this message translates to:
  /// **'Large buttons, bigger text, four steps'**
  String get ruralModeHelp;

  /// Product edition reported by the server
  ///
  /// In en, this message translates to:
  /// **'Edition: {edition}'**
  String editionLabel(String edition);

  /// No description provided for @mobileNotEnabled.
  ///
  /// In en, this message translates to:
  /// **'The mobile app is not part of your clinic\'s plan. Changes already saved on this device can still be synced from the Sync tab. Contact your administrator.'**
  String get mobileNotEnabled;

  /// No description provided for @queueTitle.
  ///
  /// In en, this message translates to:
  /// **'Offline queue entry'**
  String get queueTitle;

  /// No description provided for @queuePickBoth.
  ///
  /// In en, this message translates to:
  /// **'Pick a patient and a branch (need one sync).'**
  String get queuePickBoth;

  /// No description provided for @queueDuplicate.
  ///
  /// In en, this message translates to:
  /// **'Already queued for today — duplicate prevented.'**
  String get queueDuplicate;

  /// No description provided for @queueSaved.
  ///
  /// In en, this message translates to:
  /// **'Saved on device — pending sync ({count} in the outbox).'**
  String queueSaved(int count);

  /// No description provided for @queueAdd.
  ///
  /// In en, this message translates to:
  /// **'Add to queue (works offline)'**
  String get queueAdd;

  /// No description provided for @loadingPatients.
  ///
  /// In en, this message translates to:
  /// **'Loading patients…'**
  String get loadingPatients;

  /// No description provided for @noPatientsCached.
  ///
  /// In en, this message translates to:
  /// **'No patients cached yet — connect once to pull the directory, after which queue entries work offline.'**
  String get noPatientsCached;

  /// No description provided for @registerTitle.
  ///
  /// In en, this message translates to:
  /// **'Register patient (works offline)'**
  String get registerTitle;

  /// No description provided for @registerName.
  ///
  /// In en, this message translates to:
  /// **'Full name'**
  String get registerName;

  /// No description provided for @registerGender.
  ///
  /// In en, this message translates to:
  /// **'Gender'**
  String get registerGender;

  /// No description provided for @genderFemale.
  ///
  /// In en, this message translates to:
  /// **'Female'**
  String get genderFemale;

  /// No description provided for @genderMale.
  ///
  /// In en, this message translates to:
  /// **'Male'**
  String get genderMale;

  /// No description provided for @genderOther.
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get genderOther;

  /// No description provided for @genderUnknown.
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get genderUnknown;

  /// No description provided for @registerPhone.
  ///
  /// In en, this message translates to:
  /// **'Phone (optional)'**
  String get registerPhone;

  /// No description provided for @registerDobUnknown.
  ///
  /// In en, this message translates to:
  /// **'Date of birth — not known (estimated)'**
  String get registerDobUnknown;

  /// No description provided for @registerDob.
  ///
  /// In en, this message translates to:
  /// **'Date of birth — {date}'**
  String registerDob(String date);

  /// No description provided for @pick.
  ///
  /// In en, this message translates to:
  /// **'Pick'**
  String get pick;

  /// No description provided for @registerAllergies.
  ///
  /// In en, this message translates to:
  /// **'Known allergies (write what the family reports)'**
  String get registerAllergies;

  /// No description provided for @registerAdd.
  ///
  /// In en, this message translates to:
  /// **'Register (works offline)'**
  String get registerAdd;

  /// No description provided for @registerNameRequired.
  ///
  /// In en, this message translates to:
  /// **'Enter the patient’s full name.'**
  String get registerNameRequired;

  /// No description provided for @registerLooksDuplicate.
  ///
  /// In en, this message translates to:
  /// **'Looks like an existing patient — duplicate prevented (pick them from the list, or edit the details to register anyway).'**
  String get registerLooksDuplicate;

  /// No description provided for @registerDuplicateQueued.
  ///
  /// In en, this message translates to:
  /// **'Identical registration already queued — duplicate prevented.'**
  String get registerDuplicateQueued;

  /// No description provided for @registerSaved.
  ///
  /// In en, this message translates to:
  /// **'Saved on device — pending sync. Assigned to today’s queue as soon as it syncs.'**
  String get registerSaved;

  /// No description provided for @billingTitle.
  ///
  /// In en, this message translates to:
  /// **'Raise invoice (works offline)'**
  String get billingTitle;

  /// Invoice line type
  ///
  /// In en, this message translates to:
  /// **'Line type'**
  String get billingLineType;

  /// No description provided for @itemConsultation.
  ///
  /// In en, this message translates to:
  /// **'Consultation'**
  String get itemConsultation;

  /// No description provided for @itemProcedure.
  ///
  /// In en, this message translates to:
  /// **'Procedure'**
  String get itemProcedure;

  /// No description provided for @itemPharmacy.
  ///
  /// In en, this message translates to:
  /// **'Pharmacy'**
  String get itemPharmacy;

  /// No description provided for @itemLab.
  ///
  /// In en, this message translates to:
  /// **'Lab'**
  String get itemLab;

  /// No description provided for @itemOther.
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get itemOther;

  /// No description provided for @billingDescription.
  ///
  /// In en, this message translates to:
  /// **'Description'**
  String get billingDescription;

  /// No description provided for @billingQuantity.
  ///
  /// In en, this message translates to:
  /// **'Quantity'**
  String get billingQuantity;

  /// No description provided for @billingUnitPrice.
  ///
  /// In en, this message translates to:
  /// **'Unit price'**
  String get billingUnitPrice;

  /// No description provided for @billingAdd.
  ///
  /// In en, this message translates to:
  /// **'Save invoice (works offline)'**
  String get billingAdd;

  /// No description provided for @billingDescribe.
  ///
  /// In en, this message translates to:
  /// **'Describe the line being billed.'**
  String get billingDescribe;

  /// No description provided for @billingQtyPrice.
  ///
  /// In en, this message translates to:
  /// **'Quantity and unit price are required.'**
  String get billingQtyPrice;

  /// No description provided for @billingDuplicate.
  ///
  /// In en, this message translates to:
  /// **'Identical invoice already queued — duplicate prevented.'**
  String get billingDuplicate;

  /// No description provided for @billingSaved.
  ///
  /// In en, this message translates to:
  /// **'Invoice saved on device — pending sync. Totals and the invoice number are computed by the server.'**
  String get billingSaved;

  /// No description provided for @rxTitle.
  ///
  /// In en, this message translates to:
  /// **'Fast Rx draft (works offline)'**
  String get rxTitle;

  /// No description provided for @rxMedicine.
  ///
  /// In en, this message translates to:
  /// **'Medicine (validated catalog)'**
  String get rxMedicine;

  /// Example dose stays in mg
  ///
  /// In en, this message translates to:
  /// **'Dose (500 mg)'**
  String get rxDose;

  /// BD/TDS abbreviations are kept as written on Indian prescriptions
  ///
  /// In en, this message translates to:
  /// **'Frequency (BD)'**
  String get rxFrequency;

  /// No description provided for @rxDays.
  ///
  /// In en, this message translates to:
  /// **'Days'**
  String get rxDays;

  /// No description provided for @rxDispense.
  ///
  /// In en, this message translates to:
  /// **'Units to dispense (optional)'**
  String get rxDispense;

  /// No description provided for @rxDispenseHelp.
  ///
  /// In en, this message translates to:
  /// **'Pharmacy cannot hand out more than this in total'**
  String get rxDispenseHelp;

  /// No description provided for @rxAddItem.
  ///
  /// In en, this message translates to:
  /// **'Add medicine'**
  String get rxAddItem;

  /// Drug name and dose are never translated
  ///
  /// In en, this message translates to:
  /// **'{drug} — {dose}, {frequency}, {days} days'**
  String rxItemLine(String drug, String dose, String frequency, String days);

  /// No description provided for @rxItemDispense.
  ///
  /// In en, this message translates to:
  /// **' · dispense {quantity}'**
  String rxItemDispense(String quantity);

  /// No description provided for @rxDiagnosis.
  ///
  /// In en, this message translates to:
  /// **'Diagnosis (text)'**
  String get rxDiagnosis;

  /// No description provided for @rxSave.
  ///
  /// In en, this message translates to:
  /// **'Save draft (works offline)'**
  String get rxSave;

  /// No description provided for @rxDrafts.
  ///
  /// In en, this message translates to:
  /// **'Drafts on this device'**
  String get rxDrafts;

  /// No description provided for @rxNoDrafts.
  ///
  /// In en, this message translates to:
  /// **'No drafts yet — they are kept here with their sync state.'**
  String get rxNoDrafts;

  /// No description provided for @rxNoCatalog.
  ///
  /// In en, this message translates to:
  /// **'No drug catalog cached yet — connect once.'**
  String get rxNoCatalog;

  /// No description provided for @rxRequired.
  ///
  /// In en, this message translates to:
  /// **'Dose, frequency and duration are required.'**
  String get rxRequired;

  /// No description provided for @rxDispenseRange.
  ///
  /// In en, this message translates to:
  /// **'Quantity to dispense must be 1–10000 units (or leave it blank).'**
  String get rxDispenseRange;

  /// No description provided for @rxAddOne.
  ///
  /// In en, this message translates to:
  /// **'Add at least one medicine.'**
  String get rxAddOne;

  /// No description provided for @rxDuplicate.
  ///
  /// In en, this message translates to:
  /// **'Identical draft already queued — duplicate prevented.'**
  String get rxDuplicate;

  /// No description provided for @rxSaved.
  ///
  /// In en, this message translates to:
  /// **'Draft saved on device — pending sync. Sign it after it syncs (the allergy check runs on the server).'**
  String get rxSaved;

  /// No description provided for @rxSigned.
  ///
  /// In en, this message translates to:
  /// **'Prescription signed.'**
  String get rxSigned;

  /// No description provided for @rxSign.
  ///
  /// In en, this message translates to:
  /// **'Sign'**
  String get rxSign;

  /// No description provided for @rxSignAfterSync.
  ///
  /// In en, this message translates to:
  /// **'Sign (after sync)'**
  String get rxSignAfterSync;

  /// No description provided for @rxDraftLine.
  ///
  /// In en, this message translates to:
  /// **'{drug} {dose} {frequency} {days}d'**
  String rxDraftLine(String drug, String dose, String frequency, String days);

  /// No description provided for @rxQuickFrequency.
  ///
  /// In en, this message translates to:
  /// **'Tap a frequency'**
  String get rxQuickFrequency;

  /// No description provided for @rxQuickDuration.
  ///
  /// In en, this message translates to:
  /// **'Tap the number of days'**
  String get rxQuickDuration;

  /// OD
  ///
  /// In en, this message translates to:
  /// **'once a day'**
  String get freqOD;

  /// BD
  ///
  /// In en, this message translates to:
  /// **'twice a day'**
  String get freqBD;

  /// TDS
  ///
  /// In en, this message translates to:
  /// **'three times a day'**
  String get freqTDS;

  /// QID
  ///
  /// In en, this message translates to:
  /// **'four times a day'**
  String get freqQID;

  /// HS
  ///
  /// In en, this message translates to:
  /// **'at bedtime'**
  String get freqHS;

  /// SOS
  ///
  /// In en, this message translates to:
  /// **'only when needed'**
  String get freqSOS;

  /// No description provided for @daysCount.
  ///
  /// In en, this message translates to:
  /// **'{days, plural, =1{1 day} other{{days} days}}'**
  String daysCount(int days);

  /// No description provided for @stateSigned.
  ///
  /// In en, this message translates to:
  /// **'Signed'**
  String get stateSigned;

  /// No description provided for @stateConflict.
  ///
  /// In en, this message translates to:
  /// **'Conflict — needs you'**
  String get stateConflict;

  /// No description provided for @stateSavedPending.
  ///
  /// In en, this message translates to:
  /// **'Saved on device · Pending sync'**
  String get stateSavedPending;

  /// No description provided for @stateDiscarded.
  ///
  /// In en, this message translates to:
  /// **'Discarded — not sent'**
  String get stateDiscarded;

  /// No description provided for @stateSynced.
  ///
  /// In en, this message translates to:
  /// **'Synced'**
  String get stateSynced;

  /// No description provided for @opPending.
  ///
  /// In en, this message translates to:
  /// **'Pending sync'**
  String get opPending;

  /// No description provided for @opPendingRetry.
  ///
  /// In en, this message translates to:
  /// **'Pending sync · retry {attempt}'**
  String opPendingRetry(int attempt);

  /// No description provided for @opSyncing.
  ///
  /// In en, this message translates to:
  /// **'Syncing…'**
  String get opSyncing;

  /// No description provided for @opFailed.
  ///
  /// In en, this message translates to:
  /// **'Not sent yet — retries automatically'**
  String get opFailed;

  /// No description provided for @opFailedAttempt.
  ///
  /// In en, this message translates to:
  /// **'Not sent yet — retries automatically (attempt {attempt})'**
  String opFailedAttempt(int attempt);

  /// No description provided for @savedOnDevice.
  ///
  /// In en, this message translates to:
  /// **'Saved on device · {state}'**
  String savedOnDevice(String state);

  /// No description provided for @syncTitle.
  ///
  /// In en, this message translates to:
  /// **'Sync centre'**
  String get syncTitle;

  /// No description provided for @syncCounts.
  ///
  /// In en, this message translates to:
  /// **'pending: {pending} · failed: {failed} · conflicted: {conflicted}'**
  String syncCounts(int pending, int failed, int conflicted);

  /// No description provided for @syncNextRetry.
  ///
  /// In en, this message translates to:
  /// **'Automatic retry from {time}'**
  String syncNextRetry(String time);

  /// No description provided for @syncNow.
  ///
  /// In en, this message translates to:
  /// **'Sync now'**
  String get syncNow;

  /// No description provided for @syncRetryFailed.
  ///
  /// In en, this message translates to:
  /// **'Retry failed now'**
  String get syncRetryFailed;

  /// No description provided for @syncResult.
  ///
  /// In en, this message translates to:
  /// **'pushed {pushed} · conflicts {conflicts} · failed {failed}'**
  String syncResult(int pushed, int conflicts, int failed);

  /// No description provided for @syncWaiting.
  ///
  /// In en, this message translates to:
  /// **' · waiting {count}'**
  String syncWaiting(int count);

  /// No description provided for @syncStopped.
  ///
  /// In en, this message translates to:
  /// **' · stopped (sign in again)'**
  String get syncStopped;

  /// No description provided for @syncedEntity.
  ///
  /// In en, this message translates to:
  /// **'Synced · {entity}'**
  String syncedEntity(String entity);

  /// No description provided for @syncPersistError.
  ///
  /// In en, this message translates to:
  /// **'Could not save to device storage: {error}'**
  String syncPersistError(String error);

  /// No description provided for @syncQueued.
  ///
  /// In en, this message translates to:
  /// **'Queued on this device'**
  String get syncQueued;

  /// No description provided for @syncNothingQueued.
  ///
  /// In en, this message translates to:
  /// **'Nothing queued — every change has reached the server.'**
  String get syncNothingQueued;

  /// No description provided for @syncNoConflicts.
  ///
  /// In en, this message translates to:
  /// **'No conflicts — local and server agree.'**
  String get syncNoConflicts;

  /// No description provided for @conflictDiscard.
  ///
  /// In en, this message translates to:
  /// **'Discard (server wins here)'**
  String get conflictDiscard;

  /// No description provided for @conflictRegisterAnyway.
  ///
  /// In en, this message translates to:
  /// **'Keep local (register anyway)'**
  String get conflictRegisterAnyway;

  /// No description provided for @conflictClaim.
  ///
  /// In en, this message translates to:
  /// **'Keep local (send as me)'**
  String get conflictClaim;

  /// No description provided for @conflictKeep.
  ///
  /// In en, this message translates to:
  /// **'Keep local (re-send)'**
  String get conflictKeep;

  /// No description provided for @registerAnywayTitle.
  ///
  /// In en, this message translates to:
  /// **'Register as a NEW patient?'**
  String get registerAnywayTitle;

  /// No description provided for @registerAnywayBody.
  ///
  /// In en, this message translates to:
  /// **'The server found existing patient(s) that look like {name}. Only continue if you have checked this is a different person — a duplicate record splits the patient\'s history.'**
  String registerAnywayBody(String name);

  /// No description provided for @registerAnywayAction.
  ///
  /// In en, this message translates to:
  /// **'Register anyway'**
  String get registerAnywayAction;

  /// No description provided for @registerAnywayNotice.
  ///
  /// In en, this message translates to:
  /// **'Will register {name} as a new patient on the next sync.'**
  String registerAnywayNotice(String name);

  /// No description provided for @thisPatient.
  ///
  /// In en, this message translates to:
  /// **'this patient'**
  String get thisPatient;

  /// No description provided for @claimTitle.
  ///
  /// In en, this message translates to:
  /// **'Send under your account?'**
  String get claimTitle;

  /// No description provided for @claimBody.
  ///
  /// In en, this message translates to:
  /// **'This change was saved before the app recorded who made it. Send it only if you made it.'**
  String get claimBody;

  /// No description provided for @claimAction.
  ///
  /// In en, this message translates to:
  /// **'Send as me'**
  String get claimAction;

  /// No description provided for @discardTitle.
  ///
  /// In en, this message translates to:
  /// **'Discard {entity} and {count} more?'**
  String discardTitle(String entity, int count);

  /// No description provided for @discardBody.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{1 queued change ({what}) refers to this {entity} and can never be sent without it. It will be discarded too.} other{{count} queued changes ({what}) refer to this {entity} and can never be sent without it. They will be discarded too.}}'**
  String discardBody(int count, String what, String entity);

  /// No description provided for @discardAll.
  ///
  /// In en, this message translates to:
  /// **'Discard all'**
  String get discardAll;

  /// No description provided for @discardedOne.
  ///
  /// In en, this message translates to:
  /// **'Discarded: {entity}.'**
  String discardedOne(String entity);

  /// No description provided for @discardedMany.
  ///
  /// In en, this message translates to:
  /// **'Discarded: {entity} and {count, plural, =1{1 dependent change} other{{count} dependent changes}}.'**
  String discardedMany(String entity, int count);

  /// Kind of queued change
  ///
  /// In en, this message translates to:
  /// **'patient'**
  String get entityPatient;

  /// No description provided for @entityQueueEntry.
  ///
  /// In en, this message translates to:
  /// **'queue entry'**
  String get entityQueueEntry;

  /// No description provided for @entityInvoice.
  ///
  /// In en, this message translates to:
  /// **'invoice'**
  String get entityInvoice;

  /// No description provided for @entityPrescription.
  ///
  /// In en, this message translates to:
  /// **'prescription'**
  String get entityPrescription;

  /// No description provided for @conflictVersion.
  ///
  /// In en, this message translates to:
  /// **'The record changed on the server'**
  String get conflictVersion;

  /// No description provided for @conflictPolicy.
  ///
  /// In en, this message translates to:
  /// **'The server refused this change'**
  String get conflictPolicy;

  /// No description provided for @conflictAuth.
  ///
  /// In en, this message translates to:
  /// **'Sign in again to continue'**
  String get conflictAuth;

  /// No description provided for @conflictDuplicate.
  ///
  /// In en, this message translates to:
  /// **'Possible duplicate registration'**
  String get conflictDuplicate;

  /// No description provided for @conflictWrongUser.
  ///
  /// In en, this message translates to:
  /// **'Created by another user on this device'**
  String get conflictWrongUser;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'hi', 'mr'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'hi':
      return AppLocalizationsHi();
    case 'mr':
      return AppLocalizationsMr();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
