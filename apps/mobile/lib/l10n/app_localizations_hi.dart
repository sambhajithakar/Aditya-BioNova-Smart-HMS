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
}
