"""Reproducible AI-1 evaluation on SYNTHETIC data (docs/AI_EVALUATION.md).

    cd apps/api && python -m app.ai.evaluation          # prints Markdown tables

Deterministic: fixed seeds, no network, no model download. The same functions
are asserted against thresholds in tests/test_ai1_evaluation.py.
"""
from __future__ import annotations

import statistics

from . import eval_data as D
from . import forecasting as F
from . import knowledge as K
from . import noshow as N
from . import scribe as S
from . import synthetic as Y


def eval_opd(seeds=range(20), n_days=182, h=14) -> dict:
    sel_mae, base_mae, sel_mape, base_mape, wins, methods = [], [], [], [], 0, {}
    cov80 = cov95 = total = 0
    for seed in seeds:
        y = Y.opd_daily_visits(n_days + h, seed=seed, base=30 + seed % 7 * 5)
        train, test = y[:n_days], y[n_days:]
        fc = F.forecast_series(train, h, F.DAILY_METHODS, F.DAILY_BASELINE, min_train=28)
        methods[fc.method] = methods.get(fc.method, 0) + 1
        base = F.seasonal_naive(train, h)
        sel_mae.append(F.mae(test, fc.points))
        base_mae.append(F.mae(test, base))
        sel_mape.append(F.mape(test, fc.points))
        base_mape.append(F.mape(test, base))
        wins += sel_mae[-1] < base_mae[-1]
        for a, lo, hi, lo95, hi95 in zip(test, fc.lo80, fc.hi80, fc.lo95, fc.hi95):
            cov80 += lo <= a <= hi
            cov95 += lo95 <= a <= hi95
            total += 1
    return {"series": len(sel_mae), "horizon_days": h, "train_days": n_days,
            "selected_mae": round(statistics.mean(sel_mae), 3),
            "baseline_mae": round(statistics.mean(base_mae), 3),
            "selected_mape": round(statistics.mean(sel_mape), 2),
            "baseline_mape": round(statistics.mean(base_mape), 2),
            "selected_beats_baseline_share": round(wins / len(sel_mae), 3),
            "coverage80": round(cov80 / total, 3), "coverage95": round(cov95 / total, 3),
            "methods_selected": methods}


def eval_demand(seeds=range(20), n_days=112, h=14) -> dict:
    sel, base, methods = [], [], {}
    for seed in seeds:
        y = Y.intermittent_demand(n_days + h, seed=seed, p_demand=0.2 + seed % 5 * 0.1)
        train, test = y[:n_days], y[n_days:]
        fc = F.forecast_series(train, h, F.DEMAND_METHODS, F.DEMAND_BASELINE, min_train=28,
                               max_folds=4)
        methods[fc.method] = methods.get(fc.method, 0) + 1
        # 14-day total error: what reorder quantities depend on
        sel.append(abs(sum(test) - sum(fc.points)))
        base.append(abs(sum(test) - sum(F.moving_average(train, h))))
    return {"series": len(sel), "metric": "absolute error of the 14-day total (units)",
            "selected_mae_14d_total": round(statistics.mean(sel), 2),
            "baseline_mae_14d_total": round(statistics.mean(base), 2),
            "methods_selected": methods}


def eval_beds(seeds=range(10), n_days=200, h=14) -> dict:
    sel, base, methods = [], [], {}
    for seed in seeds:
        adm = Y.admissions(n_days + h, seed=seed, per_day=2 + seed % 4)
        census = F.daily_census(adm, n_days + h)
        train, test = census[:n_days], census[n_days:]
        methods_ = {"naive_last": F.naive_last, **F.DAILY_METHODS}
        fc = F.forecast_series(train, h, methods_, "naive_last", min_train=56)
        methods[fc.method] = methods.get(fc.method, 0) + 1
        sel.append(F.mae(test, fc.points))
        base.append(F.mae(test, F.naive_last(train, h)))
    return {"series": len(sel), "selected_mae": round(statistics.mean(sel), 3),
            "baseline_mae": round(statistics.mean(base), 3), "methods_selected": methods,
            "note": "census rebuilt from synthetic admissions; future discharges of "
                    "current inpatients are unknown, as in production"}


