/**
 * Device / responsive-shell / PWA strings (bottom navigation, shortcuts,
 * connectivity banner, update toast, printer test page). Key sets must match
 * across languages (src/lib/i18n.test.ts).
 */
type Dict = Record<string, string>;

const en: Dict = {
  devSkipToContent: "Skip to main content",
  devHome: "Home",
  devMore: "More",
  devMoreTitle: "All modules",
  devClose: "Close",
  devPrimaryNav: "Primary",
  devSearchPatients: "Search patients",
  devQuickSearch: "Quick patient search",
  devQuickSearchHint: "Name, phone or UHID — press / to focus",
  devGo: "Go",
  devBackOnline: "Back online.",
  devOffline:
    "You are offline. You can keep reading this page, but nothing is sent or saved until the connection returns.",
  devReconnecting: "Connection problem — reconnecting…",
  devRetryNow: "Retry now",
  devNeedsConnection:
    "Needs a connection: payments, refunds and prescription signing are finalised by the server and are never queued offline in the web app.",
  devUpdateAvailable: "A new version is available.",
  devReload: "Reload",
  devShortcutsTitle: "Keyboard shortcuts",
  devShortcutsHint:
    "Single-key shortcuts are ignored while you are typing in a field. Ctrl+K works everywhere.",
  devScSearch: "Focus patient search",
  devScNew: "New record on this page (when the page has one)",
  devScHelp: "Show this help",
  devScClose: "Close a dialog or sheet",
  devScGoto: "Go to",
  devScThen: "then",
  devPrintTestTitle: "Printer test page",
  devPrintTestIntro:
    "Print this page on each printer once. Every corner mark must be fully visible and the ruler must measure 50 mm; otherwise adjust the printer's margins or scaling (use 100% / “Actual size”).",
  devPaper: "Paper",
  devPaperA4: "A4",
  devPaperA5: "A5",
  devPaper80: "80 mm thermal roll",
  devPrint: "Print",
  devRuler: "50 mm ruler",
  devSampleReceipt: "Sample receipt — synthetic data, not a real bill",
  devPrinterTestLink: "Printer test page",
};

const mr: Dict = {
  devSkipToContent: "मुख्य मजकुराकडे जा",
  devHome: "मुख्यपृष्ठ",
  devMore: "अधिक",
  devMoreTitle: "सर्व विभाग",
  devClose: "बंद करा",
  devPrimaryNav: "मुख्य",
  devSearchPatients: "रुग्ण शोधा",
  devQuickSearch: "जलद रुग्ण शोध",
  devQuickSearchHint: "नाव, फोन किंवा UHID — / दाबा",
  devGo: "शोधा",
  devBackOnline: "पुन्हा ऑनलाइन.",
  devOffline:
    "तुम्ही ऑफलाइन आहात. हे पान वाचता येईल, पण कनेक्शन परत येईपर्यंत काहीही पाठवले किंवा जतन केले जात नाही.",
  devReconnecting: "कनेक्शनमध्ये अडचण — पुन्हा जोडत आहे…",
  devRetryNow: "आता पुन्हा प्रयत्न करा",
  devNeedsConnection:
    "कनेक्शन आवश्यक: पेमेंट, परतावा आणि औषधपत्रावर सही सर्व्हरवर अंतिम होतात; वेब ॲपमध्ये ते ऑफलाइन रांगेत ठेवले जात नाहीत.",
  devUpdateAvailable: "नवीन आवृत्ती उपलब्ध आहे.",
  devReload: "रीलोड करा",
  devShortcutsTitle: "कीबोर्ड शॉर्टकट",
  devShortcutsHint:
    "एखाद्या रकान्यात टाइप करताना एक-कळ शॉर्टकट चालत नाहीत. Ctrl+K सर्वत्र चालते.",
  devScSearch: "रुग्ण शोधावर जा",
  devScNew: "या पानावर नवीन नोंद (उपलब्ध असल्यास)",
  devScHelp: "ही मदत दाखवा",
  devScClose: "संवाद किंवा पत्रक बंद करा",
  devScGoto: "येथे जा",
  devScThen: "नंतर",
  devPrintTestTitle: "प्रिंटर चाचणी पान",
  devPrintTestIntro:
    "प्रत्येक प्रिंटरवर हे पान एकदा छापा. प्रत्येक कोपऱ्याची खूण पूर्ण दिसली पाहिजे आणि पट्टी 50 मिमी मोजली पाहिजे; नसल्यास प्रिंटरचे समास किंवा स्केलिंग बदला (100% / “Actual size” वापरा).",
  devPaper: "कागद",
  devPaperA4: "A4",
  devPaperA5: "A5",
  devPaper80: "80 मिमी थर्मल रोल",
  devPrint: "छापा",
  devRuler: "50 मिमी पट्टी",
  devSampleReceipt: "नमुना पावती — कृत्रिम माहिती, खरे बिल नाही",
  devPrinterTestLink: "प्रिंटर चाचणी पान",
};

