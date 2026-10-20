// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hindi (`hi`).
class AppLocalizationsHi extends AppLocalizations {
  AppLocalizationsHi([String locale = 'hi']) : super(locale);

  @override
  String get appTitle => 'Aditya BioNova Smart HMS';

  @override
  String get appSubtitle => 'डॉक्टर और फ़ील्ड स्टाफ़ ऐप';

  @override
  String get languageMenu => 'भाषा';

  @override
  String get languageDevice => 'फ़ोन की भाषा';

  @override
  String get settingsMenu => 'सेटिंग्स';

  @override
  String get refresh => 'रीफ़्रेश करें';

  @override
  String get cancel => 'रद्द करें';

  @override
  String get back => 'वापस';

  @override
  String get patient => 'मरीज़';

  @override
  String get branch => 'शाखा';

  @override
  String get pickPatientFirst => 'पहले मरीज़ चुनें.';

  @override
  String outboxCounts(int pending, int failed, int conflicted) {
    return 'आउटबॉक्स — लंबित: $pending, विफल: $failed, टकराव: $conflicted';
  }

  @override
  String outboxCountsShort(int pending, int conflicted) {
    return 'आउटबॉक्स — लंबित: $pending, टकराव: $conflicted';
  }

  @override
  String get pendingSyncTag => '(सिंक बाकी)';

  @override
  String get syncedTag => '(सिंक हो गया)';

  @override
  String get loginEmail => 'ईमेल';

  @override
  String get loginPassword => 'पासवर्ड';

  @override
  String get loginSlug => 'क्लिनिक कोड (वैकल्पिक)';

  @override
  String get loginSubmit => 'साइन इन करें';

  @override
  String get loginSigningIn => 'साइन इन हो रहा है…';

  @override
  String get loginMfaTitle => 'दो-चरणीय सत्यापन';

  @override
  String get loginMfaHelp =>
      'अपने ऑथेंटिकेटर ऐप का 6 अंकों का कोड या अपना कोई एक रिकवरी कोड (xxxx-xxxx) दर्ज करें.';

  @override
  String get loginMfaCode => 'कोड';

  @override
  String get loginVerify => 'सत्यापित करें';

  @override
  String get loginVerifying => 'सत्यापन हो रहा है…';

  @override
  String get loginMfaMissing => 'ऑथेंटिकेटर ऐप का कोड दर्ज करें.';

  @override
  String get loginMfaRejected =>
      'यह कोड स्वीकार नहीं हुआ. फ़ोन का समय जाँचें या रिकवरी कोड इस्तेमाल करें.';

  @override
  String get loginUnreachable =>
      'सर्वर से संपर्क नहीं हो सका. इंटरनेट कनेक्शन जाँचकर फिर से कोशिश करें.';

  @override
  String get rateLimitedWait =>
      'बहुत ज़्यादा प्रयास हुए. कुछ देर रुककर फिर कोशिश करें.';

  @override
  String rateLimitedSeconds(int seconds) {
    return 'बहुत ज़्यादा प्रयास हुए. $seconds सेकंड बाद फिर कोशिश करें.';
  }

  @override
  String rateLimitedMinutes(int minutes) {
    String _temp0 = intl.Intl.pluralLogic(
      minutes,
      locale: localeName,
      other: '$minutes मिनट',
      one: '1 मिनट',
    );
    return 'बहुत ज़्यादा प्रयास हुए. $_temp0 बाद फिर कोशिश करें.';
  }

  @override
  String get sessionExpiredNotice =>
      'आपका साइन-इन समाप्त हो गया है. इस डिवाइस पर सहेजा गया काम सुरक्षित है और साइन इन करने के बाद सिंक होगा.';

  @override
  String get lockedOutNotice =>
      'कई बार गलत PIN डाला गया. फिर से ऑनलाइन साइन इन करें — इस डिवाइस पर सहेजा गया काम सुरक्षित रहेगा.';

  @override
  String get pinSetTitle => 'ऐप PIN सेट करें';

  @override
  String get pinUnlockTitle => 'अपना ऐप PIN डालें';

  @override
  String get pinSetHelp =>
      'इस डिवाइस पर मरीज़ों की जानकारी PIN से सुरक्षित है. नेटवर्क न होने पर भी ऐप खोलने के लिए यह PIN चाहिए होगा.';

  @override
  String get worksOffline => 'ऑफ़लाइन भी चलता है.';

  @override
  String get pinLabel => 'PIN';

  @override
  String get pinRepeat => 'PIN दोबारा डालें';

  @override
  String get pinSave => 'PIN सहेजें';

  @override
  String get pinUnlock => 'अनलॉक करें';

  @override
  String get pinUsePassword => 'इसके बजाय पासवर्ड से साइन इन करें';

  @override
  String get pinRule => '4 से 8 अंक इस्तेमाल करें.';

  @override
  String get pinMismatch => 'दोनों PIN मेल नहीं खाते.';

  @override
  String pinWrong(int left) {
    String _temp0 = intl.Intl.pluralLogic(
      left,
      locale: localeName,
      other: '$left प्रयास',
      one: '1 प्रयास',
    );
    return 'गलत PIN — $_temp0 बाकी.';
  }

