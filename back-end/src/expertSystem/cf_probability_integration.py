from __future__ import annotations

from typing import Any, Dict, List

from certainty_factors import Rule, build_evidence_from_model, build_evidence_from_intake, evaluate_rules
from expertSystem.clinical_risk import compute_clinical_risk

HAM_CODES = ["mel", "nv", "bcc", "akiec", "bkl", "df", "vasc"]

DISPLAY_NAME = {
    "mel": "melanoma",
    "nv": "melanocytic_nevus",
    "bcc": "basal_cell_carcinoma",
    "akiec": "actinic_keratosis",
    "bkl": "benign_keratosis",
    "df": "dermatofibroma",
    "vasc": "vascular_lesion",
}

LABEL_ALIASES = {
    "mel": "mel",
    "melanoma": "mel",
    "nv": "nv",
    "melanocytic_nevus": "nv",
    "melanocytic nevus": "nv",
    "bcc": "bcc",
    "basal_cell_carcinoma": "bcc",
    "basal cell carcinoma": "bcc",
    "akiec": "akiec",
    "actinic_keratosis": "akiec",
    "actinic keratosis": "akiec",
    "bkl": "bkl",
    "benign_keratosis": "bkl",
    "benign keratosis": "bkl",
    "df": "df",
    "dermatofibroma": "df",
    "vasc": "vasc",
    "vascular_lesion": "vasc",
    "vascular lesion": "vasc",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _to_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"true", "1", "yes", "y", "on", "checked"}:
        return True
    if s in {"false", "0", "no", "n", "off", "unchecked"}:
        return False
    return None


def _to_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:
        return None


def _to_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except Exception:
        return None
    if not f.is_integer():
        return None
    return int(f)


def _normalize_model_probs(model_topk: Any) -> Dict[str, float]:
    probs: Dict[str, float] = {k: 0.0 for k in HAM_CODES}

    if isinstance(model_topk, dict):
        for raw_label, raw_prob in model_topk.items():
            code = LABEL_ALIASES.get(str(raw_label).strip().lower())
            if not code:
                continue
            try:
                probs[code] = max(0.0, float(raw_prob))
            except Exception:
                continue
    elif isinstance(model_topk, list):
        for item in model_topk:
            if not isinstance(item, dict):
                continue
            code = LABEL_ALIASES.get(str(item.get("label") or item.get("class") or "").strip().lower())
            if not code:
                continue
            try:
                probs[code] = max(0.0, float(item.get("prob", item.get("confidence", 0.0))))
            except Exception:
                continue

    total = sum(probs.values())
    if total <= 0:
        uniform = 1.0 / len(HAM_CODES)
        return {k: uniform for k in HAM_CODES}
    return {k: v / total for k, v in probs.items()}


def _build_symptom_evidence(patient_inputs: Dict[str, Any]) -> Dict[str, float]:
    width_mm = _to_float(patient_inputs.get("width_mm", patient_inputs.get("diameter_mm")))
    border_0_10 = _to_float(patient_inputs.get("border_irregularity", patient_inputs.get("border_0_10")))
    num_colors = _to_int(patient_inputs.get("num_colors", patient_inputs.get("number_of_colors")))
    elevation = str(patient_inputs.get("elevation") or "").strip().lower()
    itching_0_10 = _to_float(patient_inputs.get("itching", patient_inputs.get("itching_0_10")))
    pain_0_10 = _to_float(patient_inputs.get("pain", patient_inputs.get("pain_0_10")))

    evidence: Dict[str, float] = {}

    if width_mm is not None:
        if width_mm >= 6:
            evidence["diameter_large"] = _clamp((width_mm - 6.0) / 10.0 + 0.45, 0.0, 1.0)
        else:
            evidence["diameter_large"] = -0.2

    if border_0_10 is not None:
        b = _clamp(border_0_10, 0.0, 10.0)
        evidence["border_irregular"] = _clamp((b - 3.0) / 7.0, -1.0, 1.0)

    if num_colors is not None:
        n = max(1, num_colors)
        if n >= 3:
            evidence["multi_color"] = 0.85
            evidence["single_color"] = -0.4
        elif n == 2:
            evidence["multi_color"] = 0.35
            evidence["single_color"] = -0.1
        else:
            evidence["single_color"] = 0.6
            evidence["multi_color"] = -0.2

    if elevation:
        if any(t in elevation for t in ["nodular", "nodule", "lump"]):
            evidence["nodular"] = 0.8
        elif any(t in elevation for t in ["raised", "elevated", "bump"]):
            evidence["raised"] = 0.6
        elif "flat" in elevation:
            evidence["flat"] = 0.6

    if itching_0_10 is not None:
        itch = _clamp(itching_0_10, 0.0, 10.0)
        evidence["itching_high"] = _clamp((itch - 4.0) / 6.0, -1.0, 1.0)

    if pain_0_10 is not None:
        pain = _clamp(pain_0_10, 0.0, 10.0)
        evidence["pain_high"] = _clamp((pain - 4.0) / 6.0, -1.0, 1.0)

    return evidence


