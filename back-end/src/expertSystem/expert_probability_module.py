from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Any, Dict, List, Tuple


# HAM10000 class keys used in the current backend model
HAM10000_CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]

# Accept both short keys and full disease names
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

# Human-friendly names for output
CLASS_DISPLAY = {
    "mel": "melanoma",
    "nv": "melanocytic nevus",
    "bcc": "basal cell carcinoma",
    "akiec": "actinic keratosis",
    "bkl": "benign keratosis",
    "df": "dermatofibroma",
    "vasc": "vascular lesion",
}


@dataclass
class ExpertConfig:
    softmax_temperature: float = 1.0
    model_weight: float = 0.70
    expert_weight: float = 0.55
    epsilon: float = 1e-9


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    t = str(value).strip().lower()
    if t in {"true", "1", "yes", "y", "on"}:
        return True
    if t in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if not v.is_integer():
        return None
    return int(v)


def _normalize_elevation(value: Any) -> str | None:
    if value is None:
        return None
    t = str(value).strip().lower()
    if any(token in t for token in ["nodular", "nodule", "lump"]):
        return "nodular"
    if any(token in t for token in ["raised", "elevated", "bump"]):
        return "raised"
    if "flat" in t:
        return "flat"
    return None


def _canonical_label(label: str) -> str | None:
    t = str(label or "").strip().lower()
    return LABEL_ALIASES.get(t)


def _softmax(scores: Dict[str, float], temperature: float = 1.0) -> Dict[str, float]:
    temp = max(1e-6, float(temperature))
    max_score = max(scores.values()) if scores else 0.0
    exp_vals = {k: exp((v - max_score) / temp) for k, v in scores.items()}
    total = sum(exp_vals.values()) or 1.0
    return {k: exp_vals[k] / total for k in scores}


def _normalize_distribution(dist: Dict[str, float]) -> Dict[str, float]:
    clean = {c: max(0.0, float(dist.get(c, 0.0) or 0.0)) for c in HAM10000_CLASSES}
    total = sum(clean.values())
    if total <= 0:
        return {c: 1.0 / len(HAM10000_CLASSES) for c in HAM10000_CLASSES}
    return {c: clean[c] / total for c in HAM10000_CLASSES}


def _coerce_model_probabilities(model_probs: Any) -> Dict[str, float]:
    if isinstance(model_probs, list):
        merged: Dict[str, float] = {}
        for item in model_probs:
            if not isinstance(item, dict):
                continue
            key = _canonical_label(str(item.get("label") or item.get("class") or ""))
            if not key:
                continue
            value = item.get("prob", item.get("confidence", item.get("score", 0.0)))
            try:
                merged[key] = float(value)
            except Exception:
                continue
        return _normalize_distribution(merged)

    if isinstance(model_probs, dict):
        merged = {}
        for raw_key, raw_value in model_probs.items():
            key = _canonical_label(str(raw_key))
            if not key:
                continue
            try:
                merged[key] = float(raw_value)
            except Exception:
                continue
        return _normalize_distribution(merged)

    return {c: 1.0 / len(HAM10000_CLASSES) for c in HAM10000_CLASSES}


def _init_scores() -> Dict[str, float]:
    # Prior logits; melanoma starts slightly elevated because the chatbot asks concerning-lesion questions.
    return {
        "mel": 0.10,
        "nv": 0.05,
        "bcc": 0.02,
        "akiec": 0.01,
        "bkl": 0.01,
        "df": 0.00,
        "vasc": 0.00,
    }


def _add(contrib: Dict[str, float], disease: str, value: float, reason: str, reasons: Dict[str, List[str]]) -> None:
    contrib[disease] = contrib.get(disease, 0.0) + value
    reasons.setdefault(disease, []).append(f"{reason} ({value:+.2f})")


