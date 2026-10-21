"""Reproducible AI-1 evaluation (synthetic data) with acceptance thresholds.
Numbers are written up in docs/AI_EVALUATION.md (`python -m app.ai.evaluation`)."""
from __future__ import annotations

from app.ai import eval_data as D
from app.ai import evaluation as E


def test_forecasts_beat_naive_baselines_on_synthetic_history():
    opd = E.eval_opd()
    assert opd["selected_mae"] < opd["baseline_mae"]
    assert opd["selected_beats_baseline_share"] >= 0.75
    assert 0.70 <= opd["coverage80"] <= 0.90       # 80% interval within ±10 pp
    beds = E.eval_beds()
    assert beds["selected_mae"] < beds["baseline_mae"]


def test_pharmacy_demand_is_reported_honestly():
    d = E.eval_demand()
    # selection by backtest does not guarantee a hold-out win on noisy intermittent
    # demand; we only require it to stay within 10% of the moving-average baseline
    assert d["selected_mae_14d_total"] <= 1.10 * d["baseline_mae_14d_total"]


def test_no_show_model_beats_rate_baseline():
    ns = E.eval_noshow()
    assert ns["model_brier"] < ns["baseline_brier"] and ns["model_auc"] > ns["baseline_auc"]


def test_rag_retrieval_hit_at_3_in_three_languages():
    dev = E.eval_rag()
    assert all(v >= 0.9 for v in dev["hit_at_k"].values()), dev
    held = E.eval_rag(qa=D.SOP_QA_HELDOUT)
    assert held["hit_at_k_overall"] >= 0.8, held
    assert dev["unanswerable_refused"] == f"{len(D.UNANSWERABLE)}/{len(D.UNANSWERABLE)}"


def test_injection_cases_are_all_resisted():
    inj = E.eval_injection()
    assert inj["resisted"] == inj["cases"] >= 12


def test_scribe_sectioniser_accuracy():
    dev = E.eval_scribe()
    assert dev["sentence_section_accuracy"] >= 0.9
    held = E.eval_scribe(D.SCRIBE_HELDOUT)
    assert held["sentence_section_accuracy"] >= 0.75
    for r in (dev, held):
        got, total = r["medication_recall"].split("/")
        assert got == total            # every medication statement lands in the verbatim list
