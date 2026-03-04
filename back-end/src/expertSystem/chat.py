# File: expertSystem/chat.py
# Role: Gemini-powered dermatology intake assistant (NOT a diagnosis system).

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import os, json, time, re
from collections.abc import Mapping

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=True)
print("[load] chat.py from:", __file__)
print("[dotenv] file:", find_dotenv(usecwd=True))
print("[env] GOOGLE_API_KEY?", bool(os.getenv("GOOGLE_API_KEY")))

import google.generativeai as genai
from expertSystem.clinical_risk import build_combined_risk_summary
from expertSystem.medical_references_cache import format_references_section
from expertSystem.cf_probability_integration import run_cf_disease_fusion


# ---------------------------
# Helpers
# ---------------------------

def _coerce_call_args(raw) -> Dict[str, Any]:
    """
    Accepts SDK variants of function_call.args/arguments:
    - str/bytes (older SDK) -> json.loads
    - Mapping/MapComposite (newer SDK) -> plain dict
    Falls back safely to {}.
    """
    if raw is None:
        return {}
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            return json.loads(raw or "{}")
        except Exception:
            return {}
    if isinstance(raw, Mapping):
        try:
            return dict(raw)
        except Exception:
            try:
                return {k: raw[k] for k in raw.keys()}
            except Exception:
                return {}
    try:
        return json.loads(str(raw))
    except Exception:
        return {}


def _resp_text(resp) -> str:
    try:
        cand = (resp.candidates or [None])[0]
        parts = getattr(getattr(cand, "content", None), "parts", []) or []
        pieces = [getattr(p, "text", "") for p in parts if getattr(p, "text", None)]
        txt = "".join(pieces).strip()
        if txt:
            return txt
    except Exception:
        pass
    return (getattr(resp, "text", None) or "").strip()


def _sanitize_user_reply(text: str) -> str:
    """
    Remove internal context/instruction echoes from model output so only
    user-facing content is returned to the chat UI.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""

    blocked_prefixes = (
        "[clinical context]",
        "[reasoning inputs]",
        "[response constraints]",
        "interview mode instructions",
        "reasoning inputs:",
        "clinical context:",
        "response constraints:",
    )

    filtered_lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith(blocked_prefixes):
            continue
        if low.startswith("- use only the reasoning inputs"):
            continue
        if low.startswith("- do not invent"):
            continue
        if low.startswith("- ask at most one focused"):
            continue
        if low.startswith("- keep tone clinical"):
            continue
        filtered_lines.append(s)

    cleaned = "\n".join(filtered_lines).strip()
    return cleaned


def _retry_api_call(fn, *args, max_retries: int = 4, base_delay: float = 1.0):
    """
    Call `fn(*args)` with exponential backoff retry for transient rate-limit/resource errors.
    Retries when exception message contains 429 / Resource exhausted / rate limit.
    """
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args)
        except Exception as e:
            last_err = e
            msg = str(e) or ""
            is_rate = ("429" in msg) or ("resource exhausted" in msg.lower()) or ("rate limit" in msg.lower())
            if not is_rate:
                raise
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(f"[retry] attempt {attempt} failed: {msg[:180]} -- sleeping {delay}s")
            time.sleep(delay)
    raise last_err


def _norm_meta(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Frontend keys -> backend canonical keys.
    This lets Gemini + the tool see consistent field names.
    """
    m = dict(metadata or {})

    # Upload.jsx sends "location" and "skinType"
    if m.get("location") and not m.get("body_site"):
        m["body_site"] = m["location"]
    if m.get("skinType") and not m.get("fitzpatrick"):
        m["fitzpatrick"] = m["skinType"]

    # Accept either "age" or "patient_age"
    if m.get("age") is not None and m.get("patient_age") is None:
        m["patient_age"] = m["age"]

    # Coerce numerics when safe
    for k in ("age", "patient_age", "duration_days", "duration_weeks", "diameter_mm"):
        if k in m and m[k] not in (None, ""):
            try:
                m[k] = float(m[k])
            except Exception:
                pass

    return m


def _parse_yes_no(s: str) -> Optional[bool]:
    t = (s or "").strip().lower()
    if t in {"yes", "y", "yeah", "yep", "true"}:
        return True
    if t in {"no", "n", "nope", "false"}:
        return False
    return None


def _parse_symptom_scale(s: str) -> Optional[float]:
    t = (s or "").strip().lower()

    # Accept numeric answers like "2", "0", "10"
    try:
        n = float(t)
        if n < 0:
            n = 0.0
        if n > 10:
            n = 10.0
        return n
    except Exception:
        pass

    # Accept words
    if t == "none":
        return 0.0
    if t == "mild":
        return 2.0
    if t == "moderate":
        return 5.0
    if t == "severe":
        return 8.0

    return None


def _infer_pending_from_last_bot(state: "ConvState") -> None:
    """
    Figure out what the last bot question was asking, so we can store the user's
    next answer deterministically (prevents repeating the same question forever).
    """
    if not state.history:
        return
    last = state.history[-1]
    if last.get("role") != "model":
        return
    txt = (last.get("parts") or [{}])[0].get("text", "")
    t = txt.lower()

    if "has it bled" in t or ("bled" in t and "crust" not in t):
        state.pending_slot = "bleeding"
    elif "crust" in t or "scab" in t:
        state.pending_slot = "crusting"
    elif "itch" in t:
        state.pending_slot = "itching"
    elif "pain" in t:
        state.pending_slot = "pain"
    elif "raised" in t or "flat" in t or "nodular" in t:
        state.pending_slot = "elevation"
    elif "edges" in t and ("smooth" in t or "uneven" in t):
        state.pending_slot = "border_irregularity"
    elif "imagine folding" in t:
        state.pending_slot = "asymmetry"
    elif "how many colors" in t:
        state.pending_slot = "number_of_colors"
    elif "how wide" in t or "diameter" in t or "mm" in t:
        state.pending_slot = "diameter_mm"