const hi: Dict = {
  devSkipToContent: "मुख्य सामग्री पर जाएँ",
  devHome: "मुखपृष्ठ",
  devMore: "और",
  devMoreTitle: "सभी विभाग",
  devClose: "बंद करें",
  devPrimaryNav: "मुख्य",
  devSearchPatients: "रोगी खोजें",
  devQuickSearch: "त्वरित रोगी खोज",
  devQuickSearchHint: "नाम, फ़ोन या UHID — / दबाएँ",
  devGo: "खोजें",
  devBackOnline: "फिर से ऑनलाइन।",
  devOffline:
    "आप ऑफ़लाइन हैं। यह पेज पढ़ सकते हैं, पर कनेक्शन लौटने तक कुछ भी भेजा या सहेजा नहीं जाता।",
  devReconnecting: "कनेक्शन में समस्या — फिर से जोड़ रहे हैं…",
  devRetryNow: "अभी फिर कोशिश करें",
  devNeedsConnection:
    "कनेक्शन आवश्यक: भुगतान, रिफ़ंड और पर्चे पर हस्ताक्षर सर्वर पर अंतिम होते हैं; वेब ऐप में ये ऑफ़लाइन कतार में नहीं रखे जाते।",
  devUpdateAvailable: "नया संस्करण उपलब्ध है।",
  devReload: "रीलोड करें",
  devShortcutsTitle: "कीबोर्ड शॉर्टकट",
  devShortcutsHint:
    "किसी फ़ील्ड में टाइप करते समय एक-कुंजी शॉर्टकट काम नहीं करते। Ctrl+K हर जगह काम करता है।",
  devScSearch: "रोगी खोज पर जाएँ",
  devScNew: "इस पेज पर नया रिकॉर्ड (यदि उपलब्ध हो)",
  devScHelp: "यह सहायता दिखाएँ",
  devScClose: "डायलॉग या शीट बंद करें",
  devScGoto: "यहाँ जाएँ",
  devScThen: "फिर",
  devPrintTestTitle: "प्रिंटर परीक्षण पेज",
  devPrintTestIntro:
    "हर प्रिंटर पर यह पेज एक बार छापें। हर कोने का निशान पूरा दिखना चाहिए और पट्टी 50 मिमी मापनी चाहिए; वरना प्रिंटर का मार्जिन या स्केलिंग बदलें (100% / “Actual size” चुनें)।",
  devPaper: "कागज़",
  devPaperA4: "A4",
  devPaperA5: "A5",
  devPaper80: "80 मिमी थर्मल रोल",
  devPrint: "छापें",
  devRuler: "50 मिमी पट्टी",
  devSampleReceipt: "नमूना रसीद — कृत्रिम डेटा, असली बिल नहीं",
  devPrinterTestLink: "प्रिंटर परीक्षण पेज",
};

export const deviceDictionaries = { en, mr, hi };