def eval_noshow(seeds=range(5)) -> dict:
    rows = []
    for seed in seeds:
        r = N.train_and_score(Y.appointments(1600, seed=seed))
        rows.append(r)
    m = lambda k, src: round(statistics.mean(getattr(r, src)[k] for r in rows), 4)  # noqa
    return {"datasets": len(rows), "appointments_each": 1600 - 40,
            "model_brier": m("brier", "metrics"), "baseline_brier": m("brier",
                                                                      "baseline_metrics"),
            "model_auc": m("auc", "metrics"), "baseline_auc": m("auc", "baseline_metrics"),
            "model_ece": m("ece", "metrics"),
            "served_logistic": sum(r.served == "logistic_regression" for r in rows)}


def _kb():
    chunks: dict[str, tuple[str, str, str]] = {}   # id -> (title, section, text)
    tokens: dict[str, list[str]] = {}
    for title, _lang, body in D.SOP_CORPUS + [D.INJECTED_SOP]:
        for c in K.chunk_document(body, title):
            cid = f"{title}#{c.ordinal}"
            chunks[cid] = (title, c.section, c.text)
            tokens[cid] = c.tokens
    return chunks, tokens


def eval_rag(top_k=3, qa=None) -> dict:
    qa = qa or D.SOP_QA
    chunks, tokens = _kb()
    per_lang: dict[str, list[int]] = {}
    for q, lang, title, section in qa:
        hits = K.bm25(K.tokenize(q), tokens, top_k=top_k)
        ok = any(chunks[h.chunk_id][0] == title and section.lower() in
                 chunks[h.chunk_id][1].lower() for h in hits)
        per_lang.setdefault(lang, []).append(int(ok))
    answered_correctly = 0
    for q, lang, title, section in qa:
        hits = K.bm25(K.tokenize(q), tokens, top_k=5)
        ps = [K.Passage(h.chunk_id, "", chunks[h.chunk_id][0], chunks[h.chunk_id][1], 1,
                        chunks[h.chunk_id][2], h.score) for h in hits if h.score >= 0.5]
        ans = K.extractive_answer(q, ps)
        retrieved = {p.chunk_id: p.text for p in ps}
        grounded, _ = K.groundedness(ans, retrieved)
        if not ans["refused"] and grounded and chunks[ans["sentences"][0]["chunk_id"]][0] \
                == title:
            answered_correctly += 1
    refused = 0
    for q, _lang in D.UNANSWERABLE:
        hits = K.bm25(K.tokenize(q), tokens, top_k=5)
        ps = [K.Passage(h.chunk_id, "", "", "", 1, chunks[h.chunk_id][2], h.score)
              for h in hits if h.score >= 0.5]
        refused += K.extractive_answer(q, ps)["refused"]
    return {"questions": len(qa), "top_k": top_k,
            "hit_at_k": {lang: round(sum(v) / len(v), 3) for lang, v in per_lang.items()},
            "hit_at_k_overall": round(sum(sum(v) for v in per_lang.values())
                                      / len(qa), 3),
            "extractive_answer_from_expected_doc": round(answered_correctly / len(qa), 3),
            "unanswerable_refused": f"{refused}/{len(D.UNANSWERABLE)}"}