def _apply_pending_slot(state: "ConvState", user_text: Optional[str]) -> None:
    """
    Turn the user's last answer into structured slots.
    """
    if not user_text:
        return

    slot = state.pending_slot
    if not slot:
        return

    ut = user_text.strip()
    low = ut.lower()

    # yes/no slots
    if slot in {"bleeding", "crusting"}:
        yn = _parse_yes_no(ut)
        if yn is not None:
            state.slots[slot] = yn
            state.pending_slot = None
        return

    # symptoms
    if slot == "itching":
        v = _parse_symptom_scale(ut)
        if v is not None:
            state.slots["itching_0_10"] = v
            state.pending_slot = None
        return

    if slot == "pain":
        v = _parse_symptom_scale(ut)
        if v is not None:
            state.slots["pain_0_10"] = v
            state.pending_slot = None
        return

    # elevation
    if slot == "elevation":
        if low in {"flat", "raised", "nodular"}:
            state.slots["elevation"] = low
            state.pending_slot = None
        return

    # border irregularity (smooth vs uneven)
    if slot == "border_irregularity":
        if "not smooth" in low or "irregular" in low or "uneven" in low:
            state.slots["border_irregularity"] = 1.0
            state.pending_slot = None
            return
        if "smooth" in low:
            state.slots["border_irregularity"] = 0.0
            state.pending_slot = None
            return
        if "not sure" in low or low in {"unsure", "idk"}:
            state.slots["border_irregularity"] = None
            state.pending_slot = None
            return
        return

    # asymmetry mapping
    if slot == "asymmetry":
        if low in {"yes", "no", "not sure"}:
            if low == "yes":
                state.slots["asymmetry"] = 1.0
            elif low == "no":
                state.slots["asymmetry"] = 0.0
            else:
                state.slots["asymmetry"] = None
            state.pending_slot = None
        return

    # number_of_colors mapping
    if slot == "number_of_colors":
        if low in {"one", "two", "three+", "3+", "not sure", "1", "2", "3"}:
            if low in {"one", "1"}:
                state.slots["number_of_colors"] = 1.0
                state.slots["color_variegation"] = 0.0
            elif low in {"two", "2"}:
                state.slots["number_of_colors"] = 2.0
                state.slots["color_variegation"] = 0.5
            elif low in {"three+", "3+", "3"}:
                state.slots["number_of_colors"] = 3.0
                state.slots["color_variegation"] = 1.0
            else:
                state.slots["number_of_colors"] = None
                state.slots["color_variegation"] = None
            state.pending_slot = None
        return

    # diameter parsing (mm)
    if slot == "diameter_mm":
        m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(mm|millimeter|millimeters)?\b", low)
        if m:
            try:
                state.slots["diameter_mm"] = float(m.group(1))
                state.pending_slot = None
            except Exception:
                pass
        return


# ---------------------------
# API key & model
# ---------------------------

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("No API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY in .env/environment.")
genai.configure(api_key=API_KEY)

ENV_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
print(f"[Gemini] Env model: {ENV_MODEL_NAME}")


# ---------------------------
# Conversation state
# ---------------------------

@dataclass
class ConvState:
    history: List[Dict[str, Any]] = field(default_factory=list)

    # structured memory so we don't repeat questions forever
    slots: Dict[str, Any] = field(default_factory=dict)
    answers: Dict[str, Any] = field(default_factory=dict)
    pending_slot: Optional[str] = None
    case_state: Dict[str, Any] = field(default_factory=dict)

    def trim_history(self, max_turns: int = 10):
        max_messages = max_turns * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]


# ---------------------------
# Tool declaration
# ---------------------------

FUNCTIONS = [{
    "name": "expert_derm_consult",
    "description": "Combine history/ABCDE and optional classifier probs into a risk-oriented triage summary.",
    "parameters": {
        "type": "object",
        "properties": {
            "body_site": {"type": "string", "description": "e.g., left forearm"},
            "diameter_mm": {"type": "number", "description": "Largest diameter in millimeters"},
            "duration_weeks": {"type": "number", "description": "How long the lesion has been noticeable"},
            "evolution_weeks": {"type": "number", "description": "Weeks of noticeable change"},
            "evolution_speed": {"type": "string", "description": "stable|slow|moderate|rapid"},
            "elevation": {"type": "string", "description": "flat|raised|nodular"},
            "itching_0_10": {"type": "number"},
            "pain_0_10": {"type": "number"},
            "bleeding": {"type": "boolean"},
            "crusting": {"type": "boolean"},
            "ulceration": {"type": "boolean"},
            "asymmetry": {"type": "number", "description": "0..1"},
            "border_irregularity": {"type": "number", "description": "0..1"},
            "color_variegation": {"type": "number", "description": "0..1"},
            "number_of_colors": {"type": "number"},
            "patient_age": {"type": "number"},
            "fitzpatrick_type": {"type": "string", "description": "I|II|III|IV|V|VI"},
            "sunburn_history": {"type": "string", "description": "none|some|frequent"},
            "tanning_bed_use": {"type": "boolean"},
            "sunscreen_use": {"type": "string", "description": "never|sometimes|regular"},
            "personal_melanoma_history": {"type": "boolean"},
            "family_melanoma_history": {"type": "boolean"},
            "immunosuppressed": {"type": "boolean"},
            "prior_biopsies_here": {"type": "boolean"},
            "classifier_probs": {
                "type": "object",
                "description": "Optional posterior probabilities (0..1) from your CNN.",
                "properties": {
                    "melanoma": {"type": "number"},
                    "nevus": {"type": "number"},
                    "bcc": {"type": "number"},
                    "scc": {"type": "number"},
                    "bkl": {"type": "number"},
                    "df": {"type": "number"},
                    "vasc": {"type": "number"}
                }
            }
        },
        "required": ["body_site", "patient_age"]
    }
}]


