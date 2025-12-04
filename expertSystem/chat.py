# File: expertSystem/chat.py
# Role: Gemini-powered dermatology intake assistant (NOT a diagnosis system).
#       Holds persona/system prompt, tool (function) schema, SDK-safe tool-calling,
#       and a small rule engine that produces a risk-oriented summary.

# Exports:
# - ConvState → conversation history container for Gemini chat sessions
# - step(state, user_text, img) → dict response used by /chat

# Linked to:
# - Called by expertSystem/app.py’s POST /chat endpoint.

# Key behaviors:
# - Patient-friendly questions (ABCDE, symptoms, change); always disclaimers.
# - Tool name: 'expert_derm_consult' (JSON Schema types are lowercase).
# - Rule engine (_run_rules): combines size/evolution/symptoms/ABCDE/risk factors
#   into a simple “risk signal” + suggested next questions.
# - SDK-robustness: accepts function-call args as strings or mappings, uses
#   submit_tool_outputs when available, otherwise formats a direct reply.
# - Stores history parts as {"text": "..."} to match Gemini SDK expectations.
# """






from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import os, json
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=True)
print("[load] chat.py from:", __file__)
print("[dotenv] file:", find_dotenv(usecwd=True))
print("[env] GOOGLE_API_KEY?", bool(os.getenv("GOOGLE_API_KEY")))

import google.generativeai as genai
from collections.abc import Mapping


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


# ---- API key & model ----
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("No API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY in .env/environment.")
genai.configure(api_key=API_KEY)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
print(f"[Gemini] Using model: {MODEL_NAME}")

# ---- Conversation state ----
@dataclass
class ConvState:
    history: List[Dict[str, Any]] = field(default_factory=list)

