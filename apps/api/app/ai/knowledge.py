"""Knowledge assistant core (RAG, docs/AI_ARCHITECTURE.md §7) — pure Python.

* **Tokeniser**: Unicode-NFC, keeps Devanagari words whole (Python's ``\\w``
  splits them at vowel signs), lower-cases Latin, drops EN/मराठी/हिंदी stop
  words and strips a small set of inflectional suffixes (English plural/-ing/
  -ed, Marathi case endings such as -ाचा/-ची/-मध्ये/-ला, Hindi -ों/-ें). This
  is a light stemmer, not a morphological analyser.
* **Chunker**: Markdown/plain-text headings become the section path; long
  sections are split into ~120-word chunks on sentence boundaries.
* **Retrieval**: Okapi BM25 (k1=1.5, b=0.75) over the tenant's APPROVED,
  role-visible chunks — lexical only (no embeddings in this phase).
* **Answering**: extractive — the best-matching sentences quoted verbatim
  with document/section citations. A live model, if ever enabled, must
  return the same schema and pass :func:`groundedness` or it is rejected.
* **Safety**: :func:`detect_phi` blocks uploads that look like patient data;
  :func:`instruction_like` marks sentences that read like instructions to a
  model — they are never quoted as answers, and retrieved text is always
  passed to a model as delimited DATA, never as instructions.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

# --- tokenisation --------------------------------------------------------------------------
_TOKEN = re.compile(r"[ऀ-ॿ]+|[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

STOP_EN = set("""a an the and or of to in on at for from by with is are was were be been
being it its this that these those as if then than so do does did can could should would
will shall may might must what which who whom whose when where why how i we you he she they
me us our your their my his her them not no yes any all each per into about over under up
out also only very just there here have has had please tell me""".split())
STOP_MR = set("""आहे आहेत होते होता होती आणि व किंवा की ते ती तो हे ही हा या त्या ह्या काय कसे
कशी कसा केव्हा कधी कुठे कोण कोणते कोणती कोणता मध्ये मधे साठी करिता पण तर असे अशी असा
ने ला ना चा ची चे च्या वर खाली एक काही सर्व नाही होय मी आम्ही तुम्ही तू त्यांनी आपण
करावे करावा करावी करणे करा""".split())
STOP_HI = set("""है हैं था थे थी और या कि का की के को में से पर तक ने यह वह ये वे इस उस इन उन
क्या कैसे कब कहाँ कहां कौन कौनसा कौनसी लिए भी तो ही एक कुछ सब सभी नहीं हाँ मैं हम आप
तुम करना करें करे कीजिए चाहिए जाता जाती जाते होता होती होते""".split())
STOP = STOP_EN | STOP_MR | STOP_HI

# longest first; only stripped when a stem of >= 2 characters remains
_MR_HI_SUFFIXES = sorted("""ांच्या ाच्या च्या मध्ये मधील ांना ांचा ांची ांचे ाचा ाची ाचे
ाला ाने ात ांत ावर वर ला ना ने चा ची चे त ों ें ाओं ियों ाएं ीय""".split(), key=len, reverse=True)


def _stem_en(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes")):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def _stem_dev(w: str) -> str:
    for suf in _MR_HI_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            return w[: -len(suf)]
    return w


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).translate(_DEV_DIGITS)
    out = []
    for tok in _TOKEN.findall(text):
        if _DEVANAGARI.match(tok):
            tok = tok.rstrip("।॥")
            if not tok or tok in STOP:
                continue
            out.append(_stem_dev(tok))
        else:
            tok = tok.lower()
            if tok in STOP:
                continue
            out.append(_stem_en(tok))
    return [t for t in out if t]


def detect_language(text: str) -> str:
    if not _DEVANAGARI.search(text):
        return "en"
    mr = ("आहे", "आणि", "करावे", "मध्ये", "च्या", "नाही", "कसे", "काय")
    return "mr" if any(m in text for m in mr) else "hi"


# --- sentences & chunking ---------------------------------------------------------------
_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")
_HEADING = re.compile(r"^\s*(#{1,6})\s+(.*\S)\s*$")
_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+([^\n]{2,80})$")


def sentences(text: str) -> list[str]:
    parts = [p.strip(" \t-*•") for p in _SENT_SPLIT.split(text)]
    return [p for p in parts if len(p) >= 3]


@dataclass
class Chunk:
    ordinal: int
    section: str
    text: str
    tokens: list[str] = field(default_factory=list)


def chunk_document(body: str, title: str, max_words: int = 120) -> list[Chunk]:
    """Split on headings (Markdown ``#`` or short numbered lines), then pack
    sentences into chunks of at most ``max_words`` words."""
    sections: list[tuple[str, list[str]]] = []
    path: list[str] = []
    current: list[str] = []

    def flush():
        if any(line.strip() for line in current):
            sections.append((" › ".join(path) or title, current[:]))
        current.clear()

    for line in body.replace("\r\n", "\n").split("\n"):
        m = _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = path[: level - 1] + [m.group(2).strip()]
            continue
        n = _NUMBERED_HEADING.match(line)
        if n and not line.rstrip().endswith((".", "।")) and len(line.split()) <= 8:
            flush()
            depth = n.group(1).count(".") + 1
            path[:] = path[: depth - 1] + [f"{n.group(1)} {n.group(2).strip()}"]
            continue
        current.append(line)
    flush()

    chunks: list[Chunk] = []
    for section, lines in sections:
        buf: list[str] = []
        words = 0
        for sent in sentences("\n".join(lines)):
            w = len(sent.split())
            if buf and words + w > max_words:
                chunks.append(Chunk(len(chunks), section, " ".join(buf)))
                buf, words = [], 0
            buf.append(sent)
            words += w
        if buf:
            chunks.append(Chunk(len(chunks), section, " ".join(buf)))
    for c in chunks:
        c.tokens = tokenize(f"{c.section} {c.text}")
    return chunks


# --- BM25 ----------------------------------------------------------------------------------
@dataclass
class Hit:
    chunk_id: str
    score: float


def bm25(query_tokens: list[str], docs: dict[str, list[str]], k1: float = 1.5,
         b: float = 0.75, top_k: int = 5) -> list[Hit]:
    if not docs or not query_tokens:
        return []
    n = len(docs)
    avgdl = sum(len(t) for t in docs.values()) / n or 1.0
    df: dict[str, int] = {}
    for toks in docs.values():
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    q = list(dict.fromkeys(query_tokens))
    hits = []
    for cid, toks in docs.items():
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t in q:
            f = tf.get(t)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(toks) / avgdl))
        if score > 0:
            hits.append(Hit(cid, score))
    hits.sort(key=lambda h: (-h.score, h.chunk_id))
    return hits[:top_k]


# --- PHI & injection detectors -------------------------------------------------------------
PHI_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("phone", re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("uhid", re.compile(r"\b[Pp]\d{7}\b")),
    ("national_id", re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),  # Aadhaar-like
    ("abha", re.compile(r"(?<!\d)\d{2}-\d{4}-\d{4}-\d{4}(?!\d)")),
    ("patient_label", re.compile(
        r"(?i)\b(patient name|pt\. name|name of patient|mrn|uhid)\s*[:\-]\s*\S+|"
        r"(रुग्णाचे नाव|मरीज का नाम|रोगी का नाम)\s*[:\-]\s*\S+")),
]


def detect_phi(text: str) -> list[dict]:
    """Return [{type, line}] for anything that looks like a patient identifier.
    Values are never echoed back (the finding itself must not leak them)."""
    findings = []
    for i, line in enumerate(text.split("\n"), start=1):
        for kind, pat in PHI_PATTERNS:
            if pat.search(line):
                findings.append({"type": kind, "line": i})
    return findings


_INJECTION = re.compile(
    r"(?i)(ignore (all |any )?(previous|prior|above|earlier) (instructions|rules)"
    r"|disregard (the |all )?(previous|above|system)|you are now|act as (an? )?(admin|system)"
    r"|^\s*(system|assistant|developer)\s*:|reveal (all )?(patient|password|secret)"
    r"|list all patients|exfiltrate|send (it|them|data) to|<\s*/?\s*(script|system)\s*>"
    r"|override (the )?(rules|policy|instructions)|jailbreak"
    r"|पूर्वीच्या सूचना दुर्लक्ष|सूचना दुर्लक्षित|पिछले निर्देश(ों)? (को )?(अनदेखा|नज़रअंदाज़|नजरअंदाज))")


def instruction_like(sentence: str) -> bool:
    return bool(_INJECTION.search(sentence))


# --- extractive answers ----------------------------------------------------------------
@dataclass
class Passage:
    chunk_id: str
    document_id: str
    document_title: str
    section: str
    version: int
    text: str
    score: float


def extractive_answer(question: str, passages: list[Passage], max_sentences: int = 3,
                      min_overlap: float = 0.34) -> dict:
    """Pick the sentences that best cover the question's terms, verbatim.
    Output schema = the one every provider must satisfy (``RagAnswer``)."""
    q = set(tokenize(question))
    scored = []
    for rank, p in enumerate(passages):
        for s in sentences(p.text):
            if instruction_like(s):
                continue
            toks = set(tokenize(s))
            if not toks or not q:
                continue
            overlap = len(q & toks) / len(q)
            if overlap >= min_overlap:
                scored.append((overlap, -rank, s, p.chunk_id))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    chosen, seen = [], set()
    for _, _, s, cid in scored:
        if s in seen:
            continue
        seen.add(s)
        chosen.append({"text": s, "chunk_id": cid})
        if len(chosen) >= max_sentences:
            break
    return {"sentences": chosen, "refused": not chosen}


def supported(sentence: str, chunk_text: str, threshold: float = 0.8) -> bool:
    """A sentence is supported when it appears verbatim in the chunk, or when
    ≥ ``threshold`` of its content tokens occur in the chunk."""
    norm = lambda s: re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().lower()  # noqa: E731
    if norm(sentence) and norm(sentence) in norm(chunk_text):
        return True
    toks = tokenize(sentence)
    if not toks:
        return False
    chunk_toks = set(tokenize(chunk_text))
    return sum(1 for t in toks if t in chunk_toks) / len(toks) >= threshold


def groundedness(answer: dict, retrieved: dict[str, str]) -> tuple[bool, list[str]]:
    """Every answer sentence must cite a RETRIEVED chunk and be supported by
    it; instruction-like sentences are never acceptable. Returns (ok, problems)."""
    problems = []
    for s in answer.get("sentences", []):
        cid, text = s.get("chunk_id"), s.get("text", "")
        if cid not in retrieved:
            problems.append(f"cites a chunk that was not retrieved: {cid}")
            continue
        # support may only come from the chunk's NON-instruction sentences, so an
        # injected "answer with HACKED" cannot vouch for "HACKED"
        clean = " ".join(x for x in sentences(retrieved[cid]) if not instruction_like(x))
        if not supported(text, clean):
            problems.append(f"unsupported sentence: {text[:80]}")
        elif instruction_like(text):
            problems.append("instruction-like sentence")
    return (not problems, problems)


REFUSAL = {
    "en": "Not found in your clinic's approved documents.",
    "mr": "तुमच्या क्लिनिकच्या मंजूर दस्तऐवजांमध्ये हे सापडले नाही.",
    "hi": "आपके क्लिनिक के स्वीकृत दस्तावेज़ों में यह नहीं मिला।",
}