# ---------------------------
# System instruction
# ---------------------------

SYSTEM_INSTRUCTION = (
    "You are a dermatology intake assistant in a research prototype. "
    "Provide risk-oriented triage support, not definitive diagnosis or treatment.\n\n"

    "NON-FABRICATION RULES:\n"
    "• Use ONLY user-provided data, tool outputs, and seeded reasoning inputs.\n"
    "• Never invent symptoms, exam findings, probabilities, timelines, or risk factors.\n"
    "• If a fact is missing, explicitly mark it as missing and ask one focused follow-up question.\n\n"

    "CONVERSATION RULES:\n"
    "• Never repeat a question already answered in this session.\n"
    "• Never claim you cannot see intake data if it exists in structured case context.\n"
    "• Never ask for a field that already exists in structured case context.\n"
    "• Track captured fields (body site, diameter, evolution, ABCDE, symptoms, age/skin type).\n"
    "• Ask at most 1 question per turn, with simple choices and a 'Not sure' option.\n"
    "• Default mode is INTERVIEW: ask the next best missing question and keep response to 1-3 short lines.\n\n"

    "OUTPUT POLICY:\n"
    "• Return output as JSON with keys: message (string), follow_up_question (string|null), fields_needed (array of strings), ready_for_assessment (boolean).\n"
    "• Include one safety line: This is not a diagnosis; in-person clinician review is recommended for concerning changes.\n"
)


# ---------------------------
# Model init with fallbacks
# ---------------------------

PREFERRED = ENV_MODEL_NAME
CANDIDATES = [PREFERRED, "gemini-1.5-flash-8b", "gemini-1.5-flash", "gemini-1.5-pro"]

MODEL = None
MODEL_NAME = PREFERRED

def _make_model(name: str):
    return genai.GenerativeModel(
        model_name=name,
        tools=[{"function_declarations": FUNCTIONS}],
        system_instruction=SYSTEM_INSTRUCTION,
    )

def _get_model():
    global MODEL, MODEL_NAME
    if MODEL is not None:
        return MODEL
    last_err = None
    for name in [n for n in CANDIDATES if n]:
        try:
            m = _make_model(name)
            m.start_chat()  # touch only; no generate call
            MODEL, MODEL_NAME = m, name
            print(f"[Gemini] Using model: {name}")
            return MODEL
        except Exception as e:
            print(f"[Gemini] '{name}' failed at init: {e}")
            last_err = e
    raise RuntimeError(f"No working Gemini model from {CANDIDATES}. Last error: {last_err}")


# ---------------------------
# Rule engine
# ---------------------------

def _run_rules(payload: Dict[str, Any]) -> Dict[str, Any]:
    intake_score = 0.0
    reasons = []

    # Size / evolution
    d = payload.get("diameter_mm")
    if d is not None:
        try:
            d = float(d)
        except Exception:
            d = None

    if d is not None and d >= 6:
        intake_score += 0.35
        reasons.append("Diameter ≥ 6 mm")

    if (payload.get("evolution_speed") or "").lower() in {"rapid", "moderate"}:
        intake_score += 0.2
        reasons.append("Recent change")

    # Symptoms
    if payload.get("bleeding") is True:
        intake_score += 0.2
        reasons.append("Bleeding")
    if payload.get("ulceration") is True:
        intake_score += 0.2
        reasons.append("Ulceration")
    if (payload.get("pain_0_10") or 0) >= 5:
        intake_score += 0.05
        reasons.append("Pain ≥ 5/10")
    if (payload.get("itching_0_10") or 0) >= 5:
        intake_score += 0.03
        reasons.append("Itching ≥ 5/10")

    # ABCDE
    if (payload.get("asymmetry") or 0) > 0.5:
        intake_score += 0.1
        reasons.append("Asymmetry")
    if (payload.get("border_irregularity") or 0) > 0.5:
        intake_score += 0.1
        reasons.append("Irregular border")
    if (payload.get("color_variegation") or 0) > 0.5:
        intake_score += 0.1
        reasons.append("Variegated color")
    if (payload.get("number_of_colors") or 0) >= 3:
        intake_score += 0.05
        reasons.append("≥3 colors")

    # Risk factors
    if (payload.get("patient_age") or 0) >= 60:
        intake_score += 0.05
        reasons.append("Age ≥ 60")
    if payload.get("family_melanoma_history"):
        intake_score += 0.05
        reasons.append("Family melanoma history")
    if payload.get("immunosuppressed"):
        intake_score += 0.07
        reasons.append("Immunosuppressed")

    # (Optional) model probability contribution (kept internally)
    clf = (payload.get("classifier_probs") or {})
    try:
        mel_p = float(clf.get("melanoma", 0.0))
    except Exception:
        mel_p = 0.0
    model_score = max(0.0, min(mel_p, 1.0))
    if model_score > 0.0:
        reasons.append(f"Model melanoma probability {model_score:.2f}")

    intake_score = max(0.0, min(intake_score, 0.98))
    combined_score = max(0.0, min(0.6 * intake_score + 0.4 * model_score, 0.98))

    if intake_score >= 0.7:
        intake_label = "high"
    elif intake_score >= 0.4:
        intake_label = "moderate"
    else:
        intake_label = "low"

    if combined_score >= 0.7:
        combined_label = "high"
    elif combined_score >= 0.4:
        combined_label = "moderate"
    else:
        combined_label = "low"

    out = {
        "findings": [
            {"label": "intake_only_risk", "score": round(intake_score, 2)},
            {"label": "combined_risk", "score": round(combined_score, 2)},
            {"label": "benign_likelihood", "score": round(1 - combined_score, 2)},
        ],
        "rule_explanations": [
            {"rule_id": "R-ABCDE-intake", "why": ", ".join(reasons) or "No major flags"}
        ],
        "safety_flags": ["not_a_diagnosis"],
        "next_questions": [],
        "audit": {
            "rules_fired": ["R-ABCDE-intake"],
            "intake_prediction": {"label": intake_label, "score": round(intake_score, 2)},
            "combined_prediction": {"label": combined_label, "score": round(combined_score, 2)},
            "model_melanoma_probability": round(model_score, 2),
        },
    }

    # Ask only 1 question at a time
    needed = []
    if payload.get("body_site") in (None, ""):
        needed.append("Where on the body is it? (e.g., left forearm)")
    elif payload.get("diameter_mm") is None:
        needed.append("About how wide is it at the largest point (in mm)? A pencil eraser is ~6 mm.")
    elif payload.get("evolution_speed") is None:
        needed.append("Has it been changing recently? (No / A little / A lot / Not sure)")
    elif payload.get("bleeding") is None:
        needed.append("Has it bled? (Yes / No / Not sure)")
    elif payload.get("crusting") is None:
        needed.append("Has it formed a crust or scab? (Yes / No / Not sure)")
    elif payload.get("number_of_colors") is None:
        needed.append("One color, two colors, or three or more? (One / Two / Three+ / Not sure)")

    if not needed:
        if payload.get("asymmetry") is None:
            needed.append("If you imagine folding it in half, do both sides look similar? (Yes / No / Not sure)")
        elif payload.get("border_irregularity") is None:
            needed.append("Are the edges mostly smooth or uneven? (Smooth / Uneven / Not sure)")
        elif payload.get("color_variegation") is None:
            needed.append("Do you see one color, two colors, or three or more colors? (One / Two / Three+ / Not sure)")
        elif payload.get("elevation") in (None, ""):
            needed.append("Does it feel flat, raised, or nodular? (Flat / Raised / Nodular / Not sure)")
        elif payload.get("ulceration") is None:
            needed.append("Is there any open sore or ulceration? (Yes / No / Not sure)")
        elif payload.get("crusting") is None:
            needed.append("Has it formed a crust or scab at any point? (Yes / No / Not sure)")

    out["next_questions"] = needed[:1]
    return out