def _disease_cf_rules() -> List[Rule]:
    return [
        Rule("CF_MEL_IMG", ["img_mel"], "AND", 0.85, "cf_mel", "Model supports melanoma", "melanoma"),
        Rule("CF_MEL_ABCDE_1", ["diameter_large", "border_irregular"], "AND", 0.78, "cf_mel", "ABCDE size+border", "melanoma"),
        Rule("CF_MEL_ABCDE_2", ["multi_color", "rapid_change"], "AND", 0.82, "cf_mel", "Color/evolution concern", "melanoma"),
        Rule("CF_MEL_BLEED", ["bleeding"], "AND", 0.74, "cf_mel", "Bleeding supports melanoma concern", "melanoma"),

        Rule("CF_NV_IMG", ["img_nv"], "AND", 0.80, "cf_nv", "Model supports nevus", "nevus"),
        Rule("CF_NV_SIMPLE", ["single_color", "flat"], "AND", 0.65, "cf_nv", "Simple flat single-color lesion", "nevus"),
        Rule("CF_NV_NONBLEED", ["bleeding"], "AND", 0.30, "cf_nv", "Bleeding weakly opposes nevus", "nevus"),

        Rule("CF_BCC_IMG", ["img_bcc"], "AND", 0.82, "cf_bcc", "Model supports BCC", "bcc"),
        Rule("CF_BCC_NODE", ["nodular", "bleeding"], "AND", 0.76, "cf_bcc", "Nodular + bleeding pattern", "bcc"),
        Rule("CF_BCC_PAIN", ["pain_high"], "AND", 0.55, "cf_bcc", "Pain contributes to BCC concern", "bcc"),

        Rule("CF_AKIEC_IMG", ["img_akiec"], "AND", 0.78, "cf_akiec", "Model supports AKIEC", "akiec"),
        Rule("CF_AKIEC_IRR", ["border_irregular", "pain_high"], "AND", 0.62, "cf_akiec", "Irritation/irregularity pattern", "akiec"),

        Rule("CF_BKL_IMG", ["img_bkl"], "AND", 0.80, "cf_bkl", "Model supports BKL", "bkl"),
        Rule("CF_BKL_ITCH", ["itching_high", "raised"], "AND", 0.58, "cf_bkl", "Itchy raised lesion pattern", "bkl"),

        Rule("CF_DF_IMG", ["img_df"], "AND", 0.82, "cf_df", "Model supports dermatofibroma", "df"),
        Rule("CF_DF_NODE", ["nodular", "single_color"], "AND", 0.66, "cf_df", "Firm nodular single-color pattern", "df"),

        Rule("CF_VASC_IMG", ["img_vasc"], "AND", 0.83, "cf_vasc", "Model supports vascular lesion", "vasc"),
        Rule("CF_VASC_BLEED", ["bleeding"], "AND", 0.64, "cf_vasc", "Bleeding contributes to vascular lesion", "vasc"),
    ]


def _cf_to_probability(cf_scores: Dict[str, float]) -> Dict[str, float]:
    # Convert each CF in [-1,1] to [0,1], then normalize.
    base = {code: _clamp((float(cf_scores.get(code, 0.0)) + 1.0) / 2.0, 0.0, 1.0) for code in HAM_CODES}
    total = sum(base.values())
    if total <= 0:
        uniform = 1.0 / len(HAM_CODES)
        return {k: uniform for k in HAM_CODES}
    return {k: base[k] / total for k in HAM_CODES}


def _clinical_scalar_to_distribution(clinical_prob: float) -> Dict[str, float]:
    """
    Convert overall clinical malignancy probability into class prior distribution.
    More malignant mass goes to mel/bcc/akiec; residual to lower-risk classes.
    """
    malignancy = _clamp(float(clinical_prob or 0.0), 0.01, 0.99)
    benign = 1.0 - malignancy

    dist = {
        "mel": malignancy * 0.50,
        "bcc": malignancy * 0.30,
        "akiec": malignancy * 0.20,
        "nv": benign * 0.45,
        "bkl": benign * 0.22,
        "df": benign * 0.17,
        "vasc": benign * 0.16,
    }
    total = sum(dist.values()) or 1.0
    return {k: dist[k] / total for k in HAM_CODES}