  @override
  String get recoveryTitle => 'ऑफ़लाइन डेटा खोला नहीं जा सका';

  @override
  String get recoveryTitleFatal => 'यह बिल्ड शुरू नहीं हो सकता';

  @override
  String get recoveryBody =>
      'इस डिवाइस पर सहेजा गया काम इस फ़ोन के सुरक्षित हार्डवेयर में रखी कुंजी से एन्क्रिप्ट है. वह कुंजी या डेटा पढ़ा नहीं जा सका — ऐसा ऐप को नए फ़ोन पर रिस्टोर करने या सहेजी गई फ़ाइल खराब होने पर होता है.\n\nऑफ़लाइन स्टोरेज के बिना ऐप आगे नहीं चलेगा, क्योंकि नया काम चुपचाप खो सकता है. पहले फिर से कोशिश करें; बार-बार विफल हो तो लोकल डेटा रीसेट करें.';

  @override
  String recoveryDetails(String details) {
    return 'विवरण: $details';
  }

  @override
  String get recoveryRetry => 'फिर से कोशिश करें';

  @override
  String get recoveryReset => 'लोकल डेटा रीसेट करें (सिंक न हुआ काम खो जाएगा)';

  @override
  String get recoveryResetTitle => 'लोकल डेटा रीसेट करें?';

  @override
  String get recoveryResetBody =>
      'ऐप द्वारा इस डिवाइस पर रखा सब कुछ हटा दिया जाएगा: सिंक न हुए पंजीकरण, कतार की प्रविष्टियाँ, बिल और प्रिस्क्रिप्शन के ड्राफ़्ट हमेशा के लिए खो जाएँगे और वापस नहीं मिलेंगे. सर्वर पर मौजूद डेटा पर कोई असर नहीं होगा. इसके बाद आपको फिर से साइन इन करना होगा.';

  @override
  String get recoveryResetConfirm => 'लोकल डेटा हटाएँ';

  @override
  String homeTitle(String role) {
    return 'HMS · $role';
  }

  @override
  String get signOut => 'साइन आउट';

  @override
  String get signOutTitle => 'इस डिवाइस से साइन आउट करें?';

  @override
  String get signOutTitleUnsynced => 'सिंक न हुए बदलाव खो जाएँगे';

  @override
  String get signOutBody =>
      'इस डिवाइस से मरीज़ों की सहेजी गई सूची, ड्राफ़्ट और आपका PIN हटा दिए जाएँगे.';

