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

    # Prefer single-slot questions (we also changed the rule questions accordingly)
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

    # border_irregularity mapping
    if slot == "border_irregularity":
        if low in {"smooth", "uneven", "not sure"}:
            if low == "smooth":
                state.slots["border_irregularity"] = 0.0
            elif low == "uneven":
                state.slots["border_irregularity"] = 1.0
            else:
                state.slots["border_irregularity"] = None
            state.pending_slot = None
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
        if low in {"one", "two", "three+", "3+", "not sure"}:
            if low == "one":
                state.slots["number_of_colors"] = 1.0
                state.slots["color_variegation"] = 0.0
            elif low == "two":
                state.slots["number_of_colors"] = 2.0
                state.slots["color_variegation"] = 0.5
            elif low in {"three+", "3+"}:
                state.slots["number_of_colors"] = 3.0
                state.slots["color_variegation"] = 1.0
            else:
                state.slots["number_of_colors"] = None
                state.slots["color_variegation"] = None
            state.pending_slot = None
        return

    # diameter parsing (mm)
    if slot == "diameter_mm":
        m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(mm|millimeter|millimeters)\b", low)
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

    # NEW: structured memory so we don't repeat questions forever
    slots: Dict[str, Any] = field(default_factory=dict)
    pending_slot: Optional[str] = None

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
        "required": ["body_site", "patient_age"]  # NOTE: we do NOT require diameter here anymore; ask it if missing
    }
}]


# ---------------------------
# System instruction
# ---------------------------

