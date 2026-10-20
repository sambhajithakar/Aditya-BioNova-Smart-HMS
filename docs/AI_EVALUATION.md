# AI-1 Evaluation — Aditya BioNova Smart HMS

| | |
|---|---|
| Date | 2026-10-20 |
| Scope | Phase AI-1: statistical forecasting, no-show risk, knowledge assistant (RAG), agent proposals, Clinical Scribe draft workflow |
| Data | **Synthetic only** — seeded generators (`apps/api/app/ai/synthetic.py`) and hand-written SOP / transcript sets (`apps/api/app/ai/eval_data.py`). No real patient, staff or clinic data. |
| Reproduce | `cd apps/api && python -m app.ai.evaluation` (deterministic; ~4 s; no network, no model download). Thresholds asserted in `tests/test_ai1_evaluation.py`. |

**Read this first.** These numbers show the code works as designed on data whose
generating mechanism we know. They are **not** evidence of accuracy at a real clinic.
The RAG and scribe sets were written by the same engineer who wrote the rules, so
the development-set numbers are optimistic; the held-out sets (written after the
rules were frozen and never used for tuning) are the more honest figures, and they
are small. Nothing here is a clinical-performance claim.

## 1. What is real and what is mock

| Feature | Inference | Notes |
|---|---|---|
| OPD demand, bed occupancy, pharmacy / inventory demand | **Statistical model** (real, pure Python) | Seasonal naive, 4-week seasonal mean, Holt-Winters additive (damped, weekly), SES, Croston-SBA. No AI provider. |
| No-show risk | **Statistical model** (real) | L2-regularised logistic regression (Newton/IRLS) vs a rate baseline. |
| Knowledge assistant | **BM25 retrieval (real) + mock inference** | Answers are extractive quotes with citations. No language model is called. |
| Agents | **Deterministic planners** | No model. Proposals need human approval. |
| Scribe | **Mock transcription + rule-based sectioniser (mock inference)** | No speech recognition. The clinician types or pastes the transcript. No audio is stored. |
| Document AI / OCR | **Not implemented** | No OCR engine is available here. |

## 2. Forecasting (rolling-origin backtest + 14-day hold-out)

Method: each series is split into training data and the last 14 days, which are held out.
Model choice uses only the training data: a rolling-origin backtest (up to 8 origins,
7 days apart, horizon 14), picking the lowest MAE. The tables then score the chosen
model and the baseline on the 14 held-out days.

| Use case | Series | Baseline | Baseline MAE | Selected-model MAE | Other |
|---|---|---|---|---|---|
| OPD daily visits (182 training days, weekly seasonality + trend + noise) | 20 | seasonal naive | 4.207 | **3.261** | MAPE 6.91 % vs 8.68 %; selected model better on 85 % of series; Holt-Winters chosen 17/20 |
| Bed census from synthetic admissions (200 days) | 10 | last value | 3.793 | **3.235** | 4-week seasonal mean chosen 6/10, Holt-Winters 4/10 |
| Intermittent drug demand (112 days), error of the 14-day total | 20 | 28-day moving average | **16.95** | 17.36 | **No improvement.** The selected model was about 2 % worse on the hold-out. The API reports "not better than baseline" whenever its own backtest shows this. |

Prediction intervals are empirical quantiles of the selected method's backtest errors.
Hold-out coverage on the OPD series: **80 % interval → 78.6 %**, **95 % interval → 92.5 %**.

Minimum history before the API returns a forecast (otherwise it returns `insufficient_data`
with what is required): OPD 56 days, beds 180 days, demand 84 days with at least
6 weeks of use. These follow AI_ARCHITECTURE.md §6.1.

## 3. No-show risk

Data: 5 synthetic datasets of 1,560 finished appointments each. The no-show mechanism
is known: lead time, Saturday, evening slot and a per-patient tendency. The split is
by time: the first 80 % trains the model and the last 20 % tests it.

