// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Marathi (`mr`).
class AppLocalizationsMr extends AppLocalizations {
  AppLocalizationsMr([String locale = 'mr']) : super(locale);

  @override
  String get appTitle => 'Aditya BioNova Smart HMS';

  @override
  String get appSubtitle => 'डॉक्टर व फील्ड कर्मचाऱ्यांसाठी ॲप';

  @override
  String get languageMenu => 'भाषा';

  @override
  String get languageDevice => 'फोनची भाषा';

  @override
  String get settingsMenu => 'सेटिंग्ज';

  @override
  String get refresh => 'रीफ्रेश करा';

  @override
  String get cancel => 'रद्द करा';

  @override
  String get back => 'मागे';

  @override
  String get patient => 'रुग्ण';

  @override
  String get branch => 'शाखा';

  @override
  String get pickPatientFirst => 'आधी रुग्ण निवडा.';

  @override
  String outboxCounts(int pending, int failed, int conflicted) {
    return 'आउटबॉक्स — प्रलंबित: $pending, अयशस्वी: $failed, विसंगत: $conflicted';
  }

  @override
  String outboxCountsShort(int pending, int conflicted) {
    return 'आउटबॉक्स — प्रलंबित: $pending, विसंगत: $conflicted';
  }

  @override
  String get pendingSyncTag => '(सिंक बाकी)';

  @override
  String get syncedTag => '(सिंक झाले)';

  @override
  String get loginEmail => 'ईमेल';

  @override
  String get loginPassword => 'पासवर्ड';

  @override
  String get loginSlug => 'क्लिनिक कोड (ऐच्छिक)';

  @override
  String get loginSubmit => 'साइन इन करा';

  @override
  String get loginSigningIn => 'साइन इन होत आहे…';

  @override
  String get loginMfaTitle => 'द्वि-स्तरीय पडताळणी';

  @override
  String get loginMfaHelp =>
      'तुमच्या ऑथेंटिकेटर ॲपमधील 6 अंकी कोड किंवा तुमच्या रिकव्हरी कोडपैकी एक (xxxx-xxxx) टाका.';

  @override
  String get loginMfaCode => 'कोड';

  @override
  String get loginVerify => 'पडताळा';

  @override
  String get loginVerifying => 'पडताळणी होत आहे…';

  @override
  String get loginMfaMissing => 'ऑथेंटिकेटर ॲपमधील कोड टाका.';

  @override
  String get loginMfaRejected =>
      'हा कोड स्वीकारला गेला नाही. फोनवरील वेळ तपासा किंवा रिकव्हरी कोड वापरा.';

  @override
  String get loginUnreachable =>
      'सर्व्हरशी संपर्क झाला नाही. इंटरनेट कनेक्शन तपासून पुन्हा प्रयत्न करा.';

  @override
  String get rateLimitedWait =>
      'खूप जास्त प्रयत्न झाले. थोडा वेळ थांबून पुन्हा प्रयत्न करा.';

  @override
  String rateLimitedSeconds(int seconds) {
    return 'खूप जास्त प्रयत्न झाले. $seconds सेकंदांनी पुन्हा प्रयत्न करा.';
  }

  @override
  String rateLimitedMinutes(int minutes) {
    String _temp0 = intl.Intl.pluralLogic(
      minutes,
      locale: localeName,
      other: '$minutes मिनिटांनी',
      one: '1 मिनिटाने',
    );
    return 'खूप जास्त प्रयत्न झाले. $_temp0 पुन्हा प्रयत्न करा.';
  }

  @override
  String get sessionExpiredNotice =>
      'तुमचे साइन-इन कालबाह्य झाले आहे. या डिव्हाइसवर जतन केलेले काम सुरक्षित आहे आणि साइन इन केल्यावर सिंक होईल.';

