/** BioNova Business Copilot strings (AI-0). Key sets must match across languages. */
type Dict = Record<string, string>;

const en: Dict = {
  navCopilot: "Copilot",
  copilotTitle: "Business Copilot",
  copilotIntro:
    "Ask about this clinic's own verified figures. The assistant only picks a report; the numbers are calculated by the system from your records.",
  copilotAskLabel: "Your question",
  copilotAsk: "Ask",
  copilotExamples: "Try:",
  copilotEnablePrompt: "The Copilot is included in your edition but is switched off for this clinic.",
  copilotEnable: "Switch on the Copilot",
  copilotEnableNotice:
    "Questions are answered inside this system. With the default setting no data is sent to any outside AI service.",
  copilotNotEnabledAskAdmin: "Ask your clinic owner or admin to switch on the Copilot.",
  copilotHowComputed: "How this was computed",
  copilotFunction: "Report",
  copilotArgs: "Parameters",
  copilotMethod: "Calculation",
  copilotInferenceMock: "Rule-based (no AI model)",
  copilotInferenceLive: "AI model",
  copilotCredits: "AI credits used",
  copilotNotAnswered: "Not answered",
  copilotDisclaimer:
    "Operational information only — not clinical advice. Verify important figures in Reports.",
  copilotHistory: "This session",
};

const mr: Dict = {
  navCopilot: "कोपायलट",
  copilotTitle: "व्यवसाय कोपायलट",
  copilotIntro:
    "या क्लिनिकच्या पडताळलेल्या आकडेवारीबद्दल विचारा. सहाय्यक फक्त अहवाल निवडतो; आकडे प्रणाली तुमच्या नोंदींवरून काढते.",
  copilotAskLabel: "तुमचा प्रश्न",
  copilotAsk: "विचारा",
  copilotExamples: "उदाहरणे:",
  copilotEnablePrompt: "कोपायलट तुमच्या आवृत्तीत समाविष्ट आहे, पण या क्लिनिकसाठी बंद आहे.",
  copilotEnable: "कोपायलट सुरू करा",
  copilotEnableNotice:
    "प्रश्नांची उत्तरे या प्रणालीतच दिली जातात. मूळ सेटिंगमध्ये कोणताही डेटा बाहेरील AI सेवेकडे पाठवला जात नाही.",
  copilotNotEnabledAskAdmin: "कोपायलट सुरू करण्यासाठी क्लिनिकच्या मालकाला किंवा प्रशासकाला सांगा.",
  copilotHowComputed: "हे कसे काढले",
  copilotFunction: "अहवाल",
  copilotArgs: "मापदंड",
  copilotMethod: "गणना",
  copilotInferenceMock: "नियमाधारित (AI मॉडेल नाही)",
  copilotInferenceLive: "AI मॉडेल",
  copilotCredits: "वापरलेले AI क्रेडिट",
  copilotNotAnswered: "उत्तर दिले नाही",
  copilotDisclaimer:
    "फक्त व्यवस्थापकीय माहिती — वैद्यकीय सल्ला नाही. महत्त्वाचे आकडे अहवालांमध्ये तपासा.",
  copilotHistory: "या सत्रातील प्रश्न",
};

const hi: Dict = {
  navCopilot: "कोपायलट",
  copilotTitle: "व्यवसाय कोपायलट",
  copilotIntro:
    "इस क्लिनिक के सत्यापित आँकड़ों के बारे में पूछें। सहायक केवल रिपोर्ट चुनता है; आँकड़े सिस्टम आपके रिकॉर्ड से निकालता है।",
  copilotAskLabel: "आपका प्रश्न",
  copilotAsk: "पूछें",
  copilotExamples: "उदाहरण:",
  copilotEnablePrompt: "कोपायलट आपके संस्करण में शामिल है, पर इस क्लिनिक के लिए बंद है।",
  copilotEnable: "कोपायलट चालू करें",
  copilotEnableNotice:
    "प्रश्नों के उत्तर इसी सिस्टम में दिए जाते हैं। डिफ़ॉल्ट सेटिंग में कोई डेटा बाहरी AI सेवा को नहीं भेजा जाता।",
  copilotNotEnabledAskAdmin: "कोपायलट चालू करने के लिए क्लिनिक के मालिक या एडमिन से कहें।",
  copilotHowComputed: "यह कैसे निकाला गया",
  copilotFunction: "रिपोर्ट",
  copilotArgs: "पैरामीटर",
  copilotMethod: "गणना",
  copilotInferenceMock: "नियम-आधारित (AI मॉडल नहीं)",
  copilotInferenceLive: "AI मॉडल",
  copilotCredits: "उपयोग किए गए AI क्रेडिट",
  copilotNotAnswered: "उत्तर नहीं दिया",
  copilotDisclaimer:
    "केवल प्रबंधन संबंधी जानकारी — चिकित्सा सलाह नहीं। महत्वपूर्ण आँकड़े रिपोर्ट में जाँचें।",
  copilotHistory: "इस सत्र के प्रश्न",
};

export const aiDictionaries = { en, mr, hi };