def _weighted_fuse_probabilities(model_probs: Dict[str, float], expert_probs: Dict[str, float]) -> Dict[str, Any]:
    """
    Weighted fusion:
      final = alpha * model + (1-alpha) * expert
    with alpha adapted by model confidence.
    """
    model_conf = max(float(model_probs.get(code, 0.0) or 0.0) for code in HAM_CODES)
    if model_conf >= 0.80:
        alpha = 0.85
    elif model_conf >= 0.60:
        alpha = 0.75
    elif model_conf >= 0.40:
        alpha = 0.65
    else:
        alpha = 0.55

    fused = {}
    for code in HAM_CODES:
        mp = float(model_probs.get(code, 0.0) or 0.0)
        ep = float(expert_probs.get(code, 0.0) or 0.0)
        fused[code] = alpha * mp + (1.0 - alpha) * ep

    total = sum(fused.values()) or 1.0
    fused = {k: fused[k] / total for k in HAM_CODES}
    return {"alpha": round(alpha, 3), "model_confidence": round(model_conf, 4), "distribution": fused}


def _format_distribution(dist: Dict[str, float]) -> Dict[str, float]:
    return {DISPLAY_NAME[k]: round(v, 6) for k, v in dist.items()}


def _format_distribution_percent(dist: Dict[str, float]) -> Dict[str, float]:
    return {DISPLAY_NAME[k]: round(float(v) * 100.0, 2) for k, v in dist.items()}


def _derive_next_step(top_code: str, top_prob: float) -> str:
    high_concern = {"mel", "bcc", "akiec"}
    if top_code in high_concern and top_prob >= 0.60:
        return "Urgent dermatology evaluation recommended (ideally within 24–48 hours)."
    if top_code in high_concern or top_prob >= 0.40:
        return "Schedule a dermatology appointment soon for in-person assessment."
    return "Monitor and arrange routine dermatology follow-up if lesion changes."