SYSTEM_INSTRUCTION = (
  "You are a dermatologist intake assistant in a research prototype. "
  "Gather focused clinical information and provide risk-oriented guidance—NOT a diagnosis. "
  "This tool does not provide medical diagnosis or treatment. I am an AI, not a doctor. "
  "Always recommend consulting a licensed clinician for medical decisions.\n\n"

  "CONVERSATION RULES:\n"
  "• NEVER repeat questions the user has already answered in this conversation.\n"
  "• Track what information you already have (body site, size, changes, colors, symptoms, age, skin type).\n"
  "• Build naturally on previous answers; reference what they told you.\n"
  "• Do NOT say 'I am an AI' or 'I cannot provide medical advice' more than once per conversation.\n\n"

  "QUESTION STYLE (patient-friendly):\n"
  "• Ask 1 question per turn. Offer simple choices and 'Not sure'.\n\n"

  "AUTO-MAPPING for tool calls (convert plain answers):\n"
  "• asymmetry: Yes→1, No→0, Not sure→null\n"
  "• border_irregularity: Uneven→1, Smooth→0, Not sure→null\n"
  "• color_variegation: One→0, Two→0.5, Three+→1, Not sure→null; number_of_colors: One→1, Two→2, Three+→3\n"
  "• pain_0_10: none→0, mild→2, moderate→5, severe→8\n"
  "• itching_0_10: none→0, mild→2, moderate→5, severe→8\n"
  "• evolution_speed: No/Stable→'stable', A little→'slow', A lot→'rapid'\n\n"

  "TOOL USE:\n"
  "• When you have body_site + age + change status + at least some ABCDE/symptoms, call expert_derm_consult. "
  "Otherwise ask the single most important MISSING question.\n\n"

  "STYLE:\n"
  "• Be concise and natural; avoid repetition. Use brief bullets for findings/next steps.\n"
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
    score = 0.0
    reasons = []

    # Size / evolution
    d = payload.get("diameter_mm")
    if d is not None:
        try:
            d = float(d)
        except Exception:
            d = None

    if d is not None and d >= 6:
        score += 0.35
        reasons.append("Diameter ≥ 6 mm")

    if (payload.get("evolution_speed") or "").lower() in {"rapid", "moderate"}:
        score += 0.2
        reasons.append("Recent change")

    # Symptoms
    if payload.get("bleeding") is True:
        score += 0.2
        reasons.append("Bleeding")
    if payload.get("ulceration") is True:
        score += 0.2
        reasons.append("Ulceration")
    if (payload.get("pain_0_10") or 0) >= 5:
        score += 0.05
        reasons.append("Pain ≥ 5/10")
    if (payload.get("itching_0_10") or 0) >= 5:
        score += 0.03
        reasons.append("Itching ≥ 5/10")

    # ABCDE
    if (payload.get("asymmetry") or 0) > 0.5:
        score += 0.1
        reasons.append("Asymmetry")
    if (payload.get("border_irregularity") or 0) > 0.5:
        score += 0.1
        reasons.append("Irregular border")
    if (payload.get("color_variegation") or 0) > 0.5:
        score += 0.1
        reasons.append("Variegated color")
    if (payload.get("number_of_colors") or 0) >= 3:
        score += 0.05
        reasons.append("≥3 colors")

    # Risk factors
    if (payload.get("patient_age") or 0) >= 60:
        score += 0.05
        reasons.append("Age ≥ 60")
    if payload.get("family_melanoma_history"):
        score += 0.05
        reasons.append("Family melanoma history")
    if payload.get("immunosuppressed"):
        score += 0.07
        reasons.append("Immunosuppressed")

    # (Optional) fuse classifier softmax if present
    clf = (payload.get("classifier_probs") or {})
    try:
        mel_p = float(clf.get("melanoma", 0.0))
    except Exception:
        mel_p = 0.0
    if mel_p >= 0.5:
        score += 0.25
        reasons.append(f"CNN melanoma prob {mel_p:.2f}")

    score = max(0.0, min(score, 0.98))

    out = {
        "findings": [
            {"label": "melanoma_risk", "score": round(score, 2)},
            {"label": "benign_likelihood", "score": round(1 - score, 2)},
        ],
        "rule_explanations": [
            {"rule_id": "R-ABCDE-intake", "why": ", ".join(reasons) or "No major flags"}
        ],
        "safety_flags": ["not_a_diagnosis"],
        "next_questions": [],
        "audit": {"rules_fired": ["R-ABCDE-intake"]},
    }

    # Ask only 1 question at a time (and keep it unambiguous)
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

    out["next_questions"] = needed[:1]
    return out


def _format_tool_reply(payload: Dict[str, Any]) -> str:
    risk = next((f["score"] for f in payload.get("findings", []) if f.get("label") == "melanoma_risk"), None)
    reasons = payload.get("rule_explanations", [])
    reasons_txt = ""
    if reasons:
        why = reasons[0].get("why") or ""
        reasons_txt = f"- Why: {why}\n" if why else ""
    nxt = payload.get("next_questions", []) or []
    nx_txt = ""
    if nxt:
        nx_txt = "- Next: " + " ".join(nxt) + "\n"
    risk_txt = f"- Estimated risk signal: {int(round((risk or 0)*100))}%\n" if risk is not None else ""
    return (
        "Here’s a quick intake summary (not medical advice):\n"
        f"{risk_txt}"
        f"{reasons_txt}"
        f"{nx_txt}"
        "If you notice rapid change, bleeding, ulceration, or size ≥ 6 mm, consider prompt in-person evaluation."
    )


# ---------------------------
# Main step
# ---------------------------

def step(state: ConvState, user_text: Optional[str], img, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata = _norm_meta(metadata)

    # If the last bot message was a clear question, infer which slot it's collecting,
    # then store the user's answer deterministically.
    _infer_pending_from_last_bot(state)
    _apply_pending_slot(state, user_text)

    # Parse classifier_probs if provided
    if metadata and "classifier_probs" in metadata:
        raw = metadata["classifier_probs"]
        if isinstance(raw, str):
            try:
                metadata["classifier_probs"] = json.loads(raw)
            except Exception:
                metadata["classifier_probs"] = {}

    # Merge metadata into slots so it stays remembered across turns
    # (do NOT overwrite user-entered info with empty strings)
    if metadata:
        if metadata.get("body_site"):
            state.slots["body_site"] = metadata.get("body_site")
        if metadata.get("patient_age") is not None:
            state.slots["patient_age"] = metadata.get("patient_age")
        if metadata.get("fitzpatrick"):
            state.slots["fitzpatrick_type"] = metadata.get("fitzpatrick")
        if metadata.get("duration_days") is not None:
            # keep both (your tool schema uses weeks; but rules can still reference days)
            state.slots["duration_days"] = metadata.get("duration_days")

        # If upload provided classifier probs, keep them
        if metadata.get("classifier_probs"):
            state.slots["classifier_probs"] = metadata.get("classifier_probs")

    # Build short summary text for the model (optional)
    summary_text = ""
    if metadata:
        parts = []
        if metadata.get("name"):
            parts.append(f"Patient: {metadata['name']}")
        if metadata.get("patient_age") is not None:
            parts.append(f"Age: {metadata['patient_age']}")
        if metadata.get("fitzpatrick"):
            parts.append(f"Skin type: {metadata['fitzpatrick']}")
        if metadata.get("body_site"):
            parts.append(f"Lesion location: {metadata['body_site']}")
        if metadata.get("duration_days") is not None:
            parts.append(f"Duration: {metadata['duration_days']} day(s)")
        summary_text = " • ".join(parts)

        if user_text:
            user_text = summary_text + "\n\nUser notes: " + user_text
        else:
            user_text = summary_text

    # Trim history to prevent unbounded growth
    initial_history_size = len(state.history)
    state.trim_history(max_turns=10)
    print(f"[step] History trimmed: {initial_history_size} → {len(state.history)} messages")

    chat = _get_model().start_chat(history=state.history)

    # 1) call model (guarded)
    try:
        initial = _retry_api_call(chat.send_message, user_text or "")
    except Exception as e:
        msg = str(e)
        if "429" in msg or "Resource exhausted" in msg or "rate limit" in msg.lower():
            print(f"[step] 429 Rate limit detected after retries: {msg[:200]}")
        return {
            "reply": f"Model error: {e}\n"
                     "Try setting GEMINI_MODEL to a supported name (e.g., "
                     "gemini-2.0-flash, gemini-1.5-flash-8b, or gemini-1.5-pro).",
            "message": str(e),
            "assistant": "[Error - please retry]",
            "text": str(e),
            "error": str(e),
            "error_code": "RATE_LIMIT" if ("429" in msg or "resource exhausted" in msg.lower()) else "MODEL_ERROR",
        }

    # 2) tool call handling
    reply_text = None
    tool_payload = None
    cand = (initial.candidates or [None])[0]
    parts = getattr(getattr(cand, "content", None), "parts", []) if cand else []

    for part in parts:
        fc = getattr(part, "function_call", None)
        if fc and getattr(fc, "name", None) == "expert_derm_consult":
            raw_args = getattr(fc, "args", None) or getattr(fc, "arguments", None)
            args = _coerce_call_args(raw_args)

            # IMPORTANT: enforce remembered truth (prevents repeats)
            # Also fill common fields from slots if model omitted them.
            args.update({k: v for k, v in state.slots.items() if v is not None})

            # If age/body_site were stored in slots, ensure the tool sees them
            if "patient_age" not in args and state.slots.get("patient_age") is not None:
                args["patient_age"] = state.slots["patient_age"]
            if "body_site" not in args and state.slots.get("body_site"):
                args["body_site"] = state.slots["body_site"]

            tool_payload = _run_rules(args)

            # If the tool asks the next question, set pending_slot based on it
            nxt = (tool_payload.get("next_questions") or [])
            if nxt:
                q = nxt[0].lower()
                if "bled" in q:
                    state.pending_slot = "bleeding"
                elif "crust" in q or "scab" in q:
                    state.pending_slot = "crusting"
                elif "itch" in q:
                    state.pending_slot = "itching"
                elif "pain" in q:
                    state.pending_slot = "pain"
                elif "how many colors" in q:
                    state.pending_slot = "number_of_colors"
                elif "how wide" in q or "diameter" in q:
                    state.pending_slot = "diameter_mm"

            call_id = getattr(fc, "id", None)
            try:
                followup = _retry_api_call(
                    chat.submit_tool_outputs,
                    tool_outputs=[{"call_id": call_id, "output": json.dumps(tool_payload)}],
                )
                reply_text = _resp_text(followup)
            except Exception as e:
                print(f"[step] submit_tool_outputs failed (after retries): {str(e)[:200]}")
                reply_text = _format_tool_reply(tool_payload)
            break

    # 3) fallback if no tool used
    if not reply_text:
        reply_text = _resp_text(initial)

    # 3b) never empty
    if not reply_text:
        reply_text = "I’m here. Share diameter, color changes, evolution (weeks), age, and body site."

    # 4) store history
    state.history.append({"role": "user", "parts": [{"text": user_text or ""}]})
    state.history.append({"role": "model", "parts": [{"text": reply_text}]})

    # 5) output
    out: Dict[str, Any] = {
        "reply": reply_text,
        "message": reply_text,
        "assistant": reply_text,
        "text": reply_text,
        "slots": state.slots,  # helpful for debugging
        "pending_slot": state.pending_slot,
    }
    if tool_payload:
        out["explanations"] = tool_payload.get("rule_explanations", [])
        out["findings"] = tool_payload.get("findings", [])
        out["next_questions"] = tool_payload.get("next_questions", [])
        out["safety_flags"] = tool_payload.get("safety_flags", [])
        out["audit"] = tool_payload.get("audit", {})
    return out