def expert_rule_logits(symptoms: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
    """
    Build disease logits using explicit rule-based clinical heuristics.
    Inputs expected:
      bleeding, rapid_change, width_mm, border_0_10, num_colors,
      elevation, itching_0_10, pain_0_10
    """
    logits = _init_scores()
    reasons: Dict[str, List[str]] = {c: [] for c in HAM10000_CLASSES}

    bleeding = _to_bool(symptoms.get("bleeding"))
    rapid_change = _to_bool(symptoms.get("rapid_change"))
    width_mm = _to_float(symptoms.get("width_mm", symptoms.get("diameter_mm")))
    border_0_10 = _to_float(symptoms.get("border_0_10", symptoms.get("border_irregularity")))
    num_colors = _to_int(symptoms.get("num_colors", symptoms.get("number_of_colors")))
    elevation = _normalize_elevation(symptoms.get("elevation"))
    itching_0_10 = _to_float(symptoms.get("itching_0_10", symptoms.get("itching")))
    pain_0_10 = _to_float(symptoms.get("pain_0_10", symptoms.get("pain")))

    if bleeding is True:
        _add(logits, "mel", 1.05, "Bleeding present", reasons)
        _add(logits, "bcc", 0.85, "Bleeding present", reasons)
        _add(logits, "vasc", 0.55, "Bleeding present", reasons)
        _add(logits, "nv", -0.45, "Bleeding less typical", reasons)

    if rapid_change is True:
        _add(logits, "mel", 0.95, "Rapid change", reasons)
        _add(logits, "akiec", 0.45, "Rapid change", reasons)
        _add(logits, "bcc", 0.35, "Rapid change", reasons)
        _add(logits, "nv", -0.35, "Rapid change less typical", reasons)

    if width_mm is not None:
        w = max(0.0, width_mm)
        if w >= 10:
            _add(logits, "mel", 0.90, "Large diameter (>=10 mm)", reasons)
            _add(logits, "bcc", 0.45, "Large diameter (>=10 mm)", reasons)
            _add(logits, "nv", -0.25, "Large diameter less typical", reasons)
        elif w >= 6:
            _add(logits, "mel", 0.60, "Diameter >=6 mm (ABCDE)", reasons)
            _add(logits, "bkl", 0.20, "Moderate diameter", reasons)
        else:
            _add(logits, "nv", 0.25, "Smaller diameter", reasons)
            _add(logits, "df", 0.20, "Smaller diameter", reasons)

    if border_0_10 is not None:
        b = _clamp(border_0_10, 0.0, 10.0)
        if b >= 7:
            _add(logits, "mel", 0.95, "Irregular border", reasons)
            _add(logits, "bcc", 0.35, "Irregular border", reasons)
        elif b <= 3:
            _add(logits, "nv", 0.35, "Regular border", reasons)
            _add(logits, "df", 0.25, "Regular border", reasons)

    if num_colors is not None:
        n = max(1, num_colors)
        if n >= 3:
            _add(logits, "mel", 1.00, "Multiple colors (>=3)", reasons)
            _add(logits, "bkl", 0.40, "Multiple colors", reasons)
        elif n == 2:
            _add(logits, "mel", 0.35, "Two colors", reasons)
            _add(logits, "bkl", 0.30, "Two colors", reasons)
        else:
            _add(logits, "nv", 0.45, "Single color", reasons)
            _add(logits, "df", 0.20, "Single color", reasons)

    if elevation == "nodular":
        _add(logits, "bcc", 0.80, "Nodular elevation", reasons)
        _add(logits, "df", 0.55, "Nodular elevation", reasons)
        _add(logits, "mel", 0.30, "Nodular elevation", reasons)
    elif elevation == "raised":
        _add(logits, "bcc", 0.40, "Raised lesion", reasons)
        _add(logits, "bkl", 0.40, "Raised lesion", reasons)
        _add(logits, "df", 0.30, "Raised lesion", reasons)
    elif elevation == "flat":
        _add(logits, "nv", 0.25, "Flat lesion", reasons)
        _add(logits, "akiec", 0.20, "Flat lesion", reasons)

    if itching_0_10 is not None:
        itch = _clamp(itching_0_10, 0.0, 10.0)
        if itch >= 7:
            _add(logits, "bkl", 0.40, "High itching", reasons)
            _add(logits, "akiec", 0.35, "High itching", reasons)
            _add(logits, "bcc", 0.20, "High itching", reasons)
        elif itch <= 2:
            _add(logits, "nv", 0.12, "Low itching", reasons)

    if pain_0_10 is not None:
        pain = _clamp(pain_0_10, 0.0, 10.0)
        if pain >= 7:
            _add(logits, "bcc", 0.55, "High pain", reasons)
            _add(logits, "akiec", 0.35, "High pain", reasons)
            _add(logits, "mel", 0.30, "High pain", reasons)
        elif pain <= 2:
            _add(logits, "nv", 0.10, "Low pain", reasons)

    # Cleanup empty reasons for cleaner payload
    reasons = {k: v for k, v in reasons.items() if v}
    return logits, reasons


def compute_expert_probabilities(symptoms: Dict[str, Any], temperature: float = 1.0) -> Dict[str, Any]:
    logits, reasons = expert_rule_logits(symptoms)
    probs = _softmax(logits, temperature=temperature)
    return {
        "logits": {k: round(v, 6) for k, v in logits.items()},
        "probabilities": {k: round(v, 6) for k, v in probs.items()},
        "reasons_by_disease": reasons,
    }


def combine_probabilities(
    model_probabilities: Dict[str, float],
    expert_probabilities: Dict[str, float],
    cfg: ExpertConfig | None = None,
) -> Dict[str, float]:
    """
    Product-of-experts fusion:
      combined ~ model^model_weight * expert^expert_weight
    Then normalized to sum=1.
    """
    config = cfg or ExpertConfig()
    eps = config.epsilon

    combined_raw: Dict[str, float] = {}
    for cls in HAM10000_CLASSES:
        m = max(eps, float(model_probabilities.get(cls, 0.0) or 0.0))
        e = max(eps, float(expert_probabilities.get(cls, 0.0) or 0.0))
        combined_raw[cls] = (m ** config.model_weight) * (e ** config.expert_weight)

    return _normalize_distribution(combined_raw)


def _top_reasoning_text(reasons_by_disease: Dict[str, List[str]], top_class: str, max_items: int = 4) -> str:
    reasons = reasons_by_disease.get(top_class, [])
    if not reasons:
        return "No strong rule-based symptom evidence was triggered for the top class."
    return "; ".join(reasons[:max_items])


def build_expert_fusion_output(
    symptoms: Dict[str, Any],
    model_probs: Any,
    cfg: ExpertConfig | None = None,
) -> Dict[str, Any]:
    """
    Main integration entrypoint for Flask backend.

    Args:
      symptoms: chatbot/intake symptoms dict
      model_probs: list or dict from CNN output
      cfg: fusion/softmax configuration

    Returns payload with:
      - model probabilities
      - expert probabilities
      - final combined probabilities
      - most likely disease
      - medical reasoning explanation
    """
    config = cfg or ExpertConfig()
    model_distribution = _coerce_model_probabilities(model_probs)

    expert_out = compute_expert_probabilities(symptoms, temperature=config.softmax_temperature)
    expert_distribution = _normalize_distribution(expert_out["probabilities"])

    final_distribution = combine_probabilities(model_distribution, expert_distribution, cfg=config)

    best_class = max(final_distribution, key=final_distribution.get)

    explanation = {
        "method": "Rule-based symptom scoring -> softmax expert probabilities -> product-of-experts fusion with CNN probabilities",
        "top_class_reasons": _top_reasoning_text(expert_out["reasons_by_disease"], best_class),
        "notes": (
            "This is a triage-oriented probability estimate for educational/research use, "
            "not a diagnosis. Clinical examination and dermoscopy are required for diagnosis."
        ),
    }

    return {
        "model_probabilities": {k: round(v, 6) for k, v in model_distribution.items()},
        "expert_probabilities": {k: round(v, 6) for k, v in expert_distribution.items()},
        "final_combined_probabilities": {k: round(v, 6) for k, v in final_distribution.items()},
        "most_likely_disease": {
            "code": best_class,
            "name": CLASS_DISPLAY.get(best_class, best_class),
            "probability": round(final_distribution[best_class], 6),
        },
        "medical_reasoning": explanation,
        "reasoning_by_disease": expert_out["reasons_by_disease"],
    }


if __name__ == "__main__":
    # Example usage
    example_symptoms = {
        "bleeding": True,
        "rapid_change": True,
        "width_mm": 8,
        "border_0_10": 8,
        "num_colors": 3,
        "elevation": "raised",
        "itching_0_10": 4,
        "pain_0_10": 2,
    }

    example_model = {
        "mel": 0.772,
        "nv": 0.226,
        "vasc": 0.003,
    }

    payload = build_expert_fusion_output(example_symptoms, example_model)
    from pprint import pprint

    pprint(payload)