def run_cf_disease_fusion(patient_inputs: Dict[str, Any], model_topk: Any) -> Dict[str, Any]:
    """
    Integrates certainty_factors.py into disease-probability estimation.

    Returns:
      - patient_inputs
      - model_probabilities
      - certainty_factor_probabilities
      - final_combined_probabilities
      - most_likely_disease
      - explanation_of_reasoning
      - recommended_next_step
    """
    normalized_model = _normalize_model_probs(model_topk)

    cf_intake_evidence = build_evidence_from_intake(
        {
            "rapid_change": patient_inputs.get("rapid_change"),
            "bleeding": patient_inputs.get("bleeding"),
            "itching": _to_bool(patient_inputs.get("itching")),
            "pain": _to_bool(patient_inputs.get("pain")),
        }
    )
    cf_symptom_evidence = _build_symptom_evidence(patient_inputs)
    model_evidence = build_evidence_from_model(
        [{"label": code, "prob": prob} for code, prob in normalized_model.items()],
        neutral_prob=1.0 / 7.0,
        include_negative=False,
    )

    evidence = {**model_evidence, **cf_intake_evidence, **cf_symptom_evidence}
    final_facts, trace = evaluate_rules(evidence, _disease_cf_rules(), include_skipped=False)

    disease_cfs = {
        "mel": float(final_facts.get("cf_mel", 0.0) or 0.0),
        "nv": float(final_facts.get("cf_nv", 0.0) or 0.0),
        "bcc": float(final_facts.get("cf_bcc", 0.0) or 0.0),
        "akiec": float(final_facts.get("cf_akiec", 0.0) or 0.0),
        "bkl": float(final_facts.get("cf_bkl", 0.0) or 0.0),
        "df": float(final_facts.get("cf_df", 0.0) or 0.0),
        "vasc": float(final_facts.get("cf_vasc", 0.0) or 0.0),
    }

    cf_probs = _cf_to_probability(disease_cfs)

    clinical_risk = compute_clinical_risk(
        {
            "bleeding": patient_inputs.get("bleeding"),
            "rapid_change": patient_inputs.get("rapid_change"),
            "width_mm": patient_inputs.get("width_mm", patient_inputs.get("diameter_mm")),
            "border_0_10": patient_inputs.get("border_irregularity", patient_inputs.get("border_0_10")),
            "num_colors": patient_inputs.get("num_colors", patient_inputs.get("number_of_colors")),
            "elevation": patient_inputs.get("elevation"),
            "itching_0_10": patient_inputs.get("itching", patient_inputs.get("itching_0_10")),
            "pain_0_10": patient_inputs.get("pain", patient_inputs.get("pain_0_10")),
        }
    )
    clinical_prob = float(clinical_risk.get("probability", 0.0) or 0.0)
    clinical_dist = _clinical_scalar_to_distribution(clinical_prob)

    expert_probs = {}
    for code in HAM_CODES:
        expert_probs[code] = 0.7 * float(cf_probs.get(code, 0.0) or 0.0) + 0.3 * float(clinical_dist.get(code, 0.0) or 0.0)
    s_expert = sum(expert_probs.values()) or 1.0
    expert_probs = {k: expert_probs[k] / s_expert for k in HAM_CODES}

    fusion = _weighted_fuse_probabilities(normalized_model, expert_probs)
    fused_probs = fusion["distribution"]

    top_code = max(fused_probs, key=fused_probs.get)
    top_prob = float(fused_probs[top_code])

    top3_codes = sorted(HAM_CODES, key=lambda code: fused_probs[code], reverse=True)[:3]
    top3 = [
        {
            "code": code,
            "label": DISPLAY_NAME[code],
            "final_percent": round(fused_probs[code] * 100.0, 2),
        }
        for code in top3_codes
    ]

    reasoning_applied = [
        {
            "rule_id": step.get("rule_id"),
            "conclusion": step.get("conclusion"),
            "contrib_cf": round(float(step.get("contrib_cf", 0.0) or 0.0), 4),
            "description": step.get("description", ""),
        }
        for step in trace
        if step.get("status") == "applied" and abs(float(step.get("contrib_cf", 0.0) or 0.0)) > 1e-9
    ]

    structured_inputs = {
            "bleeding": _to_bool(patient_inputs.get("bleeding")),
            "itching": _to_float(patient_inputs.get("itching", patient_inputs.get("itching_0_10"))),
            "pain": _to_float(patient_inputs.get("pain", patient_inputs.get("pain_0_10"))),
            "lesion_width_mm": _to_float(patient_inputs.get("width_mm", patient_inputs.get("diameter_mm"))),
            "border_irregularity_0_10": _to_float(patient_inputs.get("border_irregularity", patient_inputs.get("border_0_10"))),
            "number_of_colors": _to_int(patient_inputs.get("num_colors", patient_inputs.get("number_of_colors"))),
            "elevation": str(patient_inputs.get("elevation") or "").strip().lower() or None,
            "rapid_change": _to_bool(patient_inputs.get("rapid_change")),
    }

    reasoning_list = [
        f"Clinical points {int(clinical_risk.get('points', 0) or 0)} mapped to {float(clinical_risk.get('probability_percent', 0.0) or 0.0):.1f}% clinical probability.",
        "Certainty-factor rules produced per-class CF scores and normalized expert probabilities.",
        f"Adaptive weighted fusion used alpha={float(fusion.get('alpha', 0.0) or 0.0):.2f} based on model confidence {float(fusion.get('model_confidence', 0.0) or 0.0):.2f}.",
    ]

    top_disease_breakdown = {
        "label": DISPLAY_NAME[top_code],
        "model_percent": round(normalized_model[top_code] * 100.0, 2),
        "expert_percent": round(expert_probs[top_code] * 100.0, 2),
        "final_percent": round(fused_probs[top_code] * 100.0, 2),
    }

    payload = {
        "inputs": structured_inputs,
        "model_probs": _format_distribution_percent(normalized_model),
        "expert_probs": _format_distribution_percent(expert_probs),
        "final_probs": _format_distribution_percent(fused_probs),
        "top3": top3,
        "reasoning": reasoning_list,
        "top_disease_breakdown": top_disease_breakdown,

        # Backward-compatible keys
        "patient_inputs": structured_inputs,
        "model_probabilities": _format_distribution(normalized_model),
        "certainty_factor_scores": {DISPLAY_NAME[k]: round(v, 4) for k, v in disease_cfs.items()},
        "certainty_factor_probabilities": _format_distribution(expert_probs),
        "final_combined_probabilities": _format_distribution(fused_probs),
        "most_likely_disease": {
            "code": top_code,
            "label": DISPLAY_NAME[top_code],
            "probability": round(top_prob, 6),
            "probability_percent": round(top_prob * 100.0, 2),
        },
        "explanation_of_reasoning": {
            "method": "certainty_factors.py evidence + rule evaluation, then CF-to-probability normalization and fusion with CNN probabilities",
            "evidence": {k: round(float(v), 4) for k, v in evidence.items()},
            "applied_rules": reasoning_applied,
            "clinical_probability_percent": clinical_risk.get("probability_percent"),
            "fusion_alpha": fusion.get("alpha"),
        },
        "recommended_next_step": _derive_next_step(top_code, top_prob),
    }

    return payload
