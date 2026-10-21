"""Clinical Scribe — DRAFT workflow core (docs/AI_ARCHITECTURE.md §3).

Pipeline: consent → transcript (``Transcriber``) → segments → SOAP **draft**
(deterministic trilingual sectioniser behind the gateway's mock provider) →
clinician edits → accept (normal encounter update rules) or discard.

Safety rules enforced in code, not prompts:
* every Statement quotes transcript text and references ≥ 1 segment;
* medications appear ONLY under ``medications_discussed_verbatim``, copied
  verbatim and flagged ``verify`` — never converted to prescription items,
  never dose-normalised, never invented (a medication statement that is not
  a verbatim substring of its segment fails validation);
* assessment / plan contain only what the CLINICIAN said;
* the schema has no diagnosis-code fields (extra keys are rejected).

ASR: no speech model is available in this deployment. ``MockTranscriber``
uses the transcript the clinician typed/pasted (clearly labelled);
``SelfHostedASRAdapter`` documents the interface for a self-hosted India-
region ASR server (Whisper-family / IndicConformer) and is DISABLED.
Audio is not stored in this phase.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DRAFT_SCHEMA = "scribe.soap.v1"
SECTIONISER_VERSION = "scribe-rules-1.0"


# --- transcription ---------------------------------------------------------------------------
@dataclass
class Segment:
    id: int
    speaker: str          # clinician | patient | other | unknown
    text: str
    lang: str


@dataclass
class AudioMeta:
    duration_s: float
    mime: str


class TranscriberUnavailable(Exception):
    pass


class Transcriber(Protocol):
    name: str
    label: str
    available: bool

    def transcribe(self, *, transcript_text: str | None,
                   audio: AudioMeta | None) -> list[Segment]: ...


class MockTranscriber:
    """Returns the transcript supplied by the user, segmented. It does NOT
    listen to audio — it exists so the full workflow can be exercised."""

    name = "mock_transcriber"
    label = "Mock transcription: uses the typed/pasted transcript (no speech recognition)"
    available = True

    def transcribe(self, *, transcript_text: str | None,
                   audio: AudioMeta | None) -> list[Segment]:
        if not transcript_text or not transcript_text.strip():
            raise TranscriberUnavailable(
                "Speech recognition is not available in this deployment; paste or type the "
                "consultation transcript instead.")
        return segment_transcript(transcript_text)


class SelfHostedASRAdapter:
    """Interface for a self-hosted, India-region ASR server (e.g. faster-whisper
    large-v3 or AI4Bharat IndicConformer behind an HTTP endpoint). Audio is C3
    and may only go to vendor-controlled infrastructure in India (§2.4).

    DISABLED: no model has been evaluated against §3.6 yet, so this adapter
    refuses every call. Enabling it requires the evaluation, legal review and
    a settings change — never a code default."""

    name = "selfhosted_asr"
    label = "Self-hosted ASR (disabled — not evaluated)"
    available = False

    def transcribe(self, *, transcript_text: str | None,
                   audio: AudioMeta | None) -> list[Segment]:
        raise TranscriberUnavailable("Self-hosted ASR is disabled in this phase")


# --- segmentation ----------------------------------------------------------------------------
_SPEAKERS = [
    ("clinician", r"doctor|dr\.?|d|डॉक्टर|डॉ\.?|डॉक्टर साहेब|वैद्य"),
    ("patient", r"patient|pt\.?|p|रुग्ण|पेशंट|पेशन्ट|मरीज़?|रोगी"),
    ("other", r"relative|mother|father|attendant|नातेवाईक|आई|वडील|परिजन|माँ|पिता"),
]
_SPEAKER_RE = re.compile(
    r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(" + "|".join(p for _, p in _SPEAKERS)
    + r")\s*[:：\-–]\s*", re.IGNORECASE)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")


def lang_of(text: str) -> str:
    dev = len(_DEVANAGARI.findall(text))
    lat = len(_LATIN.findall(text))
    if dev == 0:
        return "en"
    if lat and 0.15 <= lat / (dev + lat) <= 0.85:
        return "mixed"
    mr = ("आहे", "आहेत", "दिवसांपासून", "नाही", "करा", "घ्या", "होतोय", "होतंय", "दुखतंय")
    return "mr" if any(m in text for m in mr) else "hi"


def _speaker(label: str) -> str:
    for role, pat in _SPEAKERS:
        if re.fullmatch(pat, label.strip(), re.IGNORECASE):
            return role
    return "unknown"


def segment_transcript(text: str) -> list[Segment]:
    text = unicodedata.normalize("NFC", text)
    segs: list[Segment] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = _SPEAKER_RE.match(line)
        speaker = _speaker(m.group(1)) if m else "unknown"
        body = line[m.end():].strip() if m else line
        if not body:
            continue
        segs.append(Segment(len(segs), speaker, body, lang_of(body)))
    return segs


_SENT = re.compile(r"(?<=[.!?।])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if s.strip()]


# --- sectioniser rules (EN / मराठी / हिंदी, code-mixed) -------------------------------------
def _kw(*words: str) -> re.Pattern:
    return re.compile("|".join(words), re.IGNORECASE)


MED_FORM = _kw(r"\btab(?:let)?s?\b", r"\bcap(?:sule)?s?\b", r"\bsyr(?:up)?\b",
               r"\binj(?:ection)?\b", r"\bointment\b", r"\bdrops?\b", r"गोळी", r"गोळ्या",
               r"टॅबलेट", r"टॅब्लेट", r"सिरप",
               r"इंजेक्शन", r"मलम", r"गोली", r"गोलियां", r"टैबलेट", r"दवा", r"दवाई", r"औषध")
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|µg|g|ml|iu|units?)\b"
                  r"|\d+\s?(?:मिग्रॅ|मि\.ग्रॅ|मिलीग्राम)", re.IGNORECASE)
VITALS = _kw(r"\bbp\b", r"blood pressure", r"\d{2,3}\s*/\s*\d{2,3}", r"\bpulse\b", r"\bspo2\b",
             r"saturation", r"temperature", r"\btemp\b", r"°\s?[fc]\b", r"\bmmhg\b", r"\bweight\b",
             r"\bkg\b", r"रक्तदाब", r"बीपी", r"नाडी", r"तापमान", r"वजन", r"ऑक्सिजन",
             r"नब्ज़?", r"धड़कन", r"ब्लड प्रेशर")
FINDINGS = _kw(r"on examination", r"\bo/e\b", r"examin", r"chest (?:is )?clear", r"tender",
               r"swelling", r"\brash\b", r"throat (?:is )?(?:red|congested)", r"\bcrepitations?\b",
               r"तपासणीत", r"तपासले", r"सूज", r"लालसर", r"जांच में", r"जाँच में", r"सूजन",
               r"गला लाल")
ASSESS = _kw(r"looks like", r"\blikely\b", r"probabl", r"suggestive of", r"\bdiagnos",
             r"impression", r"i think (?:it|this) is", r"seems to be", r"consistent with",
             r"वाटत", r"असावा", r"असावी", r"असू शकत", r"निदान", r"लगता है", r"लग रहा है",
             r"संभवतः", r"शायद")
PLAN = _kw(r"\badvi[sc]e", r"\btest\b", r"\btests\b", r"x-?ray", r"blood test", r"\bcbc\b",
           r"follow[- ]?up", r"\breview\b", r"come back", r"\brest\b", r"drink", r"\bavoid\b",
           r"after \d+ days", r"\bscan\b", r"\brefer", r"पुन्हा", r"चाचणी", r"विश्रांती", r"टाळा",
           r"दिवसांनी", r"तपासणी करा", r"फिर से", r"जांच कर", r"जाँच कर", r"आराम", r"परहेज",
           r"दिन बाद", r"पानी", r"पाणी")
HISTORY = _kw(r"history of", r"\bdiabet", r"hypertens", r"\bbp patient\b", r"allerg",
              r"surgery", r"operated", r"asthma", r"मधुमेह", r"शुगर", r"ऍलर्जी", r"अॅलर्जी",
              r"एलर्जी", r"ऑपरेशन", r"दमा", r"पहले से", r"आधीपासून")
SYMPTOM = _kw(r"\bpain\b", r"fever", r"cough", r"\bsince\b", r"\bdays?\b", r"vomit", r"headache",
              r"\bcold\b", r"weak", r"dizz", r"breath", r"loose motion", r"diarrh", r"itch",
              r"दुखत", r"दुखणे", r"ताप", r"खोकला", r"सर्दी", r"उलटी", r"दिवसांपासून", r"चक्कर",
              r"जुलाब", r"बुखार", r"दर्द", r"खांसी", r"उल्टी", r"दिन से", r"कमजोरी", r"कमज़ोरी",
              r"दस्त", r"सांस", r"श्वास")
UNCERTAIN = _kw(r"\[inaudible\]", r"\[unclear\]", r"\?\?\?", r"\(inaudible\)", r"अस्पष्ट")


def medication_mentions(sentence: str, drug_names: list[str]) -> list[str]:
    """Verbatim substrings that name a drug or a dose. Catalogue names are
    matched case-insensitively but returned exactly as written in the
    transcript. Nothing is normalised or completed."""
    found: list[str] = []
    low = sentence.lower()
    for name in drug_names:
        n = name.lower()
        if len(n) >= 4:
            i = low.find(n)
            if i >= 0:
                found.append(sentence[i:i + len(n)])
    for m in re.finditer(r"(?i)\b(?:tab(?:let)?|cap(?:sule)?|syr(?:up)?|inj(?:ection)?)\.?\s+"
                         r"([A-Za-z][A-Za-z0-9-]{2,})", sentence):
        found.append(m.group(0))
    for m in DOSE.finditer(sentence):
        found.append(m.group(0))
    return list(dict.fromkeys(found))


SECTIONS = ("chief_complaint", "history_present_illness", "relevant_history",
            "findings_stated", "vitals_stated", "assessment_stated_by_clinician",
            "plan_stated_by_clinician", "medications_discussed_verbatim",
            "uncertain_or_inaudible", "unclassified")


def classify(sentence: str, speaker: str, drug_names: list[str]) -> str:
    """Deterministic rule order: uncertain → medication → vitals → findings →
    (clinician) assessment / plan → history → symptoms → unclassified."""
    clinician = speaker in ("clinician", "unknown")
    if UNCERTAIN.search(sentence):
        return "uncertain_or_inaudible"
    if MED_FORM.search(sentence) or DOSE.search(sentence) or medication_mentions(
            sentence, drug_names):
        return "medications_discussed_verbatim"
    if VITALS.search(sentence) and clinician:
        return "vitals_stated"
    if FINDINGS.search(sentence) and clinician:
        return "findings_stated"
    if speaker == "clinician" and sentence.rstrip().endswith("?"):
        return "unclassified"  # questions are not statements of fact
    if clinician and ASSESS.search(sentence):
        return "assessment_stated_by_clinician"
    if clinician and PLAN.search(sentence):
        return "plan_stated_by_clinician"
    if HISTORY.search(sentence):
        return "relevant_history"
    if SYMPTOM.search(sentence) and speaker != "clinician":
        return "history_present_illness"
    return "unclassified"


def sectionise(segments: list[Segment], drug_names: list[str]) -> dict:
    """Build the draft SOAP dict (``SoapDraft`` schema) from segments."""
    out: dict[str, list] = {k: [] for k in SECTIONS}
    for seg in segments:
        for sent in split_sentences(seg.text):
            section = classify(sent, seg.speaker, drug_names)
            stmt: dict = {"text": sent, "source_segments": [seg.id],
                          "confidence": "medium" if section != "unclassified" else "low"}
            if section == "medications_discussed_verbatim":
                stmt["mentions"] = medication_mentions(sent, drug_names)
                stmt["verify"] = True
            out[section].append(stmt)
    # the first patient symptom statement is the chief complaint
    if out["history_present_illness"]:
        out["chief_complaint"].append(out["history_present_illness"].pop(0))
    langs = {s.lang for s in segments}
    note_lang = (langs.pop() if len(langs) == 1 else "mixed") if langs else "en"
    return {
        "schema_version": DRAFT_SCHEMA, "language_of_note": note_lang,
        "subjective": {"chief_complaint": out["chief_complaint"],
                       "history_present_illness": out["history_present_illness"],
                       "relevant_history": out["relevant_history"]},
        "objective": {"findings_stated": out["findings_stated"],
                      "vitals_stated": out["vitals_stated"]},
        "assessment_stated_by_clinician": out["assessment_stated_by_clinician"],
        "plan_stated_by_clinician": out["plan_stated_by_clinician"],
        "medications_discussed_verbatim": out["medications_discussed_verbatim"],
        "uncertain_or_inaudible": out["uncertain_or_inaudible"],
        "unclassified": out["unclassified"],
    }


# --- output schema + validation ----------------------------------------------------------------
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Statement(_Strict):
    text: str = Field(min_length=1, max_length=2000)
    source_segments: list[int] = Field(min_length=1)
    confidence: Literal["low", "medium", "high"]


class MedStatement(Statement):
    mentions: list[str] = []
    verify: Literal[True] = True


class Subjective(_Strict):
    chief_complaint: list[Statement]
    history_present_illness: list[Statement]
    relevant_history: list[Statement]


class Objective(_Strict):
    findings_stated: list[Statement]
    vitals_stated: list[Statement]


class SoapDraft(_Strict):
    schema_version: Literal["scribe.soap.v1"]
    language_of_note: Literal["en", "mr", "hi", "mixed"]
    subjective: Subjective
    objective: Objective
    assessment_stated_by_clinician: list[Statement]
    plan_stated_by_clinician: list[Statement]
    medications_discussed_verbatim: list[MedStatement]
    uncertain_or_inaudible: list[Statement]
    unclassified: list[Statement]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().lower()


def all_statements(d: SoapDraft):
    yield from (("chief_complaint", s) for s in d.subjective.chief_complaint)
    yield from (("history_present_illness", s) for s in d.subjective.history_present_illness)
    yield from (("relevant_history", s) for s in d.subjective.relevant_history)
    yield from (("findings_stated", s) for s in d.objective.findings_stated)
    yield from (("vitals_stated", s) for s in d.objective.vitals_stated)
    for key in ("assessment_stated_by_clinician", "plan_stated_by_clinician",
                "medications_discussed_verbatim", "uncertain_or_inaudible", "unclassified"):
        yield from ((key, s) for s in getattr(d, key))


def validate_draft(output: object, segments: list[Segment]) -> tuple[bool, list[str]]:
    """Structured-output + hallucination checks for ANY provider's draft."""
    try:
        draft = SoapDraft.model_validate(output)
    except ValidationError as exc:
        return False, [f"schema: {e['loc']} {e['msg']}" for e in exc.errors()[:5]]
    by_id = {s.id: s for s in segments}
    problems: list[str] = []
    for section, st in all_statements(draft):
        if any(i not in by_id for i in st.source_segments):
            problems.append(f"{section}: unknown source segment")
            continue
        source = " ".join(by_id[i].text for i in st.source_segments)
        if _norm(st.text) not in _norm(source):
            problems.append(f"{section}: statement is not verbatim from its segment(s)")
        if section == "medications_discussed_verbatim":
            for m in st.mentions:  # type: ignore[attr-defined]
                if _norm(m) not in _norm(st.text):
                    problems.append("medication mention not verbatim")
        elif section in ("assessment_stated_by_clinician", "plan_stated_by_clinician"):
            if any(by_id[i].speaker not in ("clinician", "unknown") for i in st.source_segments):
                problems.append(f"{section}: not stated by the clinician")
        if section != "medications_discussed_verbatim" and DOSE.search(st.text):
            problems.append(f"{section}: dose outside the verbatim medication list")
    return (not problems, problems)


def draft_to_note(d: dict) -> dict:
    """Pre-fill for the clinician's editor (encounter fields). Medications are
    deliberately NOT copied into the plan — they stay in a separate verbatim
    list the clinician must verify and prescribe through the normal Rx flow."""
    j = lambda xs: "\n".join(s["text"] for s in xs)  # noqa: E731
    sub, obj = d["subjective"], d["objective"]
    return {
        "chief_complaint": j(sub["chief_complaint"])[:500],
        "history": "\n".join(x for x in (j(sub["history_present_illness"]),
                                         j(sub["relevant_history"])) if x)[:5000],
        "examination": "\n".join(x for x in (j(obj["vitals_stated"]),
                                             j(obj["findings_stated"])) if x)[:5000],
        "assessment": j(d["assessment_stated_by_clinician"])[:5000],
        "plan": j(d["plan_stated_by_clinician"])[:5000],
    }
