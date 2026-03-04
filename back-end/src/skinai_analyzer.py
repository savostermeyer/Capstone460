"""
SkinAI Analyzer: High-level interface for skin lesion analysis using MYCIN-style CF reasoning.

Integrates model predictions and clinical intake data to provide risk assessment
and clinician review recommendations.
"""

from certainty_factors import (
    Rule,
    combine_cf,
    build_evidence_from_model,
    build_evidence_from_intake,
    get_skinai_rules,
    evaluate_rules,
)


def _canonical_risk_level(triage: str) -> str:
    t = (triage or "").lower()
    if t in {"high_risk", "clinician_review"}:
        return "high"
    if t == "moderate_risk":
        return "moderate"
    return "low"


def _triage_from_facts(final_facts: dict) -> str:
    needs_review_cf = float(final_facts.get("needs_clinician_review", 0.0) or 0.0)
    high_risk_cf = float(final_facts.get("high_risk_flag", 0.0) or 0.0)
    moderate_risk_cf = float(final_facts.get("moderate_risk_flag", 0.0) or 0.0)
    low_risk_cf = float(final_facts.get("low_risk_flag", 0.0) or 0.0)

    if needs_review_cf > 0.5:
        return "clinician_review"
    if high_risk_cf > max(moderate_risk_cf, low_risk_cf):
        return "high_risk"
    if moderate_risk_cf > low_risk_cf:
        return "moderate_risk"
    return "low_risk"


def _derive_triggered_facts(final_facts: dict, trace: list[dict]) -> list[dict]:
    triggered = []
    seen = set()
    for entry in trace:
        if entry.get("status") != "applied":
            continue
        for premise in entry.get("premises", []):
            cf = float(final_facts.get(premise, 0.0) or 0.0)
            if abs(cf) < 1e-9:
                continue
            if premise in seen:
                continue
            seen.add(premise)
            triggered.append(
                {
                    "fact": premise,
                    "cf": round(cf, 4),
                    "direction": "support" if cf >= 0 else "oppose",
                }
            )
    return triggered


def fuse_predictions(
    model_probs: list[dict],
    intake_facts: dict,
    rules: list[Rule],
) -> dict:
    """
    Deterministically fuse model probabilities, intake evidence, and CF rules.

    Args:
        model_probs: List of {label, prob} from the CNN.
        intake_facts: Intake fields/symptoms from form/chat.
        rules: Rule set used for CF reasoning.

    Returns:
        Dict with ranked diseases, triage, triggered rules/facts, risk level, and
        review flag plus full reasoning internals for auditing.
    """
    model_evidence = build_evidence_from_model(model_probs)
    intake_evidence = build_evidence_from_intake(intake_facts)
    evidence = {**model_evidence, **intake_evidence}

    final_facts, trace = evaluate_rules(evidence, rules, include_skipped=False)

    ranked_diseases = []
    for item in model_probs or []:
        label = str(item.get("label", "")).strip()
        if not label:
            continue

        prob = float(item.get("prob", 0.0) or 0.0)
        img_cf = float(final_facts.get(f"img_{label}", 0.0) or 0.0)

        if label == "mel":
            risk_cf = float(final_facts.get("high_risk_flag", 0.0) or 0.0)
        elif label in {"bcc", "akiec"}:
            risk_cf = float(final_facts.get("moderate_risk_flag", 0.0) or 0.0)
        else:
            low_cf = float(final_facts.get("low_risk_flag", 0.0) or 0.0)
            risk_cf = -abs(low_cf)

        fused_cf = combine_cf([img_cf, 0.5 * risk_cf])
        fused_score = max(0.0, min(1.0, (fused_cf + 1.0) / 2.0))
        confidence = max(0.0, min(1.0, 0.65 * prob + 0.35 * fused_score))

        ranked_diseases.append(
            {
                "label": label,
                "model_prob": round(prob, 4),
                "fused_cf": round(fused_cf, 4),
                "confidence": round(confidence, 4),
            }
        )

    ranked_diseases.sort(key=lambda x: (-x["confidence"], x["label"]))

    triage = _triage_from_facts(final_facts)
    risk_level = _canonical_risk_level(triage)
    review_flag = triage in {"clinician_review", "high_risk"}

    triggered_rules = []
    for entry in trace:
        contrib = float(entry.get("contrib_cf", 0.0) or 0.0)
        if abs(contrib) < 1e-9:
            continue
        triggered_rules.append(
            {
                "rule_id": entry.get("rule_id"),
                "conclusion": entry.get("conclusion"),
                "contrib_cf": round(contrib, 4),
                "premise_cf": round(float(entry.get("premise_cf", 0.0) or 0.0), 4),
                "description": entry.get("description", ""),
                "domain": entry.get("domain", "general"),
            }
        )

    return {
        "ranked_diseases": ranked_diseases,
        "triage": triage,
        "risk_level": risk_level,
        "review_flag": review_flag,
        "triggered_rules": triggered_rules,
        "triggered_facts": _derive_triggered_facts(final_facts, trace),
        "evidence": evidence,
        "facts": final_facts,
        "trace": trace,
    }


