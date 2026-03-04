from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen

from certainty_factors import Rule, evaluate_rules

CONTRACT_VERSION = "v1"

MODEL_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["contract_version", "top_class", "top_prob", "top_k"],
    "properties": {
        "contract_version": {"type": "string"},
        "top_class": {"type": "string"},
        "top_prob": {"type": "number"},
        "top_k": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label", "prob"],
                "properties": {
                    "label": {"type": "string"},
                    "prob": {"type": "number"},
                },
            },
        },
        "generated_at": {"type": "string"},
    },
}

EXPERT_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["contract_version", "expert_label", "triage", "explanation"],
    "properties": {
        "contract_version": {"type": "string"},
        "expert_label": {"type": "string"},
        "triage": {"type": "string"},
        "explanation": {
            "type": "object",
            "required": ["rules_fired", "supporting_facts", "counter_facts"],
            "properties": {
                "rules_fired": {"type": "array", "items": {"type": "object"}},
                "supporting_facts": {"type": "array", "items": {"type": "object"}},
                "counter_facts": {"type": "array", "items": {"type": "object"}},
            },
        },
        "generated_at": {"type": "string"},
    },
}

FUSED_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["contract_version", "final_risk", "ui_display"],
    "properties": {
        "contract_version": {"type": "string"},
        "final_risk": {
            "type": "object",
            "required": ["level", "score", "wording"],
            "properties": {
                "level": {"type": "string"},
                "score": {"type": "number"},
                "wording": {"type": "string"},
            },
        },
        "ui_display": {
            "type": "object",
            "required": ["headline", "summary", "one_follow_up_question", "disclaimer"],
            "properties": {
                "headline": {"type": "string"},
                "summary": {"type": "string"},
                "one_follow_up_question": {"type": "string"},
                "disclaimer": {"type": "string"},
            },
        },
    },
}

