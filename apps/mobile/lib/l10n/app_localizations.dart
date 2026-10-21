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

  /// No description provided for @openSourceLicences.
  ///
  /// In en, this message translates to:
  /// **'Open-source licences'**
  String get openSourceLicences;

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

  /// No description provided for @statusOnline.
  ///
  /// In en, this message translates to:
  /// **'Online'**
  String get statusOnline;

  /// No description provided for @statusOffline.
  ///
  /// In en, this message translates to:
  /// **'Offline'**
  String get statusOffline;

  /// No description provided for @statusSavedOnDevice.
  ///
  /// In en, this message translates to:
  /// **'Saved on device'**
  String get statusSavedOnDevice;

  /// No description provided for @statusPendingSync.
  ///
  /// In en, this message translates to:
  /// **'Pending sync'**
  String get statusPendingSync;

  /// No description provided for @statusSyncing.
  ///
  /// In en, this message translates to:
  /// **'Syncing'**
  String get statusSyncing;

  /// No description provided for @statusSynced.
  ///
  /// In en, this message translates to:
  /// **'Synced'**
  String get statusSynced;

  /// No description provided for @statusConflict.
  ///
  /// In en, this message translates to:
  /// **'Conflict'**
  String get statusConflict;

  /// No description provided for @statusActionRequired.
  ///
  /// In en, this message translates to:
  /// **'Action required'**
  String get statusActionRequired;

  /// No description provided for @statusCount.
  ///
  /// In en, this message translates to:
  /// **'{status}: {count}'**
  String statusCount(String status, int count);

  /// No description provided for @globalToSync.
  ///
  /// In en, this message translates to:
  /// **'{count} to sync'**
  String globalToSync(int count);

  /// No description provided for @globalConflicts.
  ///
  /// In en, this message translates to:
  /// **'{count} in conflict'**
  String globalConflicts(int count);

  /// No description provided for @globalNeedAction.
  ///
  /// In en, this message translates to:
  /// **'{count} need action'**
  String globalNeedAction(int count);

  /// No description provided for @globalOfflineSaved.
  ///
  /// In en, this message translates to:
  /// **'Offline · {count} saved on device'**
  String globalOfflineSaved(int count);

  /// No description provided for @globalAllSynced.
  ///
  /// In en, this message translates to:
  /// **'All synced'**
  String get globalAllSynced;

  /// No description provided for @needsConnection.
  ///
  /// In en, this message translates to:
  /// **'Needs connection — will not be finalised offline'**
  String get needsConnection;

  /// No description provided for @needsConnectionTitle.
  ///
  /// In en, this message translates to:
  /// **'Needs connection'**
  String get needsConnectionTitle;

  /// No description provided for @needsConnectionReports.
  ///
  /// In en, this message translates to:
  /// **'Reports are calculated by the server and are not stored on this device.'**
  String get needsConnectionReports;

  /// No description provided for @errNetwork.
  ///
  /// In en, this message translates to:
  /// **'No connection — it will be retried automatically.'**
  String get errNetwork;

  /// No description provided for @errServer.
  ///
  /// In en, this message translates to:
  /// **'Server problem — it will be retried automatically.'**
  String get errServer;

  /// No description provided for @errBusy.
  ///
  /// In en, this message translates to:
  /// **'Server busy — it will be retried a little later.'**
  String get errBusy;

  /// No description provided for @errForbidden.
  ///
  /// In en, this message translates to:
  /// **'Not permitted for your account: {detail}'**
  String errForbidden(String detail);

  /// No description provided for @errInvalid.
  ///
  /// In en, this message translates to:
  /// **'The server did not accept the data: {detail}'**
  String errInvalid(String detail);

  /// No description provided for @errMaxAttempts.
  ///
  /// In en, this message translates to:
  /// **'Tried {count} times without success — automatic retries stopped. Tap Retry now.'**
  String errMaxAttempts(int count);

  /// No description provided for @retryNow.
  ///
  /// In en, this message translates to:
  /// **'Retry now'**
  String get retryNow;

  /// No description provided for @waitingFor.
  ///
  /// In en, this message translates to:
  /// **'Waiting for the {entity} to sync first'**
  String waitingFor(String entity);

  /// No description provided for @blockedBy.
  ///
  /// In en, this message translates to:
  /// **'Blocked: the {entity} it depends on needs your action'**
  String blockedBy(String entity);

  /// No description provided for @orphanedExplain.
  ///
  /// In en, this message translates to:
  /// **'It refers to a record that was discarded — it can never be sent as it is.'**
  String get orphanedExplain;

  /// No description provided for @syncAttention.
  ///
  /// In en, this message translates to:
  /// **'Needs your attention'**
  String get syncAttention;

  /// No description provided for @storageTitle.
  ///
  /// In en, this message translates to:
  /// **'Storage on this device'**
  String get storageTitle;

  /// No description provided for @storageUsage.
  ///
  /// In en, this message translates to:
  /// **'About {kb} KB encrypted · {patients} cached patients · {queued} queued changes'**
  String storageUsage(int kb, int patients, int queued);

  /// No description provided for @clearCacheAction.
  ///
  /// In en, this message translates to:
  /// **'Clear cached patient data'**
  String get clearCacheAction;

  /// No description provided for @clearCacheTitle.
  ///
  /// In en, this message translates to:
  /// **'Clear cached patients?'**
  String get clearCacheTitle;

  /// No description provided for @clearCacheBody.
  ///
  /// In en, this message translates to:
  /// **'Patients downloaded from the server are removed from this device. Patients registered here and not yet synced are kept. They download again next time you are online.'**
  String get clearCacheBody;

  /// No description provided for @clearCacheDone.
  ///
  /// In en, this message translates to:
  /// **'{count} cached patients removed from this device.'**
  String clearCacheDone(int count);

  /// No description provided for @deviceSignedOutByAdmin.
  ///
  /// In en, this message translates to:
  /// **'This device was signed out by an administrator. Patient data was removed from it; unsynced work is sealed on the device and comes back when the same user signs in again.'**
  String get deviceSignedOutByAdmin;

  /// No description provided for @quarantineTitle.
  ///
  /// In en, this message translates to:
  /// **'{count} unsynced items from a signed-out user are sealed on this device'**
  String quarantineTitle(int count);

  /// No description provided for @quarantineBody.
  ///
  /// In en, this message translates to:
  /// **'They cannot be viewed. They sync when that user signs in again on this device.'**
  String get quarantineBody;

  /// No description provided for @quarantineDiscardAction.
  ///
  /// In en, this message translates to:
  /// **'Discard sealed items'**
  String get quarantineDiscardAction;

  /// No description provided for @quarantineDiscardTitle.
  ///
  /// In en, this message translates to:
  /// **'Discard {count} sealed items?'**
  String quarantineDiscardTitle(int count);

  /// No description provided for @quarantineDiscardBody.
  ///
  /// In en, this message translates to:
  /// **'They were never sent to the server and cannot be recovered after this.'**
  String get quarantineDiscardBody;

  /// No description provided for @quarantineDiscarded.
  ///
  /// In en, this message translates to:
  /// **'Sealed items discarded.'**
  String get quarantineDiscarded;

  /// No description provided for @conflictReview.
  ///
  /// In en, this message translates to:
  /// **'Review'**
  String get conflictReview;

  /// No description provided for @conflictMine.
  ///
  /// In en, this message translates to:
  /// **'Saved on this device'**
  String get conflictMine;

  /// No description provided for @conflictServer.
  ///
  /// In en, this message translates to:
  /// **'On the server'**
  String get conflictServer;

  /// No description provided for @conflictSendMine.
  ///
  /// In en, this message translates to:
  /// **'Send mine again'**
  String get conflictSendMine;

  /// No description provided for @conflictSendMineTitle.
  ///
  /// In en, this message translates to:
  /// **'Send your version again?'**
  String get conflictSendMineTitle;

  /// No description provided for @conflictSendMineBody.
  ///
  /// In en, this message translates to:
  /// **'The server record changed after you saved this. Sending again does not overwrite silently — the server checks it again and may refuse it.'**
  String get conflictSendMineBody;

  /// No description provided for @conflictSentAgain.
  ///
  /// In en, this message translates to:
  /// **'Queued to send again.'**
  String get conflictSentAgain;

  /// No description provided for @useServerVersion.
  ///
  /// In en, this message translates to:
  /// **'Use the server version'**
  String get useServerVersion;

  /// No description provided for @versionTitle.
  ///
  /// In en, this message translates to:
  /// **'Changed on the server'**
  String get versionTitle;

  /// No description provided for @versionExplain.
  ///
  /// In en, this message translates to:
  /// **'Someone changed this record on the server after you saved your change. Compare and choose — nothing is overwritten automatically.'**
  String get versionExplain;

  /// No description provided for @dupTitle.
  ///
  /// In en, this message translates to:
  /// **'Possible duplicate patient'**
  String get dupTitle;

  /// No description provided for @dupExplain.
  ///
  /// In en, this message translates to:
  /// **'The server already has a similar patient. Choose: keep yours as a new patient, use the existing record, or merge by reviewing each field.'**
  String get dupExplain;

  /// No description provided for @dupMatchedOn.
  ///
  /// In en, this message translates to:
  /// **'Matched on: {fields}'**
  String dupMatchedOn(String fields);

  /// No description provided for @keepMineNew.
  ///
  /// In en, this message translates to:
  /// **'Keep mine as a new patient'**
  String get keepMineNew;

  /// No description provided for @useServerAction.
  ///
  /// In en, this message translates to:
  /// **'Use this record'**
  String get useServerAction;

  /// No description provided for @useServerTitle.
  ///
  /// In en, this message translates to:
  /// **'Use {patient}?'**
  String useServerTitle(String patient);

  /// No description provided for @useServerBody.
  ///
  /// In en, this message translates to:
  /// **'Your registration will not be sent. {count} queued changes for this patient will be linked to the existing record instead.'**
  String useServerBody(int count);

  /// No description provided for @useServerDone.
  ///
  /// In en, this message translates to:
  /// **'Linked to {patient}.'**
  String useServerDone(String patient);

  /// No description provided for @mergeAction.
  ///
  /// In en, this message translates to:
  /// **'Merge by review'**
  String get mergeAction;

  /// No description provided for @mergeTitle.
  ///
  /// In en, this message translates to:
  /// **'Merge by review'**
  String get mergeTitle;

  /// No description provided for @mergeExplain.
  ///
  /// In en, this message translates to:
  /// **'The server record was just read again. Tick only the fields to copy from your registration; nothing is selected for you.'**
  String get mergeExplain;

  /// No description provided for @mergeNothing.
  ///
  /// In en, this message translates to:
  /// **'No differing fields — the existing record will be used.'**
  String get mergeNothing;

  /// No description provided for @mergeFieldLine.
  ///
  /// In en, this message translates to:
  /// **'Server: {server} → Mine: {mine}'**
  String mergeFieldLine(String server, String mine);

  /// No description provided for @mergeApply.
  ///
  /// In en, this message translates to:
  /// **'Copy {count} fields and use the record'**
  String mergeApply(int count);

  /// No description provided for @mergeDone.
  ///
  /// In en, this message translates to:
  /// **'{count} fields copied to {uhid}.'**
  String mergeDone(int count, String uhid);

  /// No description provided for @fieldDob.
  ///
  /// In en, this message translates to:
  /// **'Date of birth'**
  String get fieldDob;

  /// No description provided for @fieldAddress.
  ///
  /// In en, this message translates to:
  /// **'Address'**
  String get fieldAddress;

  /// No description provided for @fieldBloodGroup.
  ///
  /// In en, this message translates to:
  /// **'Blood group'**
  String get fieldBloodGroup;

  /// No description provided for @detailRequest.
  ///
  /// In en, this message translates to:
  /// **'Request'**
  String get detailRequest;

  /// No description provided for @detailState.
  ///
  /// In en, this message translates to:
  /// **'State'**
  String get detailState;

  /// No description provided for @detailCreated.
  ///
  /// In en, this message translates to:
  /// **'Saved at'**
  String get detailCreated;

  /// No description provided for @detailAttempts.
  ///
  /// In en, this message translates to:
  /// **'Attempts'**
  String get detailAttempts;

  /// No description provided for @detailNextRetry.
  ///
  /// In en, this message translates to:
  /// **'Next retry'**
  String get detailNextRetry;

  /// No description provided for @detailKey.
  ///
  /// In en, this message translates to:
  /// **'Idempotency key'**
  String get detailKey;

  /// No description provided for @detailHttp.
  ///
  /// In en, this message translates to:
  /// **'Server answer'**
  String get detailHttp;

  /// No description provided for @detailError.
  ///
  /// In en, this message translates to:
  /// **'Last problem'**
  String get detailError;

  /// No description provided for @detailDepends.
  ///
  /// In en, this message translates to:
  /// **'Depends on'**
  String get detailDepends;

  /// No description provided for @detailNoLongerQueued.
  ///
  /// In en, this message translates to:
  /// **'This change is no longer in the queue.'**
  String get detailNoLongerQueued;

  /// No description provided for @tabOverview.
  ///
  /// In en, this message translates to:
  /// **'Overview'**
  String get tabOverview;

  /// No description provided for @tabConsult.
  ///
  /// In en, this message translates to:
  /// **'Consult'**
  String get tabConsult;

  /// No description provided for @tabPatients.
  ///
  /// In en, this message translates to:
  /// **'Patients'**
  String get tabPatients;

  /// No description provided for @tabAppointments.
  ///
  /// In en, this message translates to:
  /// **'Appointments'**
  String get tabAppointments;

  /// No description provided for @tabStock.
  ///
  /// In en, this message translates to:
  /// **'Stock'**
  String get tabStock;

  /// No description provided for @noTabsForRole.
  ///
  /// In en, this message translates to:
  /// **'Nothing is enabled for your role on mobile. Ask your administrator.'**
  String get noTabsForRole;

  /// No description provided for @patientsSearch.
  ///
  /// In en, this message translates to:
  /// **'Search name, UHID or phone'**
  String get patientsSearch;

  /// No description provided for @patientsSearchServer.
  ///
  /// In en, this message translates to:
  /// **'Search the server'**
  String get patientsSearchServer;

  /// No description provided for @patientsCachedNote.
  ///
  /// In en, this message translates to:
  /// **'{count} patients on this device (only ones you have opened online; encrypted)'**
  String patientsCachedNote(int count);

  /// No description provided for @consultTitle.
  ///
  /// In en, this message translates to:
  /// **'Consultation note (draft — works offline)'**
  String get consultTitle;

  /// No description provided for @consultComplaint.
  ///
  /// In en, this message translates to:
  /// **'Chief complaint'**
  String get consultComplaint;

  /// No description provided for @consultHistory.
  ///
  /// In en, this message translates to:
  /// **'History'**
  String get consultHistory;

  /// No description provided for @consultExam.
  ///
  /// In en, this message translates to:
  /// **'Examination'**
  String get consultExam;

  /// No description provided for @consultSave.
  ///
  /// In en, this message translates to:
  /// **'Save note draft'**
  String get consultSave;

  /// No description provided for @consultUpdate.
  ///
  /// In en, this message translates to:
  /// **'Update draft'**
  String get consultUpdate;

  /// No description provided for @consultEdit.
  ///
  /// In en, this message translates to:
  /// **'Edit'**
  String get consultEdit;

  /// No description provided for @consultSaved.
  ///
  /// In en, this message translates to:
  /// **'Note draft saved on device — pending sync.'**
  String get consultSaved;

  /// No description provided for @consultDuplicate.
  ///
  /// In en, this message translates to:
  /// **'A note draft for this patient today is already queued (duplicate prevented).'**
  String get consultDuplicate;

  /// No description provided for @consultComplaintRequired.
  ///
  /// In en, this message translates to:
  /// **'Enter the chief complaint.'**
  String get consultComplaintRequired;

  /// No description provided for @consultNoBranch.
  ///
  /// In en, this message translates to:
  /// **'No branch on this device yet — open Queue once while online.'**
  String get consultNoBranch;

  /// No description provided for @consultAlreadySent.
  ///
  /// In en, this message translates to:
  /// **'This draft was already sent — it can no longer be edited on the device.'**
  String get consultAlreadySent;

  /// No description provided for @consultDrafts.
  ///
  /// In en, this message translates to:
  /// **'Note drafts'**
  String get consultDrafts;

  /// No description provided for @consultNoDrafts.
  ///
  /// In en, this message translates to:
  /// **'No note drafts on this device.'**
  String get consultNoDrafts;

  /// No description provided for @consultComplete.
  ///
  /// In en, this message translates to:
  /// **'Complete consultation'**
  String get consultComplete;

  /// No description provided for @consultCompleteAfterSync.
  ///
  /// In en, this message translates to:
  /// **'Complete (after sync)'**
  String get consultCompleteAfterSync;

  /// No description provided for @consultCompleted.
  ///
  /// In en, this message translates to:
  /// **'Consultation completed on the server.'**
  String get consultCompleted;

  /// No description provided for @appointmentsTitle.
  ///
  /// In en, this message translates to:
  /// **'Book appointment (works offline)'**
  String get appointmentsTitle;

  /// No description provided for @appointmentDay.
  ///
  /// In en, this message translates to:
  /// **'Day: {day}'**
  String appointmentDay(String day);

  /// No description provided for @appointmentReason.
  ///
  /// In en, this message translates to:
  /// **'Reason'**
  String get appointmentReason;

  /// No description provided for @appointmentSave.
  ///
  /// In en, this message translates to:
  /// **'Save appointment draft'**
  String get appointmentSave;

  /// No description provided for @appointmentSaved.
  ///
  /// In en, this message translates to:
  /// **'Appointment saved on device — pending sync. The server checks the slot when it syncs.'**
  String get appointmentSaved;

  /// No description provided for @appointmentDuplicate.
  ///
  /// In en, this message translates to:
  /// **'This appointment is already queued (duplicate prevented).'**
  String get appointmentDuplicate;

  /// No description provided for @appointmentDrafts.
  ///
  /// In en, this message translates to:
  /// **'Appointment drafts'**
  String get appointmentDrafts;

  /// No description provided for @appointmentsToday.
  ///
  /// In en, this message translates to:
  /// **'Today\'s appointments (server)'**
  String get appointmentsToday;

  /// No description provided for @appointmentsNone.
  ///
  /// In en, this message translates to:
  /// **'No appointments today.'**
  String get appointmentsNone;

  /// No description provided for @queueToday.
  ///
  /// In en, this message translates to:
  /// **'Today\'s queue (server)'**
  String get queueToday;

  /// No description provided for @queueTodayShow.
  ///
  /// In en, this message translates to:
  /// **'Show'**
  String get queueTodayShow;

  /// No description provided for @checkInScan.
  ///
  /// In en, this message translates to:
  /// **'Scan check-in QR'**
  String get checkInScan;

  /// No description provided for @checkInSaved.
  ///
  /// In en, this message translates to:
  /// **'Check-in saved on device — pending sync.'**
  String get checkInSaved;

  /// No description provided for @checkInDuplicate.
  ///
  /// In en, this message translates to:
  /// **'This code was already scanned today (duplicate prevented).'**
  String get checkInDuplicate;

  /// No description provided for @checkInInvalid.
  ///
  /// In en, this message translates to:
  /// **'This is not a clinic check-in code.'**
  String get checkInInvalid;

  /// No description provided for @scanCheckInTitle.
  ///
  /// In en, this message translates to:
  /// **'Scan check-in code'**
  String get scanCheckInTitle;

  /// No description provided for @scanBatchTitle.
  ///
  /// In en, this message translates to:
  /// **'Scan medicine pack'**
  String get scanBatchTitle;

  /// No description provided for @scanCheckInHelp.
  ///
  /// In en, this message translates to:
  /// **'Point the camera at the QR code at the desk or on the slip.'**
  String get scanCheckInHelp;

  /// No description provided for @scanBatchHelp.
  ///
  /// In en, this message translates to:
  /// **'Point the camera at the barcode on the strip or box (batch and expiry are read from it).'**
  String get scanBatchHelp;

  /// No description provided for @scanTypeCode.
  ///
  /// In en, this message translates to:
  /// **'Type the code'**
  String get scanTypeCode;

  /// No description provided for @scanUse.
  ///
  /// In en, this message translates to:
  /// **'Use'**
  String get scanUse;

  /// No description provided for @rxDraftPdf.
  ///
  /// In en, this message translates to:
  /// **'Draft PDF'**
  String get rxDraftPdf;

  /// No description provided for @rxDraftPdfDone.
  ///
  /// In en, this message translates to:
  /// **'Draft preview created (watermarked — not valid until signed online).'**
  String get rxDraftPdfDone;

  /// No description provided for @rxPrintSigned.
  ///
  /// In en, this message translates to:
  /// **'Print signed Rx'**
  String get rxPrintSigned;

  /// No description provided for @billingRecent.
  ///
  /// In en, this message translates to:
  /// **'Recent invoices (server)'**
  String get billingRecent;

  /// No description provided for @billingRecentShow.
  ///
  /// In en, this message translates to:
  /// **'Show'**
  String get billingRecentShow;

  /// No description provided for @invoiceAmounts.
  ///
  /// In en, this message translates to:
  /// **'Total {total} · paid {paid} · {status}'**
  String invoiceAmounts(String total, String paid, String status);

  /// No description provided for @invoiceReceipt.
  ///
  /// In en, this message translates to:
  /// **'Receipt PDF'**
  String get invoiceReceipt;

  /// No description provided for @paymentConfirm.
  ///
  /// In en, this message translates to:
  /// **'Confirm payment'**
  String get paymentConfirm;

  /// No description provided for @paymentTitle.
  ///
  /// In en, this message translates to:
  /// **'Payment for {invoice}'**
  String paymentTitle(String invoice);

  /// No description provided for @paymentAmount.
  ///
  /// In en, this message translates to:
  /// **'Amount received'**
  String get paymentAmount;

  /// No description provided for @paymentServerNote.
  ///
  /// In en, this message translates to:
  /// **'Recorded by the server now. It is never saved offline.'**
  String get paymentServerNote;

  /// No description provided for @paymentRecorded.
  ///
  /// In en, this message translates to:
  /// **'Payment recorded by the server.'**
  String get paymentRecorded;

  /// No description provided for @reportsTitle.
  ///
  /// In en, this message translates to:
  /// **'Today\'s summary'**
  String get reportsTitle;

  /// No description provided for @reportsToday.
  ///
  /// In en, this message translates to:
  /// **'Today (from the server)'**
  String get reportsToday;

  /// No description provided for @reportsCollections.
  ///
  /// In en, this message translates to:
  /// **'Collections'**
  String get reportsCollections;

  /// No description provided for @reportsRefunds.
  ///
  /// In en, this message translates to:
  /// **'Refunds'**
  String get reportsRefunds;

  /// No description provided for @reportsNet.
  ///
  /// In en, this message translates to:
  /// **'Net'**
  String get reportsNet;

  /// No description provided for @reportsAppointments.
  ///
  /// In en, this message translates to:
  /// **'Appointments'**
  String get reportsAppointments;

  /// No description provided for @reportsAdmitted.
  ///
  /// In en, this message translates to:
  /// **'Admitted now'**
  String get reportsAdmitted;

  /// No description provided for @reportsLowStock.
  ///
  /// In en, this message translates to:
  /// **'Low-stock items'**
  String get reportsLowStock;

  /// No description provided for @reportsServerNote.
  ///
  /// In en, this message translates to:
  /// **'Calculated by the server from its ledger; nothing is stored on this device.'**
  String get reportsServerNote;

  /// No description provided for @reportsForbidden.
  ///
  /// In en, this message translates to:
  /// **'Your role cannot view reports.'**
  String get reportsForbidden;

  /// No description provided for @syncHealthTitle.
  ///
  /// In en, this message translates to:
  /// **'Sync health of this device'**
  String get syncHealthTitle;

  /// No description provided for @stockTitle.
  ///
  /// In en, this message translates to:
  /// **'Stock count (draft — works offline)'**
  String get stockTitle;

  /// No description provided for @stockScan.
  ///
  /// In en, this message translates to:
  /// **'Scan batch barcode'**
  String get stockScan;

  /// No description provided for @stockPickItem.
  ///
  /// In en, this message translates to:
  /// **'Pick an item'**
  String get stockPickItem;

  /// No description provided for @stockCounted.
  ///
  /// In en, this message translates to:
  /// **'Counted quantity'**
  String get stockCounted;

  /// No description provided for @stockSave.
  ///
  /// In en, this message translates to:
  /// **'Save count draft'**
  String get stockSave;

  /// No description provided for @stockSaved.
  ///
  /// In en, this message translates to:
  /// **'Count saved on device. Post it online after review.'**
  String get stockSaved;

  /// No description provided for @stockQtyInvalid.
  ///
  /// In en, this message translates to:
  /// **'Enter a whole number (0 or more).'**
  String get stockQtyInvalid;

  /// No description provided for @stockNoMatch.
  ///
  /// In en, this message translates to:
  /// **'No inventory item matches {code}. Pick the item by hand.'**
  String stockNoMatch(String code);

  /// No description provided for @stockScanned.
  ///
  /// In en, this message translates to:
  /// **'Batch {batch} · expiry {expiry}'**
  String stockScanned(String batch, String expiry);

  /// No description provided for @stockDrafts.
  ///
  /// In en, this message translates to:
  /// **'Count drafts'**
  String get stockDrafts;

  /// No description provided for @stockBatch.
  ///
  /// In en, this message translates to:
  /// **'Batch {batch}'**
  String stockBatch(String batch);

  /// No description provided for @stockExpiry.
  ///
  /// In en, this message translates to:
  /// **'Expiry {expiry}'**
  String stockExpiry(String expiry);

  /// No description provided for @stockPostAction.
  ///
  /// In en, this message translates to:
  /// **'Post adjustment'**
  String get stockPostAction;

  /// No description provided for @stockPostTitle.
  ///
  /// In en, this message translates to:
  /// **'Adjust {item}?'**
  String stockPostTitle(String item);

  /// No description provided for @stockPostBody.
  ///
  /// In en, this message translates to:
  /// **'Server on hand: {onHand}. Counted: {counted}. Adjustment: {delta}.'**
  String stockPostBody(int onHand, int counted, int delta);

  /// No description provided for @stockPosted.
  ///
  /// In en, this message translates to:
  /// **'Posted'**
  String get stockPosted;

  /// No description provided for @stockNoDifference.
  ///
  /// In en, this message translates to:
  /// **'No difference from the server — nothing to post.'**
  String get stockNoDifference;

  /// No description provided for @entityEncounter.
  ///
  /// In en, this message translates to:
  /// **'consultation note'**
  String get entityEncounter;

  /// No description provided for @entityAppointment.
  ///
  /// In en, this message translates to:
  /// **'appointment'**
  String get entityAppointment;

  /// No description provided for @entityCheckIn.
  ///
  /// In en, this message translates to:
  /// **'check-in'**
  String get entityCheckIn;

  /// No description provided for @devicesTitle.
  ///
  /// In en, this message translates to:
  /// **'Medical devices'**
  String get devicesTitle;

  /// No description provided for @devicesIntro.
  ///
  /// In en, this message translates to:
  /// **'Bluetooth BP monitors and pulse oximeters registered by the clinic. Every reading is reviewed by a clinician before it enters the record.'**
  String get devicesIntro;

  /// No description provided for @devicesNotValidated.
  ///
  /// In en, this message translates to:
  /// **'No device model has been validated on real hardware yet. Simulated devices produce synthetic readings only.'**
  String get devicesNotValidated;

  /// No description provided for @devicesNone.
  ///
  /// In en, this message translates to:
  /// **'No devices registered yet.'**
  String get devicesNone;

  /// No description provided for @devicesRefresh.
  ///
  /// In en, this message translates to:
  /// **'Refresh list'**
  String get devicesRefresh;

  /// No description provided for @devicePaired.
  ///
  /// In en, this message translates to:
  /// **'Paired with this phone'**
  String get devicePaired;

  /// No description provided for @deviceNotPaired.
  ///
  /// In en, this message translates to:
  /// **'Not paired with this phone'**
  String get deviceNotPaired;

  /// No description provided for @devicePair.
  ///
  /// In en, this message translates to:
  /// **'Pair'**
  String get devicePair;

  /// No description provided for @deviceUnpair.
  ///
  /// In en, this message translates to:
  /// **'Unpair'**
  String get deviceUnpair;

  /// No description provided for @devicePairMismatch.
  ///
  /// In en, this message translates to:
  /// **'That is not the registered device.'**
  String get devicePairMismatch;

  /// No description provided for @devicePairDone.
  ///
  /// In en, this message translates to:
  /// **'Paired.'**
  String get devicePairDone;

  /// No description provided for @deviceRegister.
  ///
  /// In en, this message translates to:
  /// **'Register a new device'**
  String get deviceRegister;

  /// No description provided for @deviceScan.
  ///
  /// In en, this message translates to:
  /// **'Scan for devices'**
  String get deviceScan;

  /// No description provided for @deviceScanNone.
  ///
  /// In en, this message translates to:
  /// **'No device found nearby.'**
  String get deviceScanNone;

  /// No description provided for @deviceLabel.
  ///
  /// In en, this message translates to:
  /// **'Name (e.g. OPD room 1 BP monitor)'**
  String get deviceLabel;

  /// No description provided for @deviceRegistered.
  ///
  /// In en, this message translates to:
  /// **'Registered and paired.'**
  String get deviceRegistered;

  /// No description provided for @deviceSimulated.
  ///
  /// In en, this message translates to:
  /// **'SIMULATED'**
  String get deviceSimulated;

  /// No description provided for @deviceKindBp.
  ///
  /// In en, this message translates to:
  /// **'BP monitor'**
  String get deviceKindBp;

  /// No description provided for @deviceKindOximeter.
  ///
  /// In en, this message translates to:
  /// **'Pulse oximeter'**
  String get deviceKindOximeter;

  /// No description provided for @measureWithDevice.
  ///
  /// In en, this message translates to:
  /// **'Measure with device'**
  String get measureWithDevice;

  /// No description provided for @measureFor.
  ///
  /// In en, this message translates to:
  /// **'Measuring for: {patient}'**
  String measureFor(String patient);

  /// No description provided for @measureNoPairedDevice.
  ///
  /// In en, this message translates to:
  /// **'No paired device of this type. Pair one under Settings → Medical devices.'**
  String get measureNoPairedDevice;

  /// No description provided for @measureStart.
  ///
  /// In en, this message translates to:
  /// **'Start measurement'**
  String get measureStart;

  /// No description provided for @measureWaiting.
  ///
  /// In en, this message translates to:
  /// **'Waiting for the device… take the measurement on the device.'**
  String get measureWaiting;

  /// No description provided for @measureScenario.
  ///
  /// In en, this message translates to:
  /// **'Simulator scenario'**
  String get measureScenario;

  /// No description provided for @measureRefused.
  ///
  /// In en, this message translates to:
  /// **'Not saved: {reason}'**
  String measureRefused(String reason);

  /// No description provided for @measureSave.
  ///
  /// In en, this message translates to:
  /// **'Save for clinician review'**
  String get measureSave;

  /// No description provided for @measureSaved.
  ///
  /// In en, this message translates to:
  /// **'Saved on this phone; it will be sent for clinician review.'**
  String get measureSaved;

  /// No description provided for @measureFlags.
  ///
  /// In en, this message translates to:
  /// **'Device notes: {flags}'**
  String measureFlags(String flags);

  /// No description provided for @measureError.
  ///
  /// In en, this message translates to:
  /// **'Measurement failed: {error}'**
  String measureError(String error);

  /// No description provided for @measureNotRecord.
  ///
  /// In en, this message translates to:
  /// **'Not yet part of the record — a clinician must accept it.'**
  String get measureNotRecord;

  /// No description provided for @reviewTitle.
  ///
  /// In en, this message translates to:
  /// **'Device readings to review'**
  String get reviewTitle;

  /// No description provided for @reviewOpen.
  ///
  /// In en, this message translates to:
  /// **'Review device readings'**
  String get reviewOpen;

  /// No description provided for @reviewNone.
  ///
  /// In en, this message translates to:
  /// **'No readings waiting for review.'**
  String get reviewNone;

  /// No description provided for @reviewAccept.
  ///
  /// In en, this message translates to:
  /// **'Accept into record'**
  String get reviewAccept;

  /// No description provided for @reviewReject.
  ///
  /// In en, this message translates to:
  /// **'Reject'**
  String get reviewReject;

  /// No description provided for @reviewConfirm.
  ///
  /// In en, this message translates to:
  /// **'This reading belongs to {patient} and was measured just now.'**
  String reviewConfirm(String patient);

  /// No description provided for @reviewReason.
  ///
  /// In en, this message translates to:
  /// **'Reason for rejecting'**
  String get reviewReason;

  /// No description provided for @reviewAccepted.
  ///
  /// In en, this message translates to:
  /// **'Accepted into the consultation\'s vitals.'**
  String get reviewAccepted;

  /// No description provided for @reviewRejected.
  ///
  /// In en, this message translates to:
  /// **'Rejected.'**
  String get reviewRejected;

  /// No description provided for @reviewFailed.
  ///
  /// In en, this message translates to:
  /// **'Could not complete the review: {error}'**
  String reviewFailed(String error);

  /// No description provided for @readingBp.
  ///
  /// In en, this message translates to:
  /// **'BP {sys}/{dia} mmHg'**
  String readingBp(String sys, String dia);

  /// No description provided for @readingPulse.
  ///
  /// In en, this message translates to:
  /// **'Pulse {pulse}/min'**
  String readingPulse(String pulse);

  /// No description provided for @readingSpo2.
  ///
  /// In en, this message translates to:
  /// **'SpO2 {spo2} %'**
  String readingSpo2(String spo2);

  /// No description provided for @readingClockSkew.
  ///
  /// In en, this message translates to:
  /// **'The device clock differs from the phone\'s.'**
  String get readingClockSkew;
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