def analyze_skin_lesion(topk: list[dict], intake: dict) -> dict:
    """
    Analyze a skin lesion using model predictions and clinical intake.
    
    Combines image classification results with clinical history to determine
    risk level and whether clinician review is needed.
    
    Args:
        topk: List of model predictions, e.g.,
              [{"label": "mel", "prob": 0.62}, {"label": "nv", "prob": 0.27}]
        intake: Dict of user intake responses, e.g.,
                {"rapid_change": True, "bleeding": False, "itching": True, "pain": False}
    
    Returns:
        Dict with:
        - primary_result: "clinician_review", "high_risk", "moderate_risk", or "low_risk"
        - facts: Dict of all derived certainty factors
        - trace: List of rule evaluation steps
    """
    fused = fuse_predictions(topk, intake, get_skinai_rules())

    return {
        "primary_result": fused["triage"],
        "facts": fused["facts"],
        "trace": fused["trace"],
        "ranked_diseases": fused["ranked_diseases"],
        "triage": fused["triage"],
        "risk_level": fused["risk_level"],
        "review_flag": fused["review_flag"],
        "triggered_rules": fused["triggered_rules"],
        "triggered_facts": fused["triggered_facts"],
    }


def _print_result(result: dict) -> None:
    """Pretty-print analysis result."""
    print("\n" + "=" * 70)
    print("ANALYSIS RESULT")
    print("=" * 70)
    
    primary = result["primary_result"]
    print(f"\nPrimary Result: {primary.upper()}")
    
    # Print key facts
    print("\nKey Clinical Indicators:")
    key_facts = [
        "needs_clinician_review",
        "high_risk_flag",
        "moderate_risk_flag",
        "low_risk_flag",
    ]
    for fact in key_facts:
        cf = result["facts"].get(fact, 0.0)
        if cf > 0.0:
            status = "✓ TRIGGERED" if cf > 0.5 else ""
            print(f"  {fact}: {cf:.4f} {status}")
    
    # Print evidence summary
    print("\nEvidence Summary:")
    img_facts = {k: v for k, v in result["facts"].items() if k.startswith("img_")}
    symptom_facts = {k: v for k, v in result["facts"].items() if k in [
        "rapid_change", "bleeding", "itching", "pain"
    ]}
    
    if img_facts:
        print("  Model Predictions:")
        for fact, cf in sorted(img_facts.items()):
            print(f"    {fact}: {cf:.4f}")
    
    if symptom_facts:
        print("  Clinical Symptoms:")
        for fact, cf in sorted(symptom_facts.items()):
            if cf > 0.0:
                print(f"    {fact}: {cf:.4f}")
    
    # Print trace
    print("\nReasoning Trace:")
    for i, entry in enumerate(result["trace"], 1):
        print(f"\n  Step {i}: {entry['rule_id']}")
        print(f"    IF {entry['operator']}({', '.join(entry['premises'])})")
        print(f"      → {entry['conclusion']}")
        print(f"    Premise CF: {entry['premise_cf']:.4f} × Rule CF: {entry['rule_cf']:.2f} = {entry['contrib_cf']:.4f}")
        if entry['previous_conclusion_cf'] is not None:
            print(f"    Combined: {entry['previous_conclusion_cf']:.4f} + {entry['contrib_cf']:.4f} = {entry['new_conclusion_cf']:.4f}")
        else:
            print(f"    New: {entry['new_conclusion_cf']:.4f}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Demo with mock data (same as certainty_factors.py --skinai)
    print("=" * 70)
    print("SkinAI Analyzer Demo")
    print("=" * 70)
    
    model_output = [
        {"label": "mel", "prob": 0.62},
        {"label": "nv", "prob": 0.27},
        {"label": "bkl", "prob": 0.11},
    ]
    
    intake_data = {
        "rapid_change": True,
        "bleeding": False,
        "itching": True,
        "pain": False,
    }
    
    print("\nInput Data:")
    print("\n  Model Predictions:")
    for item in model_output:
        print(f"    {item['label']}: {item['prob']:.2f}")
    
    print("\n  User Intake:")
    for key, value in intake_data.items():
        print(f"    {key}: {value}")
    
    # Run analysis
    result = analyze_skin_lesion(model_output, intake_data)
    _print_result(result)
