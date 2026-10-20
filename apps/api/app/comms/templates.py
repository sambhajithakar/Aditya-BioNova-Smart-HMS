"""Message templates: placeholder whitelist, validation, rendering, defaults.

CONTENT RULE (no clinical details in patient messages)
-----------------------------------------------------
SMS / WhatsApp / e-mail travel over third-party networks, are shown on lock
screens and are often read by family members. Templates therefore carry only
logistics: who (first name), where (clinic / branch / phone), when (date /
time) and with whom (doctor). They may NEVER carry diagnoses, conditions,
medicines, test results, allergies, appointment reasons or clinical notes.

Enforcement:
* Only the placeholders in :data:`ALLOWED_PLACEHOLDERS` are accepted; every
  other ``{name}`` is rejected, and the clinical ones in
  :data:`DISALLOWED_PLACEHOLDERS` get an explicit "clinical content" error so
  the editor understands why.
* Values are filled by the server from tenant data — callers cannot inject
  free text into a message body.
* Template text itself is written by clinic staff; the UI and API state this
  rule next to the editor (free-text clinical wording is a policy violation
  that review/audit catches — ``comms.template_*`` audit events).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CHANNELS = ("email", "sms", "whatsapp")
PURPOSES = ("appointment_reminder", "follow_up", "missed_appointment", "generic")
LANGUAGES = ("en", "mr", "hi")

ALLOWED_PLACEHOLDERS: dict[str, str] = {
    "patient_first_name": "Patient's first name",
    "clinic_name": "Clinic name",
    "clinic_phone": "Clinic phone number",
    "branch_name": "Branch name",
    "doctor_name": "Doctor's name",
    "appointment_date": "Appointment date (clinic time zone)",
    "appointment_time": "Appointment time (clinic time zone)",
    "follow_up_date": "Recommended follow-up date",
}

# Rejected with a specific message: these would leak clinical / identifying data.
DISALLOWED_PLACEHOLDERS = (
    "diagnosis", "diagnoses", "condition", "disease", "symptoms", "complaint",
    "medicine", "medicines", "medication", "medications", "prescription", "drug", "dose",
    "lab_result", "lab_results", "test_result", "result", "report", "allergies",
    "notes", "clinical_notes", "reason", "appointment_reason", "follow_up_reason",
    "procedure", "treatment", "uhid", "patient_full_name", "patient_name",
    "date_of_birth", "age", "address", "phone", "patient_phone", "abha", "aadhaar",
)

MAX_BODY = {"sms": 1000, "whatsapp": 1024, "email": 2000}

_TOKEN_RE = re.compile(r"\{([^{}]*)\}")

# Synthetic sample values for the live preview (never real data).
SAMPLE_VALUES: dict[str, str] = {
    "patient_first_name": "Asha",
    "clinic_name": "Demo Clinic",
    "clinic_phone": "+91 90000 00000",
    "branch_name": "Main Branch",
    "doctor_name": "Dr. Demo",
    "appointment_date": "15 Jan 2026",
    "appointment_time": "10:30 AM",
    "follow_up_date": "22 Jan 2026",
}


def placeholders_in(text: str) -> list[str]:
    return [m.group(1).strip() for m in _TOKEN_RE.finditer(text or "")]


def validate_template_text(text: str, *, field: str = "body") -> list[str]:
    """Return human-readable problems (empty list = valid)."""
    errors: list[str] = []
    stripped = _TOKEN_RE.sub("", text or "")
    if "{" in stripped or "}" in stripped:
        errors.append(f"{field}: unbalanced or nested braces")
    seen: set[str] = set()
    for name in placeholders_in(text):
        if name in seen:
            continue
        seen.add(name)
        key = name.lower()
        if key in DISALLOWED_PLACEHOLDERS:
            errors.append(
                f"{field}: placeholder {{{name}}} is not allowed — messages must not "
                "contain clinical or identifying details")
        elif name not in ALLOWED_PLACEHOLDERS:
            errors.append(f"{field}: unknown placeholder {{{name}}}")
    return errors


def validate_template(channel: str, body: str, subject: str = "") -> list[str]:
    errors = validate_template_text(body, field="body")
    if channel == "email":
        errors += validate_template_text(subject, field="subject")
    limit = MAX_BODY.get(channel, 1000)
    if len(body or "") > limit:
        errors.append(f"body: longer than {limit} characters for {channel}")
    if not (body or "").strip():
        errors.append("body: must not be empty")
    return errors


def render(text: str, values: dict[str, str]) -> str:
    """Fill whitelisted placeholders; anything else is left visibly unfilled."""
    def repl(m: re.Match) -> str:
        name = m.group(1).strip()
        if name in ALLOWED_PLACEHOLDERS:
            return values.get(name, "")
        return m.group(0)

    return _TOKEN_RE.sub(repl, text or "")


def ordered_variables(text: str, values: dict[str, str]) -> list[str]:
    """Variable values in body order (DLT / WhatsApp template parameters)."""
    return [values.get(n, "") for n in placeholders_in(text) if n in ALLOWED_PLACEHOLDERS]


# --------------------------------------------------------------------- defaults
@dataclass(frozen=True)
class DefaultTemplate:
    purpose: str
    language: str
    subject: str
    body: str


_STOP = {"en": "Reply STOP to opt out.",
         "mr": "संदेश नको असल्यास STOP पाठवा.",
         "hi": "संदेश बंद करने के लिए STOP भेजें।"}

_DEFAULTS: list[DefaultTemplate] = [
    DefaultTemplate(
        "appointment_reminder", "en", "Appointment reminder — {clinic_name}",
        "Hello {patient_first_name}, this is a reminder of your appointment at {clinic_name} "
        "on {appointment_date} at {appointment_time} with {doctor_name}."),
    DefaultTemplate(
        "appointment_reminder", "mr", "भेटीची आठवण — {clinic_name}",
        "नमस्कार {patient_first_name}, {clinic_name} येथे {appointment_date} रोजी "
        "{appointment_time} वाजता {doctor_name} यांच्याकडे तुमची भेट आहे, याची आठवण."),
    DefaultTemplate(
        "appointment_reminder", "hi", "अपॉइंटमेंट की याद — {clinic_name}",
        "नमस्ते {patient_first_name}, {clinic_name} में {appointment_date} को "
        "{appointment_time} बजे {doctor_name} के साथ आपकी अपॉइंटमेंट की याद दिलाई जा रही है।"),
    DefaultTemplate(
        "follow_up", "en", "Follow-up visit — {clinic_name}",
        "Hello {patient_first_name}, {clinic_name} recommends a follow-up visit around "
        "{follow_up_date}. Please call {clinic_phone} to book."),
    DefaultTemplate(
        "follow_up", "mr", "पुन्हा तपासणी — {clinic_name}",
        "नमस्कार {patient_first_name}, {clinic_name} कडून {follow_up_date} च्या सुमारास "
        "पुन्हा तपासणीसाठी येण्याची सूचना. भेट ठरवण्यासाठी {clinic_phone} वर संपर्क करा."),
    DefaultTemplate(
        "follow_up", "hi", "फ़ॉलो-अप विज़िट — {clinic_name}",
        "नमस्ते {patient_first_name}, {clinic_name} की ओर से {follow_up_date} के आसपास "
        "फ़ॉलो-अप विज़िट की सलाह है। अपॉइंटमेंट के लिए {clinic_phone} पर कॉल करें।"),
    DefaultTemplate(
        "missed_appointment", "en", "We missed you — {clinic_name}",
        "Hello {patient_first_name}, we missed you at {clinic_name} on {appointment_date}. "
        "Please call {clinic_phone} to reschedule."),
    DefaultTemplate(
        "missed_appointment", "mr", "भेट चुकली — {clinic_name}",
        "नमस्कार {patient_first_name}, {appointment_date} रोजी {clinic_name} येथील तुमची "
        "भेट होऊ शकली नाही. नवीन वेळ ठरवण्यासाठी {clinic_phone} वर संपर्क करा."),
    DefaultTemplate(
        "missed_appointment", "hi", "अपॉइंटमेंट छूट गई — {clinic_name}",
        "नमस्ते {patient_first_name}, {appointment_date} को {clinic_name} में आपकी "
        "अपॉइंटमेंट छूट गई। नया समय तय करने के लिए {clinic_phone} पर कॉल करें।"),
]


def default_templates() -> list[tuple[str, DefaultTemplate, str]]:
    """(channel, template, full body) for every channel × purpose × language."""
    out = []
    for channel in CHANNELS:
        for d in _DEFAULTS:
            body = d.body if channel == "email" else f"{d.body} {_STOP[d.language]}"
            out.append((channel, d, body))
    return out


FALLBACKS = {
    "clinic_phone": {"en": "the clinic", "mr": "क्लिनिक", "hi": "क्लिनिक"},
    "doctor_name": {"en": "your doctor", "mr": "डॉक्टर", "hi": "डॉक्टर"},
}