  @override
  String get lockedOutNotice =>
      'बरेच चुकीचे PIN टाकले गेले. पुन्हा ऑनलाइन साइन इन करा — या डिव्हाइसवर जतन केलेले काम सुरक्षित राहील.';

  @override
  String get pinSetTitle => 'ॲप PIN सेट करा';

  @override
  String get pinUnlockTitle => 'तुमचा ॲप PIN टाका';

  @override
  String get pinSetHelp =>
      'या डिव्हाइसवरील रुग्णांची माहिती PIN ने सुरक्षित आहे. नेटवर्क नसतानाही ॲप उघडण्यासाठी हा PIN लागेल.';

  @override
  String get worksOffline => 'ऑफलाइनही चालते.';

  @override
  String get pinLabel => 'PIN';

  @override
  String get pinRepeat => 'PIN पुन्हा टाका';

  @override
  String get pinSave => 'PIN जतन करा';

  @override
  String get pinUnlock => 'उघडा';

  @override
  String get pinUsePassword => 'त्याऐवजी पासवर्डने साइन इन करा';

  @override
  String get pinRule => '4 ते 8 अंक वापरा.';

  @override
  String get pinMismatch => 'दोन्ही PIN जुळत नाहीत.';

  @override
  String pinWrong(int left) {
    String _temp0 = intl.Intl.pluralLogic(
      left,
      locale: localeName,
      other: '$left प्रयत्न',
      one: '1 प्रयत्न',
    );
    return 'चुकीचा PIN — $_temp0 बाकी.';
  }

  @override
  String get recoveryTitle => 'ऑफलाइन डेटा उघडता आला नाही';

  @override
  String get recoveryTitleFatal => 'हे बिल्ड सुरू होऊ शकत नाही';

  @override
  String get recoveryBody =>
      'या डिव्हाइसवर जतन केलेले काम या फोनच्या सुरक्षित हार्डवेअरमधील कीने एन्क्रिप्ट केलेले आहे. ती की किंवा डेटा वाचता आला नाही — ॲप नवीन फोनवर रिस्टोअर केल्यावर किंवा जतन केलेली फाइल खराब झाल्यास असे होते.\n\nऑफलाइन स्टोरेजशिवाय ॲप पुढे चालणार नाही, कारण नवीन काम नकळत हरवू शकते. आधी पुन्हा प्रयत्न करा; तरीही अडचण राहिल्यास लोकल डेटा रीसेट करा.';

  @override
  String recoveryDetails(String details) {
    return 'तपशील: $details';
  }

  @override
  String get recoveryRetry => 'पुन्हा प्रयत्न करा';

  @override
  String get recoveryReset => 'लोकल डेटा रीसेट करा (सिंक न झालेले काम हरवेल)';

  @override
  String get recoveryResetTitle => 'लोकल डेटा रीसेट करायचा?';

  @override
  String get recoveryResetBody =>
      'ॲपने या डिव्हाइसवर ठेवलेले सर्व काही हटवले जाईल: सिंक न झालेल्या नोंदण्या, रांगेतील नोंदी, बिले आणि प्रिस्क्रिप्शनचे मसुदे कायमचे हरवतील आणि परत मिळणार नाहीत. सर्व्हरवरील डेटावर परिणाम होणार नाही. नंतर तुम्हाला पुन्हा साइन इन करावे लागेल.';

  @override
  String get recoveryResetConfirm => 'लोकल डेटा हटवा';

  @override
  String homeTitle(String role) {
    return 'HMS · $role';
  }

  @override
  String get signOut => 'साइन आउट';

  @override
  String get signOutTitle => 'या डिव्हाइसवरून साइन आउट करायचे?';

  @override
  String get signOutTitleUnsynced => 'सिंक न झालेले बदल हरवतील';

  @override
  String get signOutBody =>
      'या डिव्हाइसवरील रुग्णांची साठवलेली यादी, मसुदे आणि तुमचा PIN काढून टाकले जातील.';