# ---- Tool declaration (use lowercase JSON Schema types) ----
FUNCTIONS = [{
    "name": "expert_derm_consult",
    "description": "Combine history/ABCDE and optional classifier probs into a risk-oriented triage summary.",
    "parameters": {
        "type": "object",
        "properties": {
            # Core lesion info
            "body_site": {"type": "string", "description": "e.g., left forearm"},
            "diameter_mm": {"type": "number", "description": "Largest diameter in millimeters"},
            "duration_weeks": {"type": "number", "description": "How long the lesion has been noticeable"},
            "evolution_weeks": {"type": "number", "description": "Weeks of noticeable change"},
            "evolution_speed": {"type": "string", "description": "stable|slow|moderate|rapid"},
            "elevation": {"type": "string", "description": "flat|raised|nodular"},
            # Symptoms
            "itching_0_10": {"type": "number"},
            "pain_0_10": {"type": "number"},
            "bleeding": {"type": "boolean"},
            "crusting": {"type": "boolean"},
            "ulceration": {"type": "boolean"},
            # ABCDE numeric features
            "asymmetry": {"type": "number", "description": "0..1"},
            "border_irregularity": {"type": "number", "description": "0..1"},
            "color_variegation": {"type": "number", "description": "0..1"},
            "number_of_colors": {"type": "number"},
            # Patient/risk factors
            "patient_age": {"type": "number"},
            "fitzpatrick_type": {"type": "string", "description": "I|II|III|IV|V|VI"},
            "sunburn_history": {"type": "string", "description": "none|some|frequent"},
            "tanning_bed_use": {"type": "boolean"},
            "sunscreen_use": {"type": "string", "description": "never|sometimes|regular"},
            "personal_melanoma_history": {"type": "boolean"},
            "family_melanoma_history": {"type": "boolean"},
            "immunosuppressed": {"type": "boolean"},
            "prior_biopsies_here": {"type": "boolean"},
            # Optional classifier fusion (explicit keys)
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
        "required": ["diameter_mm", "patient_age", "body_site"]
    }
}]

# ---- System instruction (kept content same as your original prompt) ----
SYSTEM_INSTRUCTION = (
  "You are a dermatologist intake assistant in a research prototype. "
  "Gather focused clinical information and provide risk-oriented guidance—NOT a diagnosis. "
  "Always say you are not a doctor and this is not medical advice.\n\n"

  "QUESTION STYLE (patient-friendly):\n"
  "• Avoid numbers/scales unless the user already gave them. Use plain language + examples.\n"
  "• Ask 1–2 questions per turn. Offer simple choices and 'Not sure'.\n"
  "• Examples:\n"
  "  - Asymmetry → 'Do both halves look the same if you imagine folding it?' (Yes / No / Not sure)\n"
  "  - Border → 'Edges smooth like a circle/oval, or uneven/jagged?' (Smooth / Uneven / Not sure)\n"
  "  - Color → 'One color, two colors, or three or more?' (One / Two / Three+ / Not sure)\n"
  "  - Size → 'With a ruler/coin: about how wide at the largest point (mm)? A pencil eraser is ~6 mm.'\n"
  "  - Symptoms → 'Has it itched?' (none/mild/moderate/severe); 'Is it painful?'; 'Has it bled or formed a crust?'\n"
  "  - Change → 'Has it been changing recently?' (No / A little / A lot / Not sure)\n\n"

  "AUTO-MAPPING for tool calls (convert plain answers):\n"
  "• asymmetry: Yes→1, No→0, Not sure→null\n"
  "• border_irregularity: Uneven→1, Smooth→0, Not sure→null\n"
  "• color_variegation: One→0, Two→0.5, Three+→1, Not sure→null; number_of_colors: One→1, Two→2, Three+→3\n"
  "• pain_0_10: none→0, mild→2, moderate→5, severe→8 (approximate verbal scales)\n"
  "• itching_0_10: none→0, mild→2, moderate→5, severe→8\n"
  "• evolution_speed: No/Stable→'stable', A little→'slow', A lot→'rapid'\n"
  "• If unsure, leave the field null and ask at most one key follow-up next turn.\n\n"

  "TOOL USE:\n"
  "• When you have body_site + diameter_mm + change status + at least some ABCDE/symptoms, call expert_derm_consult. "
  "Otherwise ask the single most important missing question.\n\n"

  "STYLE:\n"
  "• Be concise and supportive; use brief bullets for findings/next steps. "
  "• If high-risk features (rapid change, bleeding, ulceration, diameter ≥ 6 mm, clearly uneven edges/colors), "
  "If given diagnose or prescribe treatment, give a warning that you are an AI and not a replacement for a medical professional. "
  "recommend prompt in-person evaluation.\n"
)

# Lazy model init with fallbacks (no network on import)
PREFERRED = MODEL_NAME
CANDIDATES = [PREFERRED, "gemini-1.5-flash-8b", "gemini-1.5-pro"]

MODEL = None
MODEL_NAME = PREFERRED  # keep name updated once we pick one

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
            m.start_chat()  # touch only; no generate call here
            MODEL, MODEL_NAME = m, name
            print(f"[Gemini] Using model: {name}")
            return MODEL
        except Exception as e:
            print(f"[Gemini] '{name}' failed at init: {e}")
            last_err = e
            continue
    raise RuntimeError(f"No working Gemini model from {CANDIDATES}. Last error: {last_err}")

# ---- Rule stub (replace with your expert system) ----
def _run_rules(payload: Dict[str, Any]) -> Dict[str, Any]:
    score = 0.0
    reasons = []

    # Size / evolution
    d = payload.get("diameter_mm") or 0
    if d >= 6:
        score += 0.35
        reasons.append("Diameter ≥ 6 mm")
    if (payload.get("evolution_speed") or "").lower() in {"rapid", "moderate"}:
        score += 0.2
        reasons.append("Recent change")

    # Symptoms
    if payload.get("bleeding"):
        score += 0.2
        reasons.append("Bleeding")
    if payload.get("ulceration"):
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
    mel_p = float(clf.get("melanoma", 0.0))
    if mel_p >= 0.5:
        score += 0.25
        reasons.append(f"CNN melanoma prob {mel_p:.2f}")

    # cap and mirror to low-risk class
    score = max(0.0, min(score, 0.98))
    out = {
        "findings": [
            {"label": "melanoma_risk", "score": round(score, 2)},
            {"label": "benign_likelihood", "score": round(1 - score, 2)},
        ],
        "rule_explanations": [{"rule_id": "R-ABCDE-intake", "why": ", ".join(reasons) or "No major flags"}],
        "safety_flags": ["not_a_diagnosis"],
        "next_questions": [],
        "audit": {"rules_fired": ["R-ABCDE-intake"]}
    }

    # Suggest the next 1–3 key questions (keep it short)
    needed = []
    if payload.get("diameter_mm") is None:
        needed.append("What is the largest diameter in millimeters?")
    if payload.get("evolution_speed") is None:
        needed.append("Has it been changing? stable, slow, moderate, or rapid?")
    if payload.get("bleeding") is None:
        needed.append("Has it bled or crusted?")
    if payload.get("number_of_colors") is None:
        needed.append("Roughly how many colors do you see (1,2,≥3)?")
    out["next_questions"] = needed[:3]

    return out

def _format_tool_reply(payload: Dict[str, Any]) -> str:
    # Build a concise reply if we can't round-trip through the model
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

# ---- Robust text extractor ----
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

# ---- Main step ----
def step(state: ConvState, user_text: Optional[str], img, metadata: Optional[Dict[str,Any]]=None) -> Dict[str, Any]:
    
    # Merge metadata into AI input(provided from upload.html)
    
    summary_text =""
    if metadata:
        parts = []
        
        if metadata.get("name"):
            parts.append(f"Patient: {metadata['name']}")
        if metadata.get("age"):
            parts.append(f"Age: {metadata['age']}")
        if metadata.get("fitzpatrick"):
            parts.append(f"Skin type: {metadata['fitzpatrick']}")
        if metadata.get("location"):
            parts.append(f"Lesion location: {metadata['location']}")
        if metadata.get("duration_days"):
            parts.append(f"Duration: {metadata['duration_days']} day(s)")
        if metadata.get("symptom"):
            parts.append(f"Main symptom: {metadata['symptom']}")
            
        summary_text = " • ".join(parts)
        
        if user_text:
            user_text = summary_text + "\n\nUser notes: " + user_text
        else:
            user_text = summary_text
            
    
    # start the model char
    chat = _get_model().start_chat(history=state.history)
    
    

    # 1) call model (guarded)
    try:
        initial = chat.send_message(user_text or "")
    except Exception as e:
        msg = (
            f"Model error: {e}\n"
            "Try setting GEMINI_MODEL to a supported name (e.g., "
            "gemini-2.0-flash, gemini-1.5-flash-8b, or gemini-1.5-pro)."
        )
        return {"reply": msg, "message": msg, "assistant": msg, "text": msg}

    # 2) tool call handling (submit tool outputs back to the model)
    reply_text = None
    tool_payload = None
    cand = (initial.candidates or [None])[0]
    parts = getattr(getattr(cand, "content", None), "parts", []) if cand else []
    for part in parts:
        fc = getattr(part, "function_call", None)
        if fc and getattr(fc, "name", None) == "expert_derm_consult":
            raw_args = getattr(fc, "args", None) or getattr(fc, "arguments", None)
            args = _coerce_call_args(raw_args)
            tool_payload = _run_rules(args)
            call_id = getattr(fc, "id", None)
            try:
                # Preferred path (new SDKs)
                followup = chat.submit_tool_outputs(tool_outputs=[{
                    "call_id": call_id,
                    "output": json.dumps(tool_payload)
                }])
                reply_text = _resp_text(followup)
            except Exception:
                # Robust fallback: reply directly from tool payload (no schema gymnastics)
                reply_text = _format_tool_reply(tool_payload)
            break

    # 3) fallback to model text if no tool used
    if not reply_text:
        reply_text = _resp_text(initial)

    # 3b) absolute fallback, never empty
    if not reply_text:
        reply_text = "I’m here. Share diameter, color changes, evolution (weeks), age, and body site."

    # 4) keep compact history (Gemini expects parts with 'text' objects)
    state.history.append({"role": "user", "parts": [{"text": user_text or ""}]})
    state.history.append({"role": "model", "parts": [{"text": reply_text}]})

    # 5) return multiple synonymous fields for frontend compatibility
    out: Dict[str, Any] = {
        "reply": reply_text,
        "message": reply_text,
        "assistant": reply_text,
        "text": reply_text,
    }
    if tool_payload:
        out["results"] = tool_payload.get("results", [])
        out["explanations"] = tool_payload.get("rule_explanations", [])
        out["findings"] = tool_payload.get("findings", [])
        out["next_questions"] = tool_payload.get("next_questions", [])
        out["safety_flags"] = tool_payload.get("safety_flags", [])
        out["audit"] = tool_payload.get("audit", {})
    return out