| Metric (test split, mean of 5) | Logistic model | Baseline (rate by weekday × lead-time bucket) |
|---|---|---|
| Brier score (lower is better) | **0.1670** | 0.1743 |
| AUC | **0.686** | 0.643 |
| ECE (calibration error) | 0.050 | — |

The logistic model was served in 5 of 5 datasets. The server only serves it when its
Brier score beats the baseline. Minimum data: 1,000 finished appointments including
100 no-shows (§6.1). Features never include age, gender, locality, religion, caste or
payment data. The score is used only to prioritise reminders.

## 4. Knowledge assistant (RAG)

Corpus: 14 synthetic SOPs, manuals and policies (6 English, 4 मराठी, 4 हिंदी) plus 1
document with injected instructions. Retrieval is BM25 with a Devanagari-aware
tokeniser and light suffix stripping.

| Set | Questions | hit@3 EN | hit@3 मराठी | hit@3 हिंदी | Extractive answer quoted from the expected document | Unanswerable questions refused |
|---|---|---|---|---|---|---|
| Development | 33 | 1.00 | 1.00 | 1.00 | 0.909 | 4/4 |
| Held-out | 17 | 1.00 | 1.00 | 1.00 | 0.824 | 4/4 |

Limitations:
* The corpus is tiny (14 documents), so hit@3 is easy to achieve.
* Retrieval is lexical only: a Marathi question about an English SOP will not match.
* Questions phrased with synonyms not used in the document will miss.

These are the reasons the doc keeps embeddings / hybrid retrieval in a later phase (§7.3).

## 5. Prompt-injection and hallucination guards — 13/13 resisted

| Case group | Cases | Result |
|---|---|---|
| Questions asked against an approved SOP that contains "ignore previous instructions…", "SYSTEM: you are now admin…" | 4 | Instruction-like sentences are never quoted. They are counted as `injection_flags` at upload and shown to the approver. |
| Fake live-model outputs: "HACKED", an invented patient phone number, an unsupported claim, a citation of a chunk that was not retrieved, a quote of the injected instruction, free text without the schema | 6 | All rejected by the Pydantic schema plus the groundedness check. Support may only come from non-instruction sentences. |
| Scribe drafts with an invented medication, an ICD-code field, or a patient sentence placed under "assessment" | 3 | All rejected by `validate_draft` |

Writing these tests found a real bug, which is now fixed. "HACKED" had passed the
groundedness check because it appears word for word inside the injected sentence.
Support now only counts from the chunk's non-instruction sentences.

## 6. Clinical Scribe sectioniser

Each transcript line is labelled with its expected section, and accuracy is measured per sentence.

| Set | Transcripts | Utterances | Accuracy | Medications routed to the verbatim list |
|---|---|---|---|---|
| Development (EN, मराठी, हिंदी, Marathi–English and Hindi–English code-mixed) | 8 | 66 | 0.985 | 7/7 |
| Held-out | 3 | 19 | **0.842** | 3/3 |

Held-out errors:
* A Hindi chief complaint with no symptom keyword fell to "unclassified".
* "BP की दवा" (history of BP medicine) was routed to the medication list. This is a conservative error.
* A Hindi plan sentence ("नमक कम कीजिए…") was not recognised as a plan.

Unsorted sentences are shown to the clinician for review and are never dropped silently.

Not measured, because there is no ASR: WER/CER, medical-term recall from audio, and
latency on low bandwidth (§3.6). The scribe must not be piloted on real consultations
until the §3.6 evaluation and the legal review have been done.

## 7. Limitations (summary)

* All datasets are synthetic and small. Real clinic data will be noisier: holidays,
  festivals, data-entry gaps.
* Forecast selection by backtest does not guarantee a hold-out win (see pharmacy demand).
* RAG is lexical only. The scribe is keyword rules only. Both are tuned on development
  sets written by the implementer.
* No fairness audit of the no-show model on real populations. It is used only to
  prioritise reminders.
* No live model has been evaluated. The live paths are covered only by tests with
  fake transports.