  @override
  String signOutBodyUnsynced(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count बदल',
      one: '1 बदल',
    );
    return 'या डिव्हाइसवर जतन केलेले $_temp0 अजून सर्व्हरवर पोहोचलेले नाहीत. साइन आउट केल्यास ते, रुग्णांची साठवलेली यादी आणि मसुद्यांसह, हटवले जातील. शक्य असल्यास आधी सिंक करा.';
  }

  @override
  String get signOutDelete => 'हटवा आणि साइन आउट करा';

  @override
  String get sessionExpiredBanner =>
      'सर्व्हरने तुम्हाला साइन आउट केले आहे. तुम्ही ऑफलाइन काम सुरू ठेवू शकता; सिंक करण्यासाठी पुन्हा साइन इन करा.';

  @override
  String get tabQueue => 'रांग';

  @override
  String get tabRegister => 'नोंदणी';

  @override
  String get tabRx => 'Rx';

  @override
  String get tabFastRx => 'जलद Rx';

  @override
  String get tabBilling => 'बिलिंग';

  @override
  String get tabBill => 'बिल';

  @override
  String get tabSync => 'सिंक';

  @override
  String get ruralMode => 'ग्रामीण दवाखाना मोड';

  @override
  String get ruralModeHelp => 'मोठी बटणे, मोठा मजकूर, चार टप्पे';

  @override
  String editionLabel(String edition) {
    return 'आवृत्ती: $edition';
  }

  @override
  String get mobileNotEnabled =>
      'तुमच्या क्लिनिकच्या प्लॅनमध्ये मोबाइल ॲप समाविष्ट नाही. या डिव्हाइसवर आधीच जतन केलेले बदल \"सिंक\" टॅबमधून अजूनही सिंक करता येतील. तुमच्या ॲडमिनिस्ट्रेटरशी संपर्क साधा.';

  @override
  String get queueTitle => 'ऑफलाइन रांग नोंद';

  @override
  String get queuePickBoth => 'रुग्ण आणि शाखा निवडा (एकदा सिंक आवश्यक).';

  @override
  String get queueDuplicate => 'आजच्या रांगेत आधीच आहे — दुहेरी नोंद टाळली.';

  @override
  String queueSaved(int count) {
    return 'डिव्हाइसवर जतन — सिंक बाकी (आउटबॉक्समध्ये $count).';
  }

  @override
  String get queueAdd => 'रांगेत जोडा (ऑफलाइनही चालते)';

  @override
  String get loadingPatients => 'रुग्णांची यादी येत आहे…';

  @override
  String get noPatientsCached =>
      'अजून कोणतेही रुग्ण साठवलेले नाहीत — यादी घेण्यासाठी एकदा इंटरनेटशी जोडा; त्यानंतर रांगेतील नोंदी ऑफलाइनही होतील.';

  @override
  String get registerTitle => 'रुग्ण नोंदणी (ऑफलाइनही चालते)';

  @override
  String get registerName => 'पूर्ण नाव';

  @override
  String get registerGender => 'लिंग';

  @override
  String get genderFemale => 'स्त्री';

  @override
  String get genderMale => 'पुरुष';

  @override
  String get genderOther => 'इतर';

  @override
  String get genderUnknown => 'माहीत नाही';

  @override
  String get registerPhone => 'फोन (ऐच्छिक)';

  @override
  String get registerDobUnknown => 'जन्मतारीख — माहीत नाही (अंदाजे)';

  @override
  String registerDob(String date) {
    return 'जन्मतारीख — $date';
  }

  @override
  String get pick => 'निवडा';

  @override
  String get registerAllergies => 'ज्ञात ॲलर्जी (कुटुंबीय सांगतील ते लिहा)';

  @override
  String get registerAdd => 'नोंदणी करा (ऑफलाइनही चालते)';

  @override
  String get registerNameRequired => 'रुग्णाचे पूर्ण नाव टाका.';

  @override
  String get registerLooksDuplicate =>
      'हा आधीच नोंदवलेला रुग्ण वाटतो — दुहेरी नोंद टाळली (यादीतून निवडा, किंवा तरीही नोंदवायचे असल्यास तपशील बदला).';

  @override
  String get registerDuplicateQueued =>
      'हीच नोंदणी आधीच सिंकसाठी जतन आहे — दुहेरी नोंद टाळली.';

  @override
  String get registerSaved =>
      'डिव्हाइसवर जतन — सिंक बाकी. सिंक होताच आजच्या रांगेत जोडले जाईल.';

  @override
  String get billingTitle => 'बिल तयार करा (ऑफलाइनही चालते)';

  @override
  String get billingLineType => 'बाबीचा प्रकार';

  @override
  String get itemConsultation => 'वैद्यकीय सल्ला';

  @override
  String get itemProcedure => 'प्रक्रिया';

  @override
  String get itemPharmacy => 'औषधे (फार्मसी)';

  @override
  String get itemLab => 'लॅब तपासणी';

  @override
  String get itemOther => 'इतर';

  @override
  String get billingDescription => 'तपशील';

  @override
  String get billingQuantity => 'संख्या';

  @override
  String get billingUnitPrice => 'प्रति नग किंमत';

  @override
  String get billingAdd => 'बिल जतन करा (ऑफलाइनही चालते)';

  @override
  String get billingDescribe => 'बिल करण्याच्या बाबीचा तपशील लिहा.';

  @override
  String get billingQtyPrice => 'संख्या आणि प्रति नग किंमत आवश्यक आहे.';

  @override
  String get billingDuplicate =>
      'हेच बिल आधीच सिंकसाठी जतन आहे — दुहेरी नोंद टाळली.';

  @override
  String get billingSaved =>
      'बिल डिव्हाइसवर जतन — सिंक बाकी. एकूण रक्कम आणि बिल क्रमांक सर्व्हर ठरवतो.';

  @override
  String get rxTitle => 'जलद Rx मसुदा (ऑफलाइनही चालते)';

  @override
  String get rxMedicine => 'औषध (प्रमाणित यादीतून)';

  @override
  String get rxDose => 'डोस (500 mg)';

  @override
  String get rxFrequency => 'किती वेळा (BD)';

  @override
  String get rxDays => 'दिवस';

  @override
  String get rxDispense => 'द्यायची नग संख्या (ऐच्छिक)';

  @override
  String get rxDispenseHelp => 'फार्मसी एकूण यापेक्षा जास्त देऊ शकत नाही';

  @override
  String get rxAddItem => 'औषध जोडा';

  @override
  String rxItemLine(String drug, String dose, String frequency, String days) {
    return '$drug — $dose, $frequency, $days दिवस';
  }

  @override
  String rxItemDispense(String quantity) {
    return ' · द्यायचे $quantity';
  }

  @override
  String get rxDiagnosis => 'निदान (मजकूर)';

  @override
  String get rxSave => 'मसुदा जतन करा (ऑफलाइनही चालते)';

  @override
  String get rxDrafts => 'या डिव्हाइसवरील मसुदे';

  @override
  String get rxNoDrafts =>
      'अजून मसुदे नाहीत — ते त्यांच्या सिंक स्थितीसह इथे दिसतील.';

  @override
  String get rxNoCatalog =>
      'औषधांची यादी अजून साठवलेली नाही — एकदा इंटरनेटशी जोडा.';

  @override
  String get rxRequired => 'डोस, किती वेळा आणि किती दिवस हे आवश्यक आहे.';

  @override
  String get rxDispenseRange =>
      'द्यायची संख्या 1–10000 नग असावी (किंवा रिकामी ठेवा).';

  @override
  String get rxAddOne => 'किमान एक औषध जोडा.';

  @override
  String get rxDuplicate =>
      'हाच मसुदा आधीच सिंकसाठी जतन आहे — दुहेरी नोंद टाळली.';

  @override
  String get rxSaved =>
      'मसुदा डिव्हाइसवर जतन — सिंक बाकी. सिंक झाल्यावर स्वाक्षरी करा (ॲलर्जी तपासणी सर्व्हरवर होते).';

  @override
  String get rxSigned => 'प्रिस्क्रिप्शनवर स्वाक्षरी झाली.';

  @override
  String get rxSign => 'स्वाक्षरी करा';

  @override
  String get rxSignAfterSync => 'स्वाक्षरी (सिंकनंतर)';

  @override
  String rxDraftLine(String drug, String dose, String frequency, String days) {
    return '$drug $dose $frequency $days दि.';
  }

  @override
  String get rxQuickFrequency => 'किती वेळा — निवडा';

  @override
  String get rxQuickDuration => 'किती दिवस — निवडा';

  @override
  String get freqOD => 'दिवसातून एकदा';

  @override
  String get freqBD => 'दिवसातून दोनदा';

  @override
  String get freqTDS => 'दिवसातून तीनदा';

  @override
  String get freqQID => 'दिवसातून चार वेळा';

  @override
  String get freqHS => 'झोपताना';

  @override
  String get freqSOS => 'गरज असेल तेव्हाच';

  @override
  String daysCount(int days) {
    String _temp0 = intl.Intl.pluralLogic(
      days,
      locale: localeName,
      other: '$days दिवस',
      one: '1 दिवस',
    );
    return '$_temp0';
  }

  @override
  String get stateSigned => 'स्वाक्षरी झाली';

  @override
  String get stateConflict => 'विसंगती — तुमचा निर्णय हवा';

  @override
  String get stateSavedPending => 'डिव्हाइसवर जतन · सिंक बाकी';

  @override
  String get stateDiscarded => 'रद्द केले — पाठवले नाही';

  @override
  String get stateSynced => 'सिंक झाले';

  @override
  String get opPending => 'सिंक बाकी';

  @override
  String opPendingRetry(int attempt) {
    return 'सिंक बाकी · पुन्हा प्रयत्न $attempt';
  }

  @override
  String get opSyncing => 'सिंक होत आहे…';

  @override
  String get opFailed => 'अजून पाठवले नाही — आपोआप पुन्हा प्रयत्न होईल';

  @override
  String opFailedAttempt(int attempt) {
    return 'अजून पाठवले नाही — आपोआप पुन्हा प्रयत्न होईल (प्रयत्न $attempt)';
  }

  @override
  String savedOnDevice(String state) {
    return 'डिव्हाइसवर जतन · $state';
  }

  @override
  String get syncTitle => 'सिंक केंद्र';

  @override
  String syncCounts(int pending, int failed, int conflicted) {
    return 'प्रलंबित: $pending · अयशस्वी: $failed · विसंगत: $conflicted';
  }

  @override
  String syncNextRetry(String time) {
    return '$time पासून आपोआप पुन्हा प्रयत्न';
  }

  @override
  String get syncNow => 'आता सिंक करा';

  @override
  String get syncRetryFailed => 'अयशस्वी पुन्हा पाठवा';

  @override
  String syncResult(int pushed, int conflicts, int failed) {
    return 'पाठवले $pushed · विसंगती $conflicts · अयशस्वी $failed';
  }

  @override
  String syncWaiting(int count) {
    return ' · प्रतीक्षेत $count';
  }

  @override
  String get syncStopped => ' · थांबले (पुन्हा साइन इन करा)';

  @override
  String syncedEntity(String entity) {
    return 'सिंक झाले · $entity';
  }

  @override
  String syncPersistError(String error) {
    return 'डिव्हाइसवर जतन करता आले नाही: $error';
  }

  @override
  String get syncQueued => 'या डिव्हाइसवर सिंकसाठी थांबलेले';

  @override
  String get syncNothingQueued =>
      'काहीही बाकी नाही — सर्व बदल सर्व्हरवर पोहोचले आहेत.';

  @override
  String get syncNoConflicts =>
      'कोणतीही विसंगती नाही — डिव्हाइस आणि सर्व्हर जुळतात.';

  @override
  String get conflictDiscard => 'रद्द करा (इथे सर्व्हरचे ग्राह्य)';

  @override
  String get conflictRegisterAnyway => 'डिव्हाइसवरचे ठेवा (तरीही नोंदणी करा)';

  @override
  String get conflictClaim => 'डिव्हाइसवरचे ठेवा (माझ्या नावाने पाठवा)';

  @override
  String get conflictKeep => 'डिव्हाइसवरचे ठेवा (पुन्हा पाठवा)';

  @override
  String get registerAnywayTitle => 'नवीन रुग्ण म्हणून नोंदणी करायची?';

  @override
  String registerAnywayBody(String name) {
    return 'सर्व्हरला $name सारखे दिसणारे आधीचे रुग्ण सापडले. ही वेगळी व्यक्ती आहे याची खात्री केली असेल तरच पुढे जा — दुहेरी नोंदीमुळे रुग्णाचा इतिहास विभागला जातो.';
  }

  @override
  String get registerAnywayAction => 'तरीही नोंदणी करा';

  @override
  String registerAnywayNotice(String name) {
    return 'पुढच्या सिंकमध्ये $name यांची नवीन रुग्ण म्हणून नोंदणी होईल.';
  }

  @override
  String get thisPatient => 'हा रुग्ण';

  @override
  String get claimTitle => 'तुमच्या खात्यातून पाठवायचे?';

  @override
  String get claimBody =>
      'हा बदल कोणी केला हे ॲपने नोंदवण्यापूर्वी जतन झाला होता. तो तुम्ही केला असेल तरच पाठवा.';

  @override
  String get claimAction => 'माझ्या नावाने पाठवा';

  @override
  String discardTitle(String entity, int count) {
    return '$entity आणि आणखी $count रद्द करायचे?';
  }

  @override
  String discardBody(int count, String what, String entity) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'सिंकसाठी थांबलेले $count बदल ($what) या $entity वर अवलंबून आहेत आणि त्याशिवाय कधीही पाठवता येणार नाहीत. तेही रद्द होतील.',
      one:
          'सिंकसाठी थांबलेला 1 बदल ($what) या $entity वर अवलंबून आहे आणि त्याशिवाय कधीही पाठवता येणार नाही. तोही रद्द होईल.',
    );
    return '$_temp0';
  }

  @override
  String get discardAll => 'सर्व रद्द करा';

  @override
  String discardedOne(String entity) {
    return 'रद्द केले: $entity.';
  }

  @override
  String discardedMany(String entity, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'त्यावर अवलंबून $count बदल',
      one: 'त्यावर अवलंबून 1 बदल',
    );
    return 'रद्द केले: $entity आणि $_temp0.';
  }

  @override
  String get entityPatient => 'रुग्ण नोंदणी';

  @override
  String get entityQueueEntry => 'रांग नोंद';

  @override
  String get entityInvoice => 'बिल';

  @override
  String get entityPrescription => 'प्रिस्क्रिप्शन';

  @override
  String get conflictVersion => 'सर्व्हरवरील नोंद बदलली आहे';

  @override
  String get conflictPolicy => 'सर्व्हरने हा बदल नाकारला';

  @override
  String get conflictAuth => 'पुढे जाण्यासाठी पुन्हा साइन इन करा';

  @override
  String get conflictDuplicate => 'संभाव्य दुहेरी नोंदणी';

  @override
  String get conflictWrongUser =>
      'या डिव्हाइसवर दुसऱ्या वापरकर्त्याने तयार केले';
}