EVIDENCE_LOOKUP_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["contract_version", "query", "citations"],
    "properties": {
        "contract_version": {"type": "string"},
        "query": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object"}},
        "generated_at": {"type": "string"},
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in {"true", "1", "yes", "y", "on", "checked"}:
        return True
    if s in {"false", "0", "no", "n", "off", "unchecked"}:
        return False
    return None


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _normalize_topk(topk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in topk or []:
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        prob = max(0.0, min(1.0, _safe_float(item.get("prob", 0.0))))
        out.append({"label": label, "prob": round(prob, 4)})
    out.sort(key=lambda x: (-x["prob"], x["label"]))
    return out


def run_model_stage(predictor: Any, image_bytes: bytes, k: int = 3) -> Dict[str, Any]:
    top_k = _normalize_topk(predictor.predict_topk(image_bytes, k=k))
    top = top_k[0] if top_k else {"label": "unknown", "prob": 0.0}

    return {
        "contract_version": CONTRACT_VERSION,
        "top_class": top["label"],
        "top_prob": top["prob"],
        "top_k": top_k,
        "generated_at": _now_iso(),
    }


def _build_expert_evidence(user_answers: Dict[str, Any]) -> Dict[str, float]:
    rapid_change = _to_bool(user_answers.get("rapid_change"))
    bleeding = _to_bool(user_answers.get("bleeding"))
    itching = _to_bool(user_answers.get("itching"))
    pain = _to_bool(user_answers.get("pain"))

    asymmetry = user_answers.get("asymmetry")
    border_irregularity = user_answers.get("border_irregularity")
    color_variegation = user_answers.get("color_variegation")
    diameter_mm = _safe_float(user_answers.get("diameter_mm"), 0.0)
    evolution_speed = str(user_answers.get("evolution_speed") or "").strip().lower()

    evidence = {
        "rapid_change": 0.7 if rapid_change is True else (-0.25 if rapid_change is False else 0.0),
        "bleeding": 0.65 if bleeding is True else (-0.25 if bleeding is False else 0.0),
        "itching": 0.25 if itching is True else (-0.1 if itching is False else 0.0),
        "pain": 0.3 if pain is True else (-0.1 if pain is False else 0.0),
        "no_rapid_change": 0.6 if rapid_change is False else 0.0,
        "no_bleeding": 0.6 if bleeding is False else 0.0,
        "stable_course": 0.6 if evolution_speed in {"stable", "none", "no"} else 0.0,
    }

    if asymmetry is not None:
        asym = _safe_float(asymmetry)
        evidence["asymmetry"] = max(-1.0, min(1.0, (asym - 0.5) * 2.0))

    if border_irregularity is not None:
        border = _safe_float(border_irregularity)
        evidence["border_irregularity"] = max(-1.0, min(1.0, (border - 0.5) * 2.0))

    if color_variegation is not None:
        color = _safe_float(color_variegation)
        evidence["color_variegation"] = max(-1.0, min(1.0, (color - 0.5) * 2.0))

    if diameter_mm > 0:
        if diameter_mm >= 6:
            evidence["diameter_large"] = min(1.0, 0.45 + (diameter_mm - 6.0) * 0.05)
        else:
            evidence["diameter_large"] = -0.35

    return evidence


def _expert_rules() -> List[Rule]:
    return [
        Rule(
            id="EX_HIGH_RAPID_BLEED",
            premises=["rapid_change", "bleeding"],
            operator="AND",
            rule_cf=0.82,
            conclusion="high_risk_flag",
            description="Rapid evolution with bleeding increases high-risk concern.",
            domain="high_risk",
        ),
        Rule(
            id="EX_HIGH_ABCDE",
            premises=["asymmetry", "border_irregularity", "color_variegation"],
            operator="AND",
            rule_cf=0.75,
            conclusion="high_risk_flag",
            description="Concerning ABC features increase high-risk concern.",
            domain="high_risk",
        ),
        Rule(
            id="EX_HIGH_SIZE_CHANGE",
            premises=["diameter_large", "rapid_change"],
            operator="AND",
            rule_cf=0.74,
            conclusion="high_risk_flag",
            description="Large and changing lesion raises high-risk concern.",
            domain="high_risk",
        ),
        Rule(
            id="EX_MOD_SIZE_BORDER",
            premises=["diameter_large", "border_irregularity"],
            operator="AND",
            rule_cf=0.58,
            conclusion="moderate_risk_flag",
            description="Size and border changes indicate moderate risk.",
            domain="moderate_risk",
        ),
        Rule(
            id="EX_MOD_SYMPTOMS",
            premises=["pain", "itching"],
            operator="OR",
            rule_cf=0.48,
            conclusion="moderate_risk_flag",
            description="Symptomatic lesions can indicate moderate risk.",
            domain="moderate_risk",
        ),
        Rule(
            id="EX_LOW_STABLE",
            premises=["stable_course", "no_rapid_change", "no_bleeding"],
            operator="AND",
            rule_cf=0.8,
            conclusion="low_risk_flag",
            description="Stable non-bleeding pattern supports lower risk.",
            domain="low_risk",
        ),
        Rule(
            id="EX_CLINICIAN_REVIEW",
            premises=["high_risk_flag", "moderate_risk_flag"],
            operator="OR",
            rule_cf=0.7,
            conclusion="needs_clinician_review",
            description="Any moderate/high concern should prompt clinician review.",
            domain="triage",
        ),
    ]


def _triage_from_expert_facts(facts: Dict[str, float]) -> str:
    needs_review = _safe_float(facts.get("needs_clinician_review"), 0.0)
    high = _safe_float(facts.get("high_risk_flag"), 0.0)
    moderate = _safe_float(facts.get("moderate_risk_flag"), 0.0)
    low = _safe_float(facts.get("low_risk_flag"), 0.0)

    if needs_review > 0.5:
        return "clinician_review"
    if high > max(moderate, low):
        return "high_risk"
    if moderate > low:
        return "moderate_risk"
    return "low_risk"


def _expert_label_from_triage(triage: str) -> str:
    if triage == "clinician_review":
        return "needs_clinician_review"
    if triage == "high_risk":
        return "high_concern_pattern"
    if triage == "moderate_risk":
        return "moderate_concern_pattern"
    return "low_concern_pattern"


def _follow_up_question(user_answers: Dict[str, Any]) -> str:
    if user_answers.get("evolution_speed") in (None, ""):
        return "Has the spot changed over time (not at all, a little, or a lot)?"
    if user_answers.get("diameter_mm") in (None, ""):
        return "About how wide is the spot at its largest point in millimeters?"
    if user_answers.get("border_irregularity") in (None, ""):
        return "Are the edges mostly smooth or uneven?"
    if user_answers.get("color_variegation") in (None, ""):
        return "Is it one color, two colors, or three or more colors?"
    return "None"


def run_expert_stage(user_answers: Dict[str, Any]) -> Dict[str, Any]:
    evidence = _build_expert_evidence(user_answers or {})
    facts, trace = evaluate_rules(evidence, _expert_rules(), include_skipped=False)

    triage = _triage_from_expert_facts(facts)
    expert_label = _expert_label_from_triage(triage)

    rules_fired = []
    for step in trace:
        if step.get("status") != "applied":
            continue
        contrib = _safe_float(step.get("contrib_cf"), 0.0)
        if abs(contrib) < 1e-9:
            continue
        rules_fired.append(
            {
                "rule_id": step.get("rule_id"),
                "conclusion": step.get("conclusion"),
                "contrib_cf": round(contrib, 4),
                "description": step.get("description", ""),
            }
        )

    supporting_facts = [
        {"fact": key, "cf": round(val, 4)}
        for key, val in sorted(facts.items(), key=lambda kv: (-kv[1], kv[0]))
        if val > 0.0
    ][:10]

    counter_facts = [
        {"fact": key, "cf": round(val, 4)}
        for key, val in sorted(facts.items(), key=lambda kv: (kv[1], kv[0]))
        if val < 0.0
    ][:10]

    return {
        "contract_version": CONTRACT_VERSION,
        "expert_label": expert_label,
        "triage": triage,
        "explanation": {
            "rules_fired": rules_fired,
            "supporting_facts": supporting_facts,
            "counter_facts": counter_facts,
        },
        "one_follow_up_question": _follow_up_question(user_answers or {}),
        "generated_at": _now_iso(),
    }


def _model_risk_score(model_output: Dict[str, Any]) -> float:
    top_k = _normalize_topk(model_output.get("top_k") or [])
    by_label = {x["label"]: x["prob"] for x in top_k}

    mel = _safe_float(by_label.get("mel"), 0.0)
    bcc = _safe_float(by_label.get("bcc"), 0.0)
    akiec = _safe_float(by_label.get("akiec"), 0.0)

    score = mel * 0.95 + max(bcc, akiec) * 0.65
    return max(0.0, min(1.0, score))


def _expert_risk_score(expert_output: Dict[str, Any]) -> float:
    triage = str(expert_output.get("triage") or "").lower()
    if triage == "clinician_review":
        return 0.9
    if triage == "high_risk":
        return 0.82
    if triage == "moderate_risk":
        return 0.58
    return 0.25


def run_fusion_stage(model_output: Dict[str, Any], expert_output: Dict[str, Any]) -> Dict[str, Any]:
    model_score = _model_risk_score(model_output)
    expert_score = _expert_risk_score(expert_output)

    final_score = max(0.0, min(1.0, round(0.62 * model_score + 0.38 * expert_score, 4)))

    if final_score >= 0.75:
        level = "high"
        headline = "High risk pattern detected"
    elif final_score >= 0.45:
        level = "moderate"
        headline = "Moderate risk pattern detected"
    else:
        level = "low"
        headline = "Lower risk pattern detected"

    top_class = model_output.get("top_class") or "unknown"
    expert_triage = expert_output.get("triage") or "unknown"
    rules_fired = (expert_output.get("explanation") or {}).get("rules_fired") or []
    rules_txt = ", ".join([r.get("rule_id", "") for r in rules_fired[:3] if r.get("rule_id")]) or "none"

    one_follow_up_question = expert_output.get("one_follow_up_question") or "None"

    summary = (
        f"Prediction signal is {level} risk (score {final_score:.2f}) using image prediction and expert-rule triage. "
        f"Top model class: {top_class}. Expert triage: {expert_triage}. Supporting rule IDs: {rules_txt}."
    )

    disclaimer = (
        "This is a risk assessment prediction, not a medical diagnosis. "
        "Please consult a licensed clinician for diagnosis and treatment decisions."
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "final_risk": {
            "level": level,
            "score": final_score,
            "wording": "prediction_risk_assessment",
        },
        "ui_display": {
            "headline": headline,
            "summary": summary,
            "one_follow_up_question": one_follow_up_question,
            "disclaimer": disclaimer,
        },
        "generated_at": _now_iso(),
    }


_TRUSTED_EVIDENCE: List[Dict[str, str]] = [
    {
        "title": "Melanoma: Signs and symptoms",
        "url": "https://www.mayoclinic.org/diseases-conditions/melanoma/symptoms-causes/syc-20374884",
        "source": "Mayo Clinic",
        "domain": "mayoclinic.org",
        "tags": "melanoma skin lesion signs symptoms",
    },
    {
        "title": "What to look for: ABCDEs of melanoma",
        "url": "https://www.aad.org/public/diseases/skin-cancer/find/at-risk/abcdes",
        "source": "American Academy of Dermatology",
        "domain": "aad.org",
        "tags": "abcde melanoma warning signs",
    },
    {
        "title": "Skin Cancer",
        "url": "https://medlineplus.gov/skincancer.html",
        "source": "MedlinePlus",
        "domain": "medlineplus.gov",
        "tags": "skin cancer patient education",
    },
    {
        "title": "Skin Cancer",
        "url": "https://www.cancer.gov/types/skin",
        "source": "NIH/NCI",
        "domain": "cancer.gov",
        "tags": "nih skin cancer",
    },
    {
        "title": "Common Moles, Dysplastic Nevi, and Risk of Melanoma",
        "url": "https://www.cancer.gov/types/skin/moles-fact-sheet",
        "source": "NIH/NCI",
        "domain": "cancer.gov",
        "tags": "moles nevus melanoma risk",
    },
]

_ALLOWED_DOMAINS = {
    "aad.org",
    "nih.gov",
    "cancer.gov",
    "medlineplus.gov",
    "mayoclinic.org",
}


def _search_brave_web(query: str, limit: int) -> List[Dict[str, Any]]:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return []

    endpoint = f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}&count={max(1, min(limit, 10))}"
    req = Request(endpoint, headers={"Accept": "application/json", "X-Subscription-Token": api_key})

    with urlopen(req, timeout=12) as resp:  # nosec B310 - trusted HTTPS endpoint
        data = json.loads(resp.read().decode("utf-8"))

    out: List[Dict[str, Any]] = []
    for item in ((data.get("web") or {}).get("results") or []):
        url = str(item.get("url") or "")
        domain = url.split("/")[2].lower() if "//" in url else ""
        base = domain[4:] if domain.startswith("www.") else domain
        if base not in _ALLOWED_DOMAINS:
            continue
        out.append(
            {
                "title": item.get("title") or "Untitled",
                "url": url,
                "source": base,
                "snippet": item.get("description") or "",
                "citation": f"{item.get('title') or 'Untitled'} ({base})",
            }
        )
        if len(out) >= limit:
            break

    return out


def _search_curated(query: str, limit: int) -> List[Dict[str, Any]]:
    q = (query or "").lower()
    ranked = sorted(
        _TRUSTED_EVIDENCE,
        key=lambda item: sum(1 for token in q.split() if token and token in item.get("tags", "")),
        reverse=True,
    )

    out: List[Dict[str, Any]] = []
    for item in ranked[:limit]:
        out.append(
            {
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "snippet": f"Trusted reference from {item['source']}.",
                "citation": f"{item['title']} ({item['source']})",
            }
        )
    return out


def run_evidence_lookup(query: str, limit: int = 5, use_web: bool = True) -> Dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        q = "skin lesion risk signs"

    cap = max(1, min(int(limit), 10))

    citations: List[Dict[str, Any]] = []
    source_mode = "curated"

    if use_web:
        try:
            citations = _search_brave_web(q, cap)
            if citations:
                source_mode = "web+trusted-filter"
        except Exception:
            citations = []

    if not citations:
        citations = _search_curated(q, cap)

    return {
        "contract_version": CONTRACT_VERSION,
        "query": q,
        "lookup_mode": source_mode,
        "citations": citations,
        "generated_at": _now_iso(),
    }