  @override
  String signOutBodyUnsynced(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count बदलाव',
      one: '1 बदलाव',
    );
    return 'इस डिवाइस पर सहेजे गए $_temp0 अभी तक सर्वर पर नहीं पहुँचे हैं. साइन आउट करने पर ये, मरीज़ों की सहेजी गई सूची और ड्राफ़्ट के साथ, हट जाएँगे. हो सके तो पहले सिंक करें.';
  }

  @override
  String get signOutDelete => 'हटाएँ और साइन आउट करें';

  @override
  String get sessionExpiredBanner =>
      'सर्वर ने आपको साइन आउट कर दिया है. आप ऑफ़लाइन काम जारी रख सकते हैं; सिंक करने के लिए फिर से साइन इन करें.';

  @override
  String get tabQueue => 'कतार';

  @override
  String get tabRegister => 'पंजीकरण';

  @override
  String get tabRx => 'Rx';

  @override
  String get tabFastRx => 'फ़ास्ट Rx';

  @override
  String get tabBilling => 'बिलिंग';

  @override
  String get tabBill => 'बिल';

  @override
  String get tabSync => 'सिंक';

  @override
  String get ruralMode => 'ग्रामीण क्लिनिक मोड';

  @override
  String get ruralModeHelp => 'बड़े बटन, बड़ा टेक्स्ट, चार चरण';

  @override
  String editionLabel(String edition) {
    return 'संस्करण: $edition';
  }

  @override
  String get mobileNotEnabled =>
      'आपके क्लिनिक के प्लान में मोबाइल ऐप शामिल नहीं है. इस डिवाइस पर पहले से सहेजे गए बदलाव \"सिंक\" टैब से अब भी सिंक किए जा सकते हैं. अपने एडमिनिस्ट्रेटर से संपर्क करें.';

  @override
  String get queueTitle => 'ऑफ़लाइन कतार प्रविष्टि';

  @override
  String get queuePickBoth => 'मरीज़ और शाखा चुनें (एक बार सिंक ज़रूरी).';

  @override
  String get queueDuplicate =>
      'आज की कतार में पहले से है — दोहरी प्रविष्टि रोकी गई.';

  @override
  String queueSaved(int count) {
    return 'डिवाइस पर सहेजा गया — सिंक बाकी (आउटबॉक्स में $count).';
  }

  @override
  String get queueAdd => 'कतार में जोड़ें (ऑफ़लाइन भी चलता है)';

  @override
  String get loadingPatients => 'मरीज़ों की सूची लोड हो रही है…';

  @override
  String get noPatientsCached =>
      'अभी कोई मरीज़ सहेजा नहीं गया है — सूची लाने के लिए एक बार इंटरनेट से जुड़ें; उसके बाद कतार प्रविष्टियाँ ऑफ़लाइन भी होंगी.';

  @override
  String get registerTitle => 'मरीज़ पंजीकरण (ऑफ़लाइन भी चलता है)';

  @override
  String get registerName => 'पूरा नाम';

  @override
  String get registerGender => 'लिंग';

  @override
  String get genderFemale => 'महिला';

  @override
  String get genderMale => 'पुरुष';

  @override
  String get genderOther => 'अन्य';

  @override
  String get genderUnknown => 'पता नहीं';

  @override
  String get registerPhone => 'फ़ोन (वैकल्पिक)';

  @override
  String get registerDobUnknown => 'जन्मतिथि — पता नहीं (अनुमानित)';

  @override
  String registerDob(String date) {
    return 'जन्मतिथि — $date';
  }

  @override
  String get pick => 'चुनें';

  @override
  String get registerAllergies => 'ज्ञात एलर्जी (परिवार जो बताए वह लिखें)';

  @override
  String get registerAdd => 'पंजीकरण करें (ऑफ़लाइन भी चलता है)';

  @override
  String get registerNameRequired => 'मरीज़ का पूरा नाम दर्ज करें.';

  @override
  String get registerLooksDuplicate =>
      'यह पहले से दर्ज मरीज़ लगता है — दोहरी प्रविष्टि रोकी गई (सूची से चुनें, या फिर भी दर्ज करना हो तो विवरण बदलें).';

  @override
  String get registerDuplicateQueued =>
      'यही पंजीकरण पहले से सिंक के लिए सहेजा है — दोहरी प्रविष्टि रोकी गई.';

  @override
  String get registerSaved =>
      'डिवाइस पर सहेजा गया — सिंक बाकी. सिंक होते ही आज की कतार में जोड़ दिया जाएगा.';

  @override
  String get billingTitle => 'बिल बनाएँ (ऑफ़लाइन भी चलता है)';

  @override
  String get billingLineType => 'मद का प्रकार';

  @override
  String get itemConsultation => 'परामर्श';

  @override
  String get itemProcedure => 'प्रक्रिया';

  @override
  String get itemPharmacy => 'दवाइयाँ (फ़ार्मेसी)';

  @override
  String get itemLab => 'लैब जाँच';

  @override
  String get itemOther => 'अन्य';

  @override
  String get billingDescription => 'विवरण';

  @override
  String get billingQuantity => 'मात्रा';

  @override
  String get billingUnitPrice => 'प्रति इकाई मूल्य';

  @override
  String get billingAdd => 'बिल सहेजें (ऑफ़लाइन भी चलता है)';

  @override
  String get billingDescribe => 'बिल की जा रही मद का विवरण लिखें.';

  @override
  String get billingQtyPrice => 'मात्रा और प्रति इकाई मूल्य ज़रूरी हैं.';

  @override
  String get billingDuplicate =>
      'यही बिल पहले से सिंक के लिए सहेजा है — दोहरी प्रविष्टि रोकी गई.';

  @override
  String get billingSaved =>
      'बिल डिवाइस पर सहेजा गया — सिंक बाकी. कुल राशि और बिल नंबर सर्वर तय करता है.';

  @override
  String get rxTitle => 'फ़ास्ट Rx ड्राफ़्ट (ऑफ़लाइन भी चलता है)';

  @override
  String get rxMedicine => 'दवा (प्रमाणित सूची से)';

  @override
  String get rxDose => 'खुराक (500 mg)';

  @override
  String get rxFrequency => 'कितनी बार (BD)';

  @override
  String get rxDays => 'दिन';

  @override
  String get rxDispense => 'दी जाने वाली इकाइयाँ (वैकल्पिक)';

  @override
  String get rxDispenseHelp => 'फ़ार्मेसी कुल मिलाकर इससे ज़्यादा नहीं दे सकती';

  @override
  String get rxAddItem => 'दवा जोड़ें';

  @override
  String rxItemLine(String drug, String dose, String frequency, String days) {
    return '$drug — $dose, $frequency, $days दिन';
  }

  @override
  String rxItemDispense(String quantity) {
    return ' · देना $quantity';
  }

  @override
  String get rxDiagnosis => 'निदान (टेक्स्ट)';

  @override
  String get rxSave => 'ड्राफ़्ट सहेजें (ऑफ़लाइन भी चलता है)';

  @override
  String get rxDrafts => 'इस डिवाइस पर ड्राफ़्ट';

  @override
  String get rxNoDrafts =>
      'अभी कोई ड्राफ़्ट नहीं — वे अपनी सिंक स्थिति के साथ यहाँ दिखेंगे.';

  @override
  String get rxNoCatalog =>
      'दवाओं की सूची अभी सहेजी नहीं गई — एक बार इंटरनेट से जुड़ें.';

  @override
  String get rxRequired => 'खुराक, कितनी बार और कितने दिन — ये ज़रूरी हैं.';

  @override
  String get rxDispenseRange =>
      'दी जाने वाली मात्रा 1–10000 इकाई होनी चाहिए (या खाली छोड़ें).';

  @override
  String get rxAddOne => 'कम से कम एक दवा जोड़ें.';

  @override
  String get rxDuplicate =>
      'यही ड्राफ़्ट पहले से सिंक के लिए सहेजा है — दोहरी प्रविष्टि रोकी गई.';

  @override
  String get rxSaved =>
      'ड्राफ़्ट डिवाइस पर सहेजा गया — सिंक बाकी. सिंक होने के बाद हस्ताक्षर करें (एलर्जी जाँच सर्वर पर होती है).';

  @override
  String get rxSigned => 'प्रिस्क्रिप्शन पर हस्ताक्षर हो गए.';

  @override
  String get rxSign => 'हस्ताक्षर करें';

  @override
  String get rxSignAfterSync => 'हस्ताक्षर (सिंक के बाद)';

  @override
  String rxDraftLine(String drug, String dose, String frequency, String days) {
    return '$drug $dose $frequency $days दिन';
  }

  @override
  String get rxQuickFrequency => 'कितनी बार — चुनें';

  @override
  String get rxQuickDuration => 'कितने दिन — चुनें';

  @override
  String get freqOD => 'दिन में एक बार';

  @override
  String get freqBD => 'दिन में दो बार';

  @override
  String get freqTDS => 'दिन में तीन बार';

  @override
  String get freqQID => 'दिन में चार बार';

  @override
  String get freqHS => 'सोते समय';

  @override
  String get freqSOS => 'ज़रूरत होने पर ही';

  @override
  String daysCount(int days) {
    String _temp0 = intl.Intl.pluralLogic(
      days,
      locale: localeName,
      other: '$days दिन',
      one: '1 दिन',
    );
    return '$_temp0';
  }

  @override
  String get stateSigned => 'हस्ताक्षरित';

  @override
  String get stateConflict => 'टकराव — आपका निर्णय चाहिए';

  @override
  String get stateSavedPending => 'डिवाइस पर सहेजा · सिंक बाकी';

  @override
  String get stateDiscarded => 'रद्द — भेजा नहीं गया';

  @override
  String get stateSynced => 'सिंक हो गया';

  @override
  String get opPending => 'सिंक बाकी';

  @override
  String opPendingRetry(int attempt) {
    return 'सिंक बाकी · दोबारा प्रयास $attempt';
  }

  @override
  String get opSyncing => 'सिंक हो रहा है…';

  @override
  String get opFailed => 'अभी भेजा नहीं गया — अपने आप दोबारा कोशिश होगी';

  @override
  String opFailedAttempt(int attempt) {
    return 'अभी भेजा नहीं गया — अपने आप दोबारा कोशिश होगी (प्रयास $attempt)';
  }

  @override
  String savedOnDevice(String state) {
    return 'डिवाइस पर सहेजा · $state';
  }

  @override
  String get syncTitle => 'सिंक केंद्र';

  @override
  String syncCounts(int pending, int failed, int conflicted) {
    return 'लंबित: $pending · विफल: $failed · टकराव: $conflicted';
  }

  @override
  String syncNextRetry(String time) {
    return '$time से अपने आप दोबारा प्रयास';
  }

  @override
  String get syncNow => 'अभी सिंक करें';

  @override
  String get syncRetryFailed => 'विफल को अभी दोबारा भेजें';

  @override
  String syncResult(int pushed, int conflicts, int failed) {
    return 'भेजे गए $pushed · टकराव $conflicts · विफल $failed';
  }

  @override
  String syncWaiting(int count) {
    return ' · प्रतीक्षा में $count';
  }

  @override
  String get syncStopped => ' · रुका (फिर से साइन इन करें)';

  @override
  String syncedEntity(String entity) {
    return 'सिंक हो गया · $entity';
  }

  @override
  String syncPersistError(String error) {
    return 'डिवाइस स्टोरेज में सहेजा नहीं जा सका: $error';
  }

  @override
  String get syncQueued => 'इस डिवाइस पर सिंक के लिए रुके हुए';

  @override
  String get syncNothingQueued =>
      'कुछ बाकी नहीं — सभी बदलाव सर्वर पर पहुँच गए हैं.';

  @override
  String get syncNoConflicts =>
      'कोई टकराव नहीं — डिवाइस और सर्वर मेल खाते हैं.';

  @override
  String get conflictDiscard => 'रद्द करें (यहाँ सर्वर का मान्य)';

  @override
  String get conflictRegisterAnyway => 'डिवाइस वाला रखें (फिर भी पंजीकरण करें)';

  @override
  String get conflictClaim => 'डिवाइस वाला रखें (मेरे नाम से भेजें)';

  @override
  String get conflictKeep => 'डिवाइस वाला रखें (दोबारा भेजें)';

  @override
  String get registerAnywayTitle => 'नए मरीज़ के रूप में पंजीकरण करें?';

  @override
  String registerAnywayBody(String name) {
    return 'सर्वर को $name जैसे दिखने वाले मौजूदा मरीज़ मिले हैं. आगे तभी बढ़ें जब आपने जाँच लिया हो कि यह अलग व्यक्ति है — दोहरा रिकॉर्ड मरीज़ का इतिहास बाँट देता है.';
  }

  @override
  String get registerAnywayAction => 'फिर भी पंजीकरण करें';

  @override
  String registerAnywayNotice(String name) {
    return 'अगले सिंक में $name का नए मरीज़ के रूप में पंजीकरण होगा.';
  }

  @override
  String get thisPatient => 'यह मरीज़';

  @override
  String get claimTitle => 'अपने खाते से भेजें?';

  @override
  String get claimBody =>
      'यह बदलाव ऐप द्वारा बनाने वाले का नाम दर्ज करने से पहले सहेजा गया था. इसे तभी भेजें जब यह आपने किया हो.';

  @override
  String get claimAction => 'मेरे नाम से भेजें';

  @override
  String discardTitle(String entity, int count) {
    return '$entity और $count अन्य रद्द करें?';
  }

  @override
  String discardBody(int count, String what, String entity) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other:
          'सिंक के लिए रुके $count बदलाव ($what) इस $entity पर निर्भर हैं और इसके बिना कभी नहीं भेजे जा सकते. वे भी रद्द होंगे.',
      one:
          'सिंक के लिए रुका 1 बदलाव ($what) इस $entity पर निर्भर है और इसके बिना कभी नहीं भेजा जा सकता. वह भी रद्द होगा.',
    );
    return '$_temp0';
  }

  @override
  String get discardAll => 'सभी रद्द करें';

  @override
  String discardedOne(String entity) {
    return 'रद्द किया गया: $entity.';
  }

  @override
  String discardedMany(String entity, int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'उस पर निर्भर $count बदलाव',
      one: 'उस पर निर्भर 1 बदलाव',
    );
    return 'रद्द किया गया: $entity और $_temp0.';
  }

  @override
  String get entityPatient => 'मरीज़ पंजीकरण';

  @override
  String get entityQueueEntry => 'कतार प्रविष्टि';

  @override
  String get entityInvoice => 'बिल';

  @override
  String get entityPrescription => 'प्रिस्क्रिप्शन';

  @override
  String get conflictVersion => 'सर्वर पर रिकॉर्ड बदल गया है';

  @override
  String get conflictPolicy => 'सर्वर ने यह बदलाव अस्वीकार किया';

  @override
  String get conflictAuth => 'जारी रखने के लिए फिर से साइन इन करें';

  @override
  String get conflictDuplicate => 'संभावित दोहरा पंजीकरण';

  @override
  String get conflictWrongUser => 'इस डिवाइस पर किसी अन्य उपयोगकर्ता ने बनाया';

  @override
  String get statusOnline => 'ऑनलाइन';

  @override
  String get statusOffline => 'ऑफ़लाइन';

  @override
  String get statusSavedOnDevice => 'डिवाइस पर सहेजा';

  @override
  String get statusPendingSync => 'सिंक लंबित';

  @override
  String get statusSyncing => 'सिंक हो रहा है';

  @override
  String get statusSynced => 'सिंक हो गया';

  @override
  String get statusConflict => 'टकराव';

  @override
  String get statusActionRequired => 'कार्रवाई ज़रूरी';

  @override
  String statusCount(String status, int count) {
    return '$status: $count';
  }

  @override
  String globalToSync(int count) {
    return 'सिंक करने हैं: $count';
  }

  @override
  String globalConflicts(int count) {
    return 'टकराव: $count';
  }

  @override
  String globalNeedAction(int count) {
    return 'कार्रवाई ज़रूरी: $count';
  }

  @override
  String globalOfflineSaved(int count) {
    return 'ऑफ़लाइन · डिवाइस पर $count सहेजे';
  }

  @override
  String get globalAllSynced => 'सब सिंक हो गया';

  @override
  String get needsConnection => 'इंटरनेट चाहिए — ऑफ़लाइन अंतिम नहीं किया जाएगा';

  @override
  String get needsConnectionTitle => 'इंटरनेट चाहिए';

  @override
  String get needsConnectionReports =>
      'रिपोर्ट सर्वर बनाता है; वे इस डिवाइस पर नहीं रखी जातीं.';

  @override
  String get errNetwork => 'इंटरनेट नहीं — अपने आप फिर से कोशिश होगी.';

  @override
  String get errServer => 'सर्वर में समस्या — अपने आप फिर से कोशिश होगी.';

  @override
  String get errBusy => 'सर्वर व्यस्त — थोड़ी देर बाद फिर कोशिश होगी.';

  @override
  String errForbidden(String detail) {
    return 'आपके खाते को अनुमति नहीं: $detail';
  }

  @override
  String errInvalid(String detail) {
    return 'सर्वर ने जानकारी स्वीकार नहीं की: $detail';
  }

  @override
  String errMaxAttempts(int count) {
    return '$count बार कोशिश नाकाम — अपने आप कोशिश रुकी. अभी फिर कोशिश करें दबाएँ.';
  }

  @override
  String get retryNow => 'अभी फिर कोशिश करें';

  @override
  String waitingFor(String entity) {
    return 'पहले $entity के सिंक होने का इंतज़ार';
  }

  @override
  String blockedBy(String entity) {
    return 'रुका हुआ: जिस $entity पर निर्भर है उस पर आपकी कार्रवाई चाहिए';
  }

  @override
  String get orphanedExplain =>
      'यह रद्द किए गए रिकॉर्ड पर निर्भर है — जैसा है वैसा भेजा नहीं जा सकता.';

  @override
  String get syncAttention => 'आपका ध्यान चाहिए';

  @override
  String get storageTitle => 'इस डिवाइस पर स्टोरेज';

  @override
  String storageUsage(int kb, int patients, int queued) {
    return 'लगभग $kb KB एन्क्रिप्टेड · $patients कैश मरीज़ · $queued कतार में बदलाव';
  }

  @override
  String get clearCacheAction => 'कैश की गई मरीज़ जानकारी हटाएँ';

  @override
  String get clearCacheTitle => 'कैश मरीज़ हटाएँ?';

  @override
  String get clearCacheBody =>
      'सर्वर से आए मरीज़ इस डिवाइस से हटा दिए जाएँगे. यहाँ दर्ज और अभी सिंक न हुए मरीज़ रहेंगे. अगली बार ऑनलाइन होने पर वे फिर आएँगे.';

  @override
  String clearCacheDone(int count) {
    return '$count कैश मरीज़ इस डिवाइस से हटाए गए.';
  }

  @override
  String get deviceSignedOutByAdmin =>
      'व्यवस्थापक ने इस डिवाइस को साइन आउट कर दिया. मरीज़ों की जानकारी हटा दी गई; सिंक न हुआ काम डिवाइस पर सुरक्षित बंद है और वही उपयोगकर्ता दोबारा साइन इन करने पर वापस आएगा.';

  @override
  String quarantineTitle(int count) {
    return 'साइन आउट हुए उपयोगकर्ता के $count सिंक न हुए बदलाव इस डिवाइस पर बंद हैं';
  }

  @override
  String get quarantineBody =>
      'इन्हें देखा नहीं जा सकता. वही उपयोगकर्ता इस डिवाइस पर दोबारा साइन इन करे तो ये सिंक होंगे.';

  @override
  String get quarantineDiscardAction => 'बंद बदलाव रद्द करें';

  @override
  String quarantineDiscardTitle(int count) {
    return '$count बंद बदलाव रद्द करें?';
  }

  @override
  String get quarantineDiscardBody =>
      'ये कभी सर्वर को नहीं भेजे गए और इसके बाद वापस नहीं मिलेंगे.';

  @override
  String get quarantineDiscarded => 'बंद बदलाव रद्द किए गए.';

  @override
  String get conflictReview => 'जाँचें';

  @override
  String get conflictMine => 'इस डिवाइस पर सहेजा';

  @override
  String get conflictServer => 'सर्वर पर';

  @override
  String get conflictSendMine => 'मेरा फिर से भेजें';

  @override
  String get conflictSendMineTitle => 'अपना संस्करण फिर से भेजें?';

  @override
  String get conflictSendMineBody =>
      'आपके सहेजने के बाद सर्वर का रिकॉर्ड बदल गया. फिर से भेजने पर चुपचाप कुछ नहीं बदलता — सर्वर फिर जाँचता है और मना कर सकता है.';

  @override
  String get conflictSentAgain => 'फिर से भेजने के लिए कतार में.';

  @override
  String get useServerVersion => 'सर्वर का संस्करण इस्तेमाल करें';

  @override
  String get versionTitle => 'सर्वर पर बदला गया';

  @override
  String get versionExplain =>
      'आपके बदलाव सहेजने के बाद किसी ने सर्वर पर यह रिकॉर्ड बदला. तुलना करके चुनें — कुछ भी अपने आप नहीं बदला जाता.';

  @override
  String get dupTitle => 'संभावित दोहरा मरीज़';

  @override
  String get dupExplain =>
      'सर्वर पर पहले से ऐसा मरीज़ है. चुनें: अपना नया मरीज़ रखें, मौजूदा रिकॉर्ड इस्तेमाल करें, या हर जानकारी जाँचकर मिलाएँ.';

  @override
  String dupMatchedOn(String fields) {
    return 'मिलान: $fields';
  }

  @override
  String get keepMineNew => 'मेरा नया मरीज़ रखें';

  @override
  String get useServerAction => 'यह रिकॉर्ड इस्तेमाल करें';

  @override
  String useServerTitle(String patient) {
    return '$patient इस्तेमाल करें?';
  }

  @override
  String useServerBody(int count) {
    return 'आपका पंजीकरण नहीं भेजा जाएगा. इस मरीज़ के $count कतार वाले बदलाव मौजूदा रिकॉर्ड से जोड़े जाएँगे.';
  }

  @override
  String useServerDone(String patient) {
    return '$patient से जोड़ा गया.';
  }

  @override
  String get mergeAction => 'जाँचकर मिलाएँ';

  @override
  String get mergeTitle => 'जाँचकर मिलाएँ';

  @override
  String get mergeExplain =>
      'सर्वर का रिकॉर्ड अभी फिर से पढ़ा गया. अपने पंजीकरण से लेने वाली जानकारी पर ही निशान लगाएँ; आपके लिए कुछ पहले से चुना नहीं गया.';

  @override
  String get mergeNothing =>
      'कोई अलग जानकारी नहीं — मौजूदा रिकॉर्ड इस्तेमाल होगा.';

  @override
  String mergeFieldLine(String server, String mine) {
    return 'सर्वर: $server → मेरा: $mine';
  }

  @override
  String mergeApply(int count) {
    return '$count जानकारी लें और रिकॉर्ड इस्तेमाल करें';
  }

  @override
  String mergeDone(int count, String uhid) {
    return '$count जानकारी $uhid में ली गई.';
  }

  @override
  String get fieldDob => 'जन्म तिथि';

  @override
  String get fieldAddress => 'पता';

  @override
  String get fieldBloodGroup => 'ब्लड ग्रुप';

  @override
  String get detailRequest => 'अनुरोध';

  @override
  String get detailState => 'स्थिति';

  @override
  String get detailCreated => 'सहेजने का समय';

  @override
  String get detailAttempts => 'कोशिशें';

  @override
  String get detailNextRetry => 'अगली कोशिश';

  @override
  String get detailKey => 'आइडेम्पोटेंसी की';

  @override
  String get detailHttp => 'सर्वर का जवाब';

  @override
  String get detailError => 'आख़िरी समस्या';

  @override
  String get detailDepends => 'इस पर निर्भर';

  @override
  String get detailNoLongerQueued => 'यह बदलाव अब कतार में नहीं है.';

  @override
  String get tabOverview => 'सारांश';

  @override
  String get tabConsult => 'परामर्श';

  @override
  String get tabPatients => 'मरीज़';

  @override
  String get tabAppointments => 'अपॉइंटमेंट';

  @override
  String get tabStock => 'स्टॉक';

  @override
  String get noTabsForRole =>
      'मोबाइल पर आपकी भूमिका के लिए कुछ चालू नहीं है. व्यवस्थापक से पूछें.';

  @override
  String get patientsSearch => 'नाम, UHID या फ़ोन खोजें';

  @override
  String get patientsSearchServer => 'सर्वर पर खोजें';

  @override
  String patientsCachedNote(int count) {
    return 'इस डिवाइस पर $count मरीज़ (केवल आपने ऑनलाइन देखे; एन्क्रिप्टेड)';
  }

  @override
  String get consultTitle => 'परामर्श नोट (ड्राफ़्ट — ऑफ़लाइन भी चलता है)';

  @override
  String get consultComplaint => 'मुख्य शिकायत';

  @override
  String get consultHistory => 'इतिहास';

  @override
  String get consultExam => 'जाँच';

  @override
  String get consultSave => 'नोट ड्राफ़्ट सहेजें';

  @override
  String get consultUpdate => 'ड्राफ़्ट अपडेट करें';

  @override
  String get consultEdit => 'बदलें';

  @override
  String get consultSaved => 'नोट ड्राफ़्ट डिवाइस पर सहेजा — सिंक लंबित.';

  @override
  String get consultDuplicate =>
      'इस मरीज़ का आज का नोट ड्राफ़्ट पहले से कतार में है (duplicate prevented).';

  @override
  String get consultComplaintRequired => 'मुख्य शिकायत लिखें.';

  @override
  String get consultNoBranch =>
      'इस डिवाइस पर अभी शाखा नहीं — ऑनलाइन रहते एक बार कतार खोलें.';

  @override
  String get consultAlreadySent =>
      'यह ड्राफ़्ट पहले ही भेजा गया — अब डिवाइस पर बदला नहीं जा सकता.';

  @override
  String get consultDrafts => 'नोट ड्राफ़्ट';

  @override
  String get consultNoDrafts => 'इस डिवाइस पर नोट ड्राफ़्ट नहीं.';

  @override
  String get consultComplete => 'परामर्श पूरा करें';

  @override
  String get consultCompleteAfterSync => 'पूरा करें (सिंक के बाद)';

  @override
  String get consultCompleted => 'परामर्श सर्वर पर पूरा हुआ.';

  @override
  String get appointmentsTitle => 'अपॉइंटमेंट बुक करें (ऑफ़लाइन भी चलता है)';

  @override
  String appointmentDay(String day) {
    return 'दिन: $day';
  }

  @override
  String get appointmentReason => 'कारण';

  @override
  String get appointmentSave => 'अपॉइंटमेंट ड्राफ़्ट सहेजें';

  @override
  String get appointmentSaved =>
      'अपॉइंटमेंट डिवाइस पर सहेजा — सिंक लंबित. सिंक होने पर सर्वर समय जाँचता है.';

  @override
  String get appointmentDuplicate =>
      'यह अपॉइंटमेंट पहले से कतार में है (duplicate prevented).';

  @override
  String get appointmentDrafts => 'अपॉइंटमेंट ड्राफ़्ट';

  @override
  String get appointmentsToday => 'आज के अपॉइंटमेंट (सर्वर)';

  @override
  String get appointmentsNone => 'आज कोई अपॉइंटमेंट नहीं.';

  @override
  String get queueToday => 'आज की कतार (सर्वर)';

  @override
  String get queueTodayShow => 'दिखाएँ';

  @override
  String get checkInScan => 'चेक-इन QR स्कैन करें';

  @override
  String get checkInSaved => 'चेक-इन डिवाइस पर सहेजा — सिंक लंबित.';

  @override
  String get checkInDuplicate =>
      'यह कोड आज पहले ही स्कैन हुआ (duplicate prevented).';

  @override
  String get checkInInvalid => 'यह क्लिनिक का चेक-इन कोड नहीं है.';

  @override
  String get scanCheckInTitle => 'चेक-इन कोड स्कैन करें';

  @override
  String get scanBatchTitle => 'दवा पैक स्कैन करें';

  @override
  String get scanCheckInHelp => 'कैमरा डेस्क या पर्ची पर QR की ओर करें.';

  @override
  String get scanBatchHelp =>
      'कैमरा पत्ते या डिब्बे के बारकोड की ओर करें (बैच और एक्सपायरी उससे पढ़ी जाती है).';

  @override
  String get scanTypeCode => 'कोड टाइप करें';

  @override
  String get scanUse => 'इस्तेमाल करें';

  @override
  String get rxDraftPdf => 'ड्राफ़्ट PDF';

  @override
  String get rxDraftPdfDone =>
      'ड्राफ़्ट प्रीव्यू बना (वॉटरमार्क — ऑनलाइन साइन होने तक मान्य नहीं).';

  @override
  String get rxPrintSigned => 'साइन किया Rx प्रिंट करें';

  @override
  String get billingRecent => 'हाल के बिल (सर्वर)';

  @override
  String get billingRecentShow => 'दिखाएँ';

  @override
  String invoiceAmounts(String total, String paid, String status) {
    return 'कुल $total · भुगतान $paid · $status';
  }

  @override
  String get invoiceReceipt => 'रसीद PDF';

  @override
  String get paymentConfirm => 'भुगतान पक्का करें';

  @override
  String paymentTitle(String invoice) {
    return '$invoice के लिए भुगतान';
  }

  @override
  String get paymentAmount => 'प्राप्त राशि';

  @override
  String get paymentServerNote =>
      'सर्वर अभी दर्ज करता है. यह कभी ऑफ़लाइन सहेजा नहीं जाता.';

  @override
  String get paymentRecorded => 'सर्वर ने भुगतान दर्ज किया.';

  @override
  String get reportsTitle => 'आज का सारांश';

  @override
  String get reportsToday => 'आज (सर्वर से)';

  @override
  String get reportsCollections => 'वसूली';

  @override
  String get reportsRefunds => 'रिफ़ंड';

  @override
  String get reportsNet => 'शुद्ध';

  @override
  String get reportsAppointments => 'अपॉइंटमेंट';

  @override
  String get reportsAdmitted => 'अभी भर्ती';

  @override
  String get reportsLowStock => 'कम स्टॉक';

  @override
  String get reportsServerNote =>
      'सर्वर ने अपने बहीखाते से गिना; इस डिवाइस पर कुछ नहीं रखा जाता.';

  @override
  String get reportsForbidden => 'आपकी भूमिका रिपोर्ट नहीं देख सकती.';

  @override
  String get syncHealthTitle => 'इस डिवाइस की सिंक स्थिति';

  @override
  String get stockTitle => 'स्टॉक गिनती (ड्राफ़्ट — ऑफ़लाइन भी चलता है)';

  @override
  String get stockScan => 'बैच बारकोड स्कैन करें';

  @override
  String get stockPickItem => 'वस्तु चुनें';

  @override
  String get stockCounted => 'गिनी गई मात्रा';

  @override
  String get stockSave => 'गिनती ड्राफ़्ट सहेजें';

  @override
  String get stockSaved => 'गिनती डिवाइस पर सहेजी. जाँचकर ऑनलाइन दर्ज करें.';

  @override
  String get stockQtyInvalid => 'पूरी संख्या लिखें (0 या अधिक).';

  @override
  String stockNoMatch(String code) {
    return '$code से मेल खाती वस्तु नहीं. हाथ से चुनें.';
  }

  @override
  String stockScanned(String batch, String expiry) {
    return 'बैच $batch · एक्सपायरी $expiry';
  }

  @override
  String get stockDrafts => 'गिनती ड्राफ़्ट';

  @override
  String stockBatch(String batch) {
    return 'बैच $batch';
  }

  @override
  String stockExpiry(String expiry) {
    return 'एक्सपायरी $expiry';
  }

  @override
  String get stockPostAction => 'समायोजन दर्ज करें';

  @override
  String stockPostTitle(String item) {
    return '$item में समायोजन करें?';
  }

  @override
  String stockPostBody(int onHand, int counted, int delta) {
    return 'सर्वर पर स्टॉक: $onHand. गिना: $counted. समायोजन: $delta.';
  }

  @override
  String get stockPosted => 'दर्ज किया';

  @override
  String get stockNoDifference =>
      'सर्वर से कोई अंतर नहीं — दर्ज करने को कुछ नहीं.';

  @override
  String get entityEncounter => 'परामर्श नोट';

  @override
  String get entityAppointment => 'अपॉइंटमेंट';

  @override
  String get entityCheckIn => 'चेक-इन';
}