def _build_structured_case_context(state: ConvState, metadata: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(state.case_state or {})

    external_case_state = metadata.get("session_case_state") if metadata else None
    if isinstance(external_case_state, dict):
        merged.update(external_case_state)

    if metadata:
        if metadata.get("name"):
            merged["name"] = metadata.get("name")
        if metadata.get("patient_age") is not None:
            merged["age"] = metadata.get("patient_age")
        if metadata.get("fitzpatrick"):
            merged["skin_type"] = metadata.get("fitzpatrick")
        if metadata.get("body_site"):
            merged["lesion_location"] = metadata.get("body_site")
        if metadata.get("duration_days") is not None:
            merged["duration_days"] = metadata.get("duration_days")

        if metadata.get("primary_result"):
            merged["current_triage"] = metadata.get("primary_result")

        if metadata.get("model_topk"):
            try:
                model_probs = (
                    metadata.get("model_topk")
                    if isinstance(metadata.get("model_topk"), list)
                    else json.loads(str(metadata.get("model_topk")))
                )
                merged["model_probabilities"] = model_probs
            except Exception:
                pass

        if metadata.get("classifier_probs"):
            merged["model_probabilities"] = metadata.get("classifier_probs")

    symptom_map = {
        "bleeding": state.slots.get("bleeding"),
        "crusting": state.slots.get("crusting"),
        "itching_0_10": state.slots.get("itching_0_10"),
        "pain_0_10": state.slots.get("pain_0_10"),
        "elevation": state.slots.get("elevation"),
        "asymmetry": state.slots.get("asymmetry"),
        "border_irregularity": state.slots.get("border_irregularity"),
        "color_variegation": state.slots.get("color_variegation"),
        "number_of_colors": state.slots.get("number_of_colors"),
        "diameter_mm": state.slots.get("diameter_mm"),
    }

    merged_symptoms = dict(merged.get("symptom_flags") or {})
    for k, v in symptom_map.items():
        if v is not None:
            merged_symptoms[k] = v
    if merged_symptoms:
        merged["symptom_flags"] = merged_symptoms

    merged["known_slots"] = {k: v for k, v in state.slots.items() if v is not None}

    required = [
        "lesion_location",
        "age",
        "duration_days",
        "symptom_flags.bleeding",
        "symptom_flags.itching_0_10",
        "symptom_flags.pain_0_10",
        "symptom_flags.diameter_mm",
        "symptom_flags.border_irregularity",
        "symptom_flags.color_variegation",
    ]

    missing: List[str] = []
    for key in required:
        if "." in key:
            head, tail = key.split(".", 1)
            part = merged.get(head) or {}
            if not isinstance(part, dict) or part.get(tail) in (None, ""):
                missing.append(key)
        else:
            if merged.get(key) in (None, ""):
                missing.append(key)

    merged["missing_fields"] = missing
    state.case_state = merged
    return merged


def _build_llm_turn_input(case_context: Dict[str, Any], user_text: Optional[str]) -> str:
    user_part = (user_text or "").strip()
    context_json = json.dumps(case_context, ensure_ascii=False)
    return (
        "[STRUCTURED_CASE_CONTEXT]\n"
        f"{context_json}\n"
        "[/STRUCTURED_CASE_CONTEXT]\n"
        "Rules: Do not ask for fields already present under known_slots/case context. "
        "Ask only one highest-priority missing field when needed. "
        "Return ONLY valid JSON object with keys: message, follow_up_question, fields_needed, ready_for_assessment.\n\n"
        f"User message: {user_part}"
    )


def _default_follow_up_from_missing(case_context: Dict[str, Any]) -> str:
    missing = list(case_context.get("missing_fields") or [])
    if "lesion_location" in missing:
        return "Where on the body is the lesion located?"
    if "symptom_flags.diameter_mm" in missing:
        return "About how wide is it at the largest point (in mm)?"
    if "symptom_flags.border_irregularity" in missing:
        return "Are the edges mostly smooth or uneven?"
    if "symptom_flags.color_variegation" in missing:
        return "Is it one color, two colors, or three or more colors?"
    if "symptom_flags.bleeding" in missing:
        return "Has it bled recently?"
    if "duration_days" in missing:
        return "How many days has it been present?"
    return "None"


def _sanitize_follow_up_question(question: str, case_context: Dict[str, Any]) -> str:
    q = str(question or "").strip()
    if not q:
        q = "None"

    location_known = bool(case_context.get("lesion_location") or case_context.get("known_slots", {}).get("body_site"))
    if location_known:
        low = q.lower()
        if "where" in low and ("body" in low or "location" in low or "located" in low):
            q = _default_follow_up_from_missing(case_context)

    return q


def _derive_fields_needed(case_context: Dict[str, Any]) -> List[str]:
    mapping = {
        "lesion_location": "location",
        "age": "age",
        "duration_days": "duration",
        "symptom_flags.bleeding": "bleeding",
        "symptom_flags.itching_0_10": "itching",
        "symptom_flags.pain_0_10": "pain",
        "symptom_flags.diameter_mm": "diameter_mm",
        "symptom_flags.border_irregularity": "border_irregularity",
        "symptom_flags.color_variegation": "color_variegation",
    }
    out: List[str] = []
    for key in list(case_context.get("missing_fields") or []):
        out.append(mapping.get(key, key))
    return out


def _parse_structured_reply(raw_text: str, case_context: Dict[str, Any], fallback_question: str) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    txt = str(raw_text or "").strip()

    def _load_json_from_text(s: str) -> Dict[str, Any]:
        src = str(s or "").strip()
        if not src:
            return {}

        try:
            obj = json.loads(src)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", src, flags=re.IGNORECASE)
        if fenced:
            try:
                obj = json.loads(fenced.group(1))
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

        start = src.find("{")
        end = src.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = src[start: end + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

        return {}

    parsed = _load_json_from_text(txt)

    message = str(parsed.get("message") or txt or "").strip()
    message = re.sub(r"```(?:json)?", "", message, flags=re.IGNORECASE).replace("```", "").strip()

    follow_up_question = str(parsed.get("follow_up_question") or fallback_question or "None").strip()
    follow_up_question = _sanitize_follow_up_question(follow_up_question, case_context)

    fields_needed = parsed.get("fields_needed")
    if not isinstance(fields_needed, list):
        fields_needed = _derive_fields_needed(case_context)

    ready_for_assessment = parsed.get("ready_for_assessment")
    if not isinstance(ready_for_assessment, bool):
        ready_for_assessment = len(fields_needed) == 0

    if not message:
        message = "I have your latest update."

    return {
        "message": message,
        "follow_up_question": follow_up_question,
        "fields_needed": fields_needed,
        "ready_for_assessment": ready_for_assessment,
    }


def _format_tool_reply(payload: Dict[str, Any]) -> str:
    intake_risk = next((f["score"] for f in payload.get("findings", []) if f.get("label") == "intake_only_risk"), None)

    audit = payload.get("audit", {}) or {}
    intake_pred = (audit.get("intake_prediction") or {}).get("label") or "unknown"

    lines = ["Expert-system triage (intake-based):"]

    if intake_risk is not None:
        lines.append(f"- Risk: {intake_pred.upper()} ({int(round(float(intake_risk) * 100))}%)")

    reasons = payload.get("rule_explanations", []) or []
    if reasons:
        why = (reasons[0].get("why") or "").strip()
        if why:
            lines.append(f"Evidence used: {why}")

    lines.append("This is not a diagnosis; in-person clinician review is recommended for concerning changes.")
    return "\n".join(lines)


QUESTION_FLOW: List[Dict[str, str]] = [
    {"key": "bleeding", "prompt": "Has the lesion bled? (yes/no)"},
    {"key": "itching", "prompt": "How itchy is it on a 0–10 scale?"},
    {"key": "width_mm", "prompt": "What is the lesion width at the largest point (in mm)?"},
    {"key": "border_irregularity", "prompt": "How irregular are the borders on a 0–10 scale?"},
    {"key": "num_colors", "prompt": "How many colors do you see? (integer, e.g., 1, 2, 3)"},
    {"key": "elevation", "prompt": "What is the elevation? (flat/raised/nodular)"},
    {"key": "pain", "prompt": "How painful is it on a 0–10 scale?"},
]


def _extract_number(text: str) -> Optional[float]:
    m = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


_NUMBER_WORDS: Dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def _normalize_free_text(text: str) -> str:
    low = str(text or "").strip().lower()
    low = low.replace("–", "-")
    low = low.replace("—", "-")
    low = re.sub(r"[~≈]", " ", low)
    low = re.sub(r"\babout\b|\baround\b|\bmaybe\b|\broughly\b|\bapproximately\b|\bkinda\b|\bkind of\b", " ", low)
    low = re.sub(r"\bmillimeters?\b|\bmillimetres?\b|\bmm\b", " ", low)
    low = re.sub(r"[^a-z0-9+/\.\-\s]", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    return low


def _replace_number_words(text: str) -> str:
    out = str(text or "")
    for word, val in _NUMBER_WORDS.items():
        out = re.sub(rf"\b{re.escape(word)}\b", str(val), out)
    return out


def _extract_numeric_value(text: str) -> Optional[float]:
    cleaned = _replace_number_words(_normalize_free_text(text))

    ratio = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*10\b", cleaned)
    if ratio:
        try:
            return float(ratio.group(1))
        except Exception:
            pass

    return _extract_number(cleaned)


def _extract_integer_value(text: str) -> Optional[int]:
    n = _extract_numeric_value(text)
    if n is None:
        return None
    if float(n).is_integer():
        return int(n)
    return None


def _parse_yes_no_strict(text: str) -> Optional[bool]:
    low = _normalize_free_text(text)
    if re.search(r"\b(yes|y|yeah|yep|true|sure|affirmative)\b", low):
        return True
    if re.search(r"\b(no|n|nope|false|negative)\b", low):
        return False
    return None


def _parse_zero_to_ten(text: str) -> Dict[str, Any]:
    low = _normalize_free_text(text)
    if re.search(r"\b(yes|no|true|false|y|n)\b", low):
        return {"ok": False, "error": "Please enter a number 0–10."}

    n = _extract_numeric_value(low)
    if n is None:
        return {"ok": False, "error": "Please enter a number 0–10."}
    normalized = max(0.0, min(10.0, float(n)))
    return {
        "ok": True,
        "value": normalized,
        "normalized_text": str(normalized),
    }


def _parse_width_mm(text: str) -> Dict[str, Any]:
    n = _extract_numeric_value(text)
    if n is None or n <= 0:
        return {"ok": False, "error": "Please enter a positive width in mm (for example: 6)."}
    return {
        "ok": True,
        "value": float(n),
        "normalized_text": f"{float(n):g} mm",
    }


def _parse_num_colors(text: str) -> Dict[str, Any]:
    low = _normalize_free_text(text)
    if "3+" in low:
        return {"ok": True, "value": 3}
    if re.search(r"\bthree\s*\+\b", str(text or "").lower()):
        return {"ok": True, "value": 3}

    n = _extract_integer_value(low)
    if n is None:
        return {"ok": False, "error": "Please enter an integer color count (1 or higher)."}
    if int(n) >= 1:
        return {
            "ok": True,
            "value": int(n),
            "normalized_text": str(int(n)),
        }
    return {"ok": False, "error": "Please enter an integer color count (1 or higher)."}


def _parse_elevation(text: str) -> Dict[str, Any]:
    low = _normalize_free_text(text)
    synonyms = {
        "flat": "flat",
        "raised": "raised",
        "elevated": "raised",
        "bump": "raised",
        "bumpy": "raised",
        "slightly raised": "raised",
        "kind of raised": "raised",
        "nodule": "nodular",
        "nodular": "nodular",
        "lump": "nodular",
    }
    for token, mapped in synonyms.items():
        if re.search(rf"\b{re.escape(token)}\b", low):
            return {"ok": True, "value": mapped}
    return {"ok": False, "error": "Please answer with one of: flat, raised, or nodular."}


def _is_valid_answer(field_key: str, value: Any) -> bool:
    if field_key == "bleeding":
        return isinstance(value, bool)
    if field_key in {"itching", "border_irregularity", "pain"}:
        try:
            v = float(value)
            return 0.0 <= v <= 10.0
        except Exception:
            return False
    if field_key == "width_mm":
        try:
            return float(value) > 0.0
        except Exception:
            return False
    if field_key == "num_colors":
        return isinstance(value, int) and value >= 1
    if field_key == "elevation":
        return str(value or "").strip().lower() in {"flat", "raised", "nodular"}
    return False


def _next_question_key(answers: Dict[str, Any]) -> Optional[str]:
    for q in QUESTION_FLOW:
        key = q["key"]
        if not _is_valid_answer(key, answers.get(key)):
            return key
    return None


def _question_prompt(field_key: str) -> str:
    for q in QUESTION_FLOW:
        if q["key"] == field_key:
            return q["prompt"]
    return ""


def _validate_for_field(field_key: str, text: str) -> Dict[str, Any]:
    if field_key == "bleeding":
        yn = _parse_yes_no_strict(text)
        if yn is None:
            return {"ok": False, "error": "Please answer yes or no."}
        return {"ok": True, "value": yn}
    if field_key in {"itching", "border_irregularity", "pain"}:
        return _parse_zero_to_ten(text)
    if field_key == "width_mm":
        return _parse_width_mm(text)
    if field_key == "num_colors":
        return _parse_num_colors(text)
    if field_key == "elevation":
        return _parse_elevation(text)
    return {"ok": False, "error": "Invalid field."}


def _seed_answers_from_state(state: ConvState, metadata: Dict[str, Any]) -> None:
    answers = state.answers
    symptom_flags = (state.case_state.get("symptom_flags") or {}) if isinstance(state.case_state, dict) else {}

    if "bleeding" not in answers:
        raw_bleeding = symptom_flags.get("bleeding")
        if isinstance(raw_bleeding, bool):
            answers["bleeding"] = raw_bleeding
        elif isinstance(raw_bleeding, str):
            yn = _parse_yes_no_strict(raw_bleeding)
            if yn is not None:
                answers["bleeding"] = yn

    def _seed_numeric(target_key: str, candidates: List[Any], low: Optional[float] = None, high: Optional[float] = None) -> None:
        if target_key in answers and _is_valid_answer(target_key, answers.get(target_key)):
            return
        for cand in candidates:
            if cand in (None, ""):
                continue
            try:
                num = float(cand)
            except Exception:
                continue
            if low is not None and num < low:
                continue
            if high is not None and num > high:
                continue
            if target_key == "num_colors":
                if float(num).is_integer() and int(num) >= 1:
                    answers[target_key] = int(num)
                    return
                continue
            answers[target_key] = num
            return

    _seed_numeric("itching", [state.slots.get("itching_0_10"), symptom_flags.get("itching_0_10")], low=0, high=10)
    _seed_numeric(
        "width_mm",
        [
            state.slots.get("diameter_mm"),
            symptom_flags.get("diameter_mm"),
            metadata.get("diameter_mm"),
        ],
        low=0,
    )
    if not _is_valid_answer("border_irregularity", answers.get("border_irregularity")):
        border_candidates = [
            state.slots.get("border_irregularity_0_10"),
            symptom_flags.get("border_irregularity_0_10"),
            symptom_flags.get("border_irregularity"),
            state.slots.get("border_irregularity"),
        ]
        for cand in border_candidates:
            if cand in (None, ""):
                continue
            try:
                b = float(cand)
            except Exception:
                continue
            if 0.0 <= b <= 1.0:
                b = b * 10.0
            if 0.0 <= b <= 10.0:
                answers["border_irregularity"] = b
                break
    _seed_numeric("num_colors", [state.slots.get("number_of_colors"), symptom_flags.get("number_of_colors")], low=1)
    _seed_numeric("pain", [state.slots.get("pain_0_10"), symptom_flags.get("pain_0_10")], low=0, high=10)

    if "elevation" not in answers:
        elev = state.slots.get("elevation") or symptom_flags.get("elevation") or metadata.get("elevation")
        if elev not in (None, ""):
            parsed = _parse_elevation(str(elev))
            if parsed.get("ok"):
                answers["elevation"] = parsed.get("value")


def _sync_answers_to_legacy_slots(state: ConvState) -> None:
    answers = state.answers
    if _is_valid_answer("bleeding", answers.get("bleeding")):
        state.slots["bleeding"] = bool(answers["bleeding"])
    if _is_valid_answer("itching", answers.get("itching")):
        state.slots["itching_0_10"] = float(answers["itching"])
    if _is_valid_answer("width_mm", answers.get("width_mm")):
        state.slots["diameter_mm"] = float(answers["width_mm"])
    if _is_valid_answer("border_irregularity", answers.get("border_irregularity")):
        border_0_10 = float(answers["border_irregularity"])
        state.slots["border_irregularity_0_10"] = border_0_10
        state.slots["border_irregularity"] = border_0_10 / 10.0
    if _is_valid_answer("num_colors", answers.get("num_colors")):
        n = int(answers["num_colors"])
        state.slots["number_of_colors"] = n
        if n >= 3:
            state.slots["color_variegation"] = 1.0
        elif n == 2:
            state.slots["color_variegation"] = 0.5
        else:
            state.slots["color_variegation"] = 0.0
    if _is_valid_answer("elevation", answers.get("elevation")):
        state.slots["elevation"] = str(answers["elevation"]).lower()
    if _is_valid_answer("pain", answers.get("pain")):
        state.slots["pain_0_10"] = float(answers["pain"])


def _compute_result(answers: Dict[str, Any], state: ConvState) -> Dict[str, Any]:
    model_topk = []
    try:
        model_topk = list((state.case_state or {}).get("model_probabilities") or [])
    except Exception:
        model_topk = []

    symptom_flags = ((state.case_state or {}).get("symptom_flags") or {}) if isinstance(state.case_state, dict) else {}
    rapid_change = symptom_flags.get("rapid_change")
    if rapid_change is None:
        rapid_change = state.slots.get("rapid_change")

    combined = build_combined_risk_summary(
        answers={
            "bleeding": answers.get("bleeding"),
            "rapid_change": rapid_change,
            "width_mm": answers.get("width_mm"),
            "border_0_10": answers.get("border_irregularity"),
            "num_colors": answers.get("num_colors"),
            "elevation": answers.get("elevation"),
            "itching_0_10": answers.get("itching"),
            "pain_0_10": answers.get("pain"),
        },
        model_topk=model_topk,
        model_label_hint=(state.case_state or {}).get("current_triage"),
        extras={
            "age": (state.case_state or {}).get("age"),
            "duration_days": (state.case_state or {}).get("duration_days"),
            "familyHistory": (state.case_state or {}).get("family_history"),
        },
    )

    final = combined.get("final", {}) or {}
    clinical = combined.get("clinical", {}) or {}
    model = combined.get("model", {}) or {}

    cf_fusion = run_cf_disease_fusion(
        patient_inputs={
            "bleeding": answers.get("bleeding"),
            "rapid_change": rapid_change,
            "width_mm": answers.get("width_mm"),
            "border_irregularity": answers.get("border_irregularity"),
            "num_colors": answers.get("num_colors"),
            "elevation": answers.get("elevation"),
            "itching": answers.get("itching"),
            "pain": answers.get("pain"),
            "age": (state.case_state or {}).get("age"),
            "duration_days": (state.case_state or {}).get("duration_days"),
        },
        model_topk=model_topk,
    )

    top3 = cf_fusion.get("top3", [])
    top_breakdown = cf_fusion.get("top_disease_breakdown", {})

    intake_section = "\n".join(
        [
            "Intake summary",
            f"- Bleeding: {'yes' if answers.get('bleeding') else 'no'}",
            f"- Itching (0-10): {float(answers.get('itching')):g}",
            f"- Width (mm): {float(answers.get('width_mm')):g}",
            f"- Border irregularity (0-10): {float(answers.get('border_irregularity')):g}",
            f"- Number of colors: {int(answers.get('num_colors'))}",
            f"- Elevation: {str(answers.get('elevation')).lower()}",
            f"- Pain (0-10): {float(answers.get('pain')):g}",
        ]
    )

    prediction_section = "\n".join(
        [
            "Prediction summary",
            f"- Clinical risk points: {int(clinical.get('points', 0) or 0)} ({clinical.get('level', 'low')})",
            f"- Clinical probability: {float(clinical.get('probability_percent', 0.0) or 0.0):.1f}%",
            f"- Model risk: {model.get('level', 'low')} (score {float(model.get('score', 0.0) or 0.0):.2f})",
            f"- Final risk (conservative): {final.get('level', 'low')}",
            f"- Top disease (%): {top_breakdown.get('label', 'unknown')} (model {float(top_breakdown.get('model_percent', 0.0) or 0.0):.2f}%, expert {float(top_breakdown.get('expert_percent', 0.0) or 0.0):.2f}%, final {float(top_breakdown.get('final_percent', 0.0) or 0.0):.2f}%)",
            "- Top 3 final diseases: "
            + (
                ", ".join(
                    f"{str(item.get('label', 'unknown'))} {float(item.get('final_percent', 0.0) or 0.0):.2f}%"
                    for item in top3[:3]
                )
                if top3
                else "Unavailable"
            ),
            "This is not a diagnosis; in-person clinician review is recommended for concerning changes.",
        ]
    )

    references_and_steps_section = "\n".join(
        [
            f"Recommended next step: {final.get('recommended_next_step', '')}",
            "",
            format_references_section(),
        ]
    )

    lines = [intake_section, prediction_section, references_and_steps_section]
    return {
        "risk": final.get("level", "low"),
        "message": "\n".join(lines),
        "message_sections": [
            intake_section,
            prediction_section,
            references_and_steps_section,
        ],
        "summary": {
            "clinical_risk": clinical,
            "model_risk": model,
            "final_risk": final,
            "probability_fusion": {
                "inputs": cf_fusion.get("inputs", {}),
                "model_probs": cf_fusion.get("model_probs", {}),
                "expert_probs": cf_fusion.get("expert_probs", {}),
                "final_probs": cf_fusion.get("final_probs", {}),
                "top3": top3,
                "reasoning": cf_fusion.get("reasoning", []),
                "top_disease_breakdown": top_breakdown,
            },
        },
    }


# ---------------------------
# Main step
# ---------------------------

def step(state: ConvState, user_text: Optional[str], img, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata = _norm_meta(metadata)

    if metadata:
        if metadata.get("body_site"):
            state.slots["body_site"] = metadata.get("body_site")
        if metadata.get("patient_age") is not None:
            state.slots["patient_age"] = metadata.get("patient_age")
        if metadata.get("fitzpatrick"):
            state.slots["fitzpatrick_type"] = metadata.get("fitzpatrick")
        if metadata.get("duration_days") is not None:
            state.slots["duration_days"] = metadata.get("duration_days")

    case_context = _build_structured_case_context(state, metadata)
    _seed_answers_from_state(state, metadata)
    _sync_answers_to_legacy_slots(state)

    current_key = _next_question_key(state.answers)
    incoming_text = str(user_text or "").strip()

    if current_key and incoming_text:
        validated = _validate_for_field(current_key, incoming_text)
        if validated.get("ok"):
            state.answers[current_key] = validated.get("value")
            _sync_answers_to_legacy_slots(state)
            current_key = _next_question_key(state.answers)
            state.pending_slot = current_key
        else:
            prompt = _question_prompt(current_key)
            reply_text = f"{validated.get('error')} {prompt}".strip()
            state.pending_slot = current_key
            state.history.append({"role": "user", "parts": [{"text": incoming_text}]})
            state.history.append({"role": "model", "parts": [{"text": reply_text}]})
            return {
                "reply": reply_text,
                "message": reply_text,
                "assistant": reply_text,
                "text": reply_text,
                "follow_up_question": "None",
                "fields_needed": [current_key],
                "ready_for_assessment": False,
                "slots": state.slots,
                "answers": state.answers,
                "case_state": case_context,
                "pending_slot": current_key,
            }

    if current_key:
        prompt = _question_prompt(current_key)
        reply_text = prompt
        state.pending_slot = current_key
        if incoming_text:
            state.history.append({"role": "user", "parts": [{"text": incoming_text}]})
        state.history.append({"role": "model", "parts": [{"text": reply_text}]})
        return {
            "reply": reply_text,
            "message": reply_text,
            "assistant": reply_text,
            "text": reply_text,
            "follow_up_question": "None",
            "fields_needed": [current_key],
            "ready_for_assessment": False,
            "slots": state.slots,
            "answers": state.answers,
            "case_state": case_context,
            "pending_slot": current_key,
        }

    result_payload = _compute_result(state.answers, state)
    reply_text = result_payload["message"]
    state.pending_slot = None
    if incoming_text:
        state.history.append({"role": "user", "parts": [{"text": incoming_text}]})
    state.history.append({"role": "model", "parts": [{"text": reply_text}]})

    return {
        "reply": reply_text,
        "message": reply_text,
        "assistant": reply_text,
        "text": reply_text,
        "follow_up_question": "None",
        "fields_needed": [],
        "ready_for_assessment": True,
        "slots": state.slots,
        "answers": state.answers,
        "case_state": case_context,
        "pending_slot": None,
        "risk_level": result_payload.get("risk"),
        "message_sections": result_payload.get("message_sections", []),
        "result_summary": result_payload.get("summary", {}),
    }