def eval_injection() -> dict:
    chunks, tokens = _kb()
    cases = passed = 0
    # (a) instruction-like sentences in an approved document are never quoted
    for q in D.INJECTION_QUESTIONS:
        hits = K.bm25(K.tokenize(q), tokens, top_k=5)
        ps = [K.Passage(h.chunk_id, "", "", "", 1, chunks[h.chunk_id][2], h.score)
              for h in hits]
        ans = K.extractive_answer(q, ps)
        cases += 1
        passed += all(not K.instruction_like(s["text"]) and "HACKED" not in s["text"]
                      for s in ans["sentences"])
    # (b) fake live-model outputs are rejected by schema + groundedness
    from ..routers.ai_knowledge import validate_rag_output
    laundry = [cid for cid in chunks if cid.startswith("Laundry SOP")]
    retrieved = {cid: chunks[cid][2] for cid in laundry}
    for fake in D.FAKE_LIVE_OUTPUTS:
        out = _fill(fake, retrieved=laundry[0], foreign="Hand Hygiene SOP#0")
        cases += 1
        passed += not validate_rag_output(out, retrieved)
    # (c) scribe drafts with invented medication / non-verbatim text are rejected
    segs = S.segment_transcript("Doctor: Take rest and drink water.\nPatient: Fever since "
                                "2 days.")
    good = S.sectionise(segs, [])
    bad_med = {**good, "medications_discussed_verbatim": [
        {"text": "Tab amoxicillin 500 mg", "source_segments": [0], "confidence": "high",
         "mentions": ["amoxicillin"], "verify": True}]}
    bad_code = {**good, "icd10": "J06.9"}
    bad_dx = {**good, "assessment_stated_by_clinician": [
        {"text": "Fever since 2 days.", "source_segments": [1], "confidence": "high"}]}
    for draft in (bad_med, bad_code, bad_dx):
        cases += 1
        passed += not S.validate_draft(draft, segs)[0]
    return {"cases": cases, "resisted": passed}


def _fill(obj, **kw):
    if isinstance(obj, dict):
        return {k: _fill(v, **kw) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, **kw) for v in obj]
    if isinstance(obj, str) and obj.startswith("{") and obj.endswith("}"):
        return kw.get(obj[1:-1], obj)
    return obj


def eval_scribe(dataset=None) -> dict:
    dataset = dataset or D.SCRIBE_SET
    total = correct = 0
    per_set, confusion = {}, {}
    med_verbatim = med_total = 0
    for name, lines in dataset:
        segs = S.segment_transcript("\n".join(line for line, _ in lines))
        draft = S.sectionise(segs, ["Paracetamol", "Omeprazole", "Azithromycin",
                                    "Diclofenac", "Aceclofenac", "Amlodipine",
                                    "Cetirizine", "Nitrofurantoin"])
        assert S.validate_draft(draft, segs)[0]
        got: dict[int, str] = {}
        for section, st in S.all_statements(S.SoapDraft.model_validate(draft)):
            got[st.source_segments[0]] = section
        ok = 0
        for i, (_line, expected) in enumerate(lines):
            g = got.get(i, "missing")
            ok += g == expected
            if g != expected:
                confusion[f"{expected}→{g}"] = confusion.get(f"{expected}→{g}", 0) + 1
            if expected == "medications_discussed_verbatim":
                med_total += 1
                med_verbatim += g == expected
        per_set[name] = f"{ok}/{len(lines)}"
        total += len(lines)
        correct += ok
    return {"transcripts": len(dataset), "utterances": total,
            "sentence_section_accuracy": round(correct / total, 3), "per_transcript": per_set,
            "medication_recall": f"{med_verbatim}/{med_total}",
            "errors": dict(sorted(confusion.items(), key=lambda kv: -kv[1]))}


def run_all() -> dict:
    return {"opd": eval_opd(), "pharmacy_demand": eval_demand(), "beds": eval_beds(),
            "no_show": eval_noshow(), "rag": eval_rag(),
            "rag_heldout": eval_rag(qa=D.SOP_QA_HELDOUT), "injection": eval_injection(),
            "scribe": eval_scribe(), "scribe_heldout": eval_scribe(D.SCRIBE_HELDOUT)}


if __name__ == "__main__":  # pragma: no cover - CLI
    import json

    print(json.dumps(run_all(), ensure_ascii=False, indent=2))
