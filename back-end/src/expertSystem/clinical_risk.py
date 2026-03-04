from __future__ import annotations

from typing import Any, Dict, List

RISK_RANK = {"low": 1, "moderate": 2, "high": 3}


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y", "on"}:
        return True
    if s in {"false", "0", "no", "n", "off"}:
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
        num = float(value)
    except Exception:
        return None
    if not num.is_integer():
        return None
    return int(num)


def normalize_risk_label(label: str | None) -> str:
    t = str(label or "").strip().lower()
    if t in {"high", "high_risk", "clinician_review"}:
        return "high"
    if t in {"moderate", "moderate_risk"}:
        return "moderate"
    return "low"


def max_risk_label(*labels: str) -> str:
    best = "low"
    for item in labels:
        level = normalize_risk_label(item)
        if RISK_RANK[level] > RISK_RANK[best]:
            best = level
    return best


def recommended_next_step(level: str) -> str:
    lvl = normalize_risk_label(level)
    if lvl == "high":
        return "Urgent dermatology visit recommended (ideally within 24–48 hours)."
    if lvl == "moderate":
        return "Schedule a dermatology appointment soon for in-person assessment."
    return "Monitor for changes and arrange a routine dermatology follow-up if concerns persist."


def compute_model_risk(model_topk: List[Dict[str, Any]] | None, fallback_label: str | None = None) -> Dict[str, Any]:
    topk = model_topk or []
    by_label = {}
    for item in topk:
        label = str(item.get("label") or "").strip().lower()
        try:
            prob = float(item.get("prob", item.get("confidence", 0.0)) or 0.0)
        except Exception:
            prob = 0.0
        by_label[label] = max(0.0, min(1.0, prob))

    mel = by_label.get("mel", 0.0)
    bcc = by_label.get("bcc", 0.0)
    akiec = by_label.get("akiec", 0.0)
    malignant_signal = max(mel, bcc, akiec)

    if malignant_signal >= 0.65:
        level = "high"
    elif malignant_signal >= 0.35:
        level = "moderate"
    else:
        level = "low"

    if fallback_label:
        level = max_risk_label(level, fallback_label)

    return {
        "level": level,
        "score": round(malignant_signal, 4),
        "facts": [
            {"name": "mel_prob", "value": round(mel, 4)},
            {"name": "bcc_prob", "value": round(bcc, 4)},
            {"name": "akiec_prob", "value": round(akiec, 4)},
        ],
    }


def compute_clinical_risk(answers: Dict[str, Any] | None, extras: Dict[str, Any] | None = None) -> Dict[str, Any]:
    src = dict(answers or {})
    ext = dict(extras or {})

    bleeding = _to_bool(src.get("bleeding"))
    rapid_change = _to_bool(src.get("rapid_change"))
    width_mm = _to_float(src.get("width_mm", src.get("diameter_mm")))
    border_0_10 = _to_float(src.get("border_0_10", src.get("border_irregularity")))
    num_colors = _to_int(src.get("num_colors", src.get("number_of_colors")))
    elevation = str(src.get("elevation") or "").strip().lower() or None
    itching_0_10 = _to_float(src.get("itching_0_10", src.get("itching")))
    pain_0_10 = _to_float(src.get("pain_0_10", src.get("pain")))

    age = _to_int(ext.get("age", ext.get("patient_age")))
    duration_days = _to_int(ext.get("duration_days"))
    family_history = str(ext.get("familyHistory", ext.get("family_melanoma_history", ""))).strip().lower()

    points = 0
    facts: List[Dict[str, Any]] = []

    required = {
        "bleeding": bleeding,
        "rapid_change": rapid_change,
        "width_mm": width_mm,
        "border_0_10": border_0_10,
        "num_colors": num_colors,
        "elevation": elevation,
    }
    missing_required = [key for key, value in required.items() if value in (None, "")]

    if bleeding is True:
        points += 3
        facts.append({"factor": "bleeding", "points": 3, "value": "yes"})

    if rapid_change is True:
        points += 3
        facts.append({"factor": "rapid_change", "points": 3, "value": "yes"})

    if width_mm is not None:
        if width_mm >= 10:
            points += 3
            facts.append({"factor": "width_mm", "points": 3, "value": width_mm})
        elif width_mm >= 6:
            points += 2
            facts.append({"factor": "width_mm", "points": 2, "value": width_mm})

    if border_0_10 is not None:
        if border_0_10 >= 7:
            points += 2
            facts.append({"factor": "border_0_10", "points": 2, "value": border_0_10})
        elif border_0_10 >= 4:
            points += 1
            facts.append({"factor": "border_0_10", "points": 1, "value": border_0_10})

    if num_colors is not None:
        if num_colors >= 3:
            points += 2
            facts.append({"factor": "num_colors", "points": 2, "value": num_colors})
        elif num_colors == 2:
            points += 1
            facts.append({"factor": "num_colors", "points": 1, "value": num_colors})

    if elevation in {"nodular", "nodule"}:
        points += 2
        facts.append({"factor": "elevation", "points": 2, "value": "nodular"})
    elif elevation in {"raised", "elevated", "bump"}:
        points += 1
        facts.append({"factor": "elevation", "points": 1, "value": "raised"})

    if itching_0_10 is not None and itching_0_10 >= 7:
        points += 1
        facts.append({"factor": "itching_0_10", "points": 1, "value": itching_0_10})

    if pain_0_10 is not None and pain_0_10 >= 7:
        points += 1
        facts.append({"factor": "pain_0_10", "points": 1, "value": pain_0_10})

    if age is not None and age >= 60:
        points += 1
        facts.append({"factor": "age", "points": 1, "value": age})

    if duration_days is not None and duration_days >= 30:
        points += 1
        facts.append({"factor": "duration_days", "points": 1, "value": duration_days})

    if family_history and family_history not in {"none", "no", "unknown", "n/a"}:
        points += 1
        facts.append({"factor": "family_history", "points": 1, "value": family_history})

    if points >= 8:
        level = "high"
    elif points >= 4:
        level = "moderate"
    else:
        level = "low"

    return {
        "points": points,
        "level": level,
        "facts": facts,
        "required_fields": list(required.keys()),
        "missing_required": missing_required,
    }


def build_combined_risk_summary(
    answers: Dict[str, Any] | None,
    model_topk: List[Dict[str, Any]] | None,
    model_label_hint: str | None = None,
    extras: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    clinical = compute_clinical_risk(answers, extras)
    model = compute_model_risk(model_topk, model_label_hint)
    final_level = max_risk_label(model.get("level", "low"), clinical.get("level", "low"))

    return {
        "clinical": clinical,
        "model": model,
        "final": {
            "level": final_level,
            "method": "max(model_risk, clinical_risk)",
            "recommended_next_step": recommended_next_step(final_level),
        },
    }
