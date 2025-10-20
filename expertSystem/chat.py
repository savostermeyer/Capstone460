# expertSystem/chat.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import os, json
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=True)
print("[load] chat.py from:", __file__)
print("[dotenv] file:", find_dotenv(usecwd=True))
print("[env] GOOGLE_API_KEY?", bool(os.getenv("GOOGLE_API_KEY")))
print("[env] GEMINI_API_KEY?", bool(os.getenv("GEMINI_API_KEY")))

import google.generativeai as genai

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("No API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY in .env/environment.")
genai.configure(api_key=API_KEY)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest")
print(f"[Gemini] Using model: {MODEL_NAME}")


# ---- API key & model ----
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("No API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY in .env/environment.")
genai.configure(api_key=API_KEY)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest")
print(f"[Gemini] Using model: {MODEL_NAME}")

# ---- Conversation state ----
@dataclass
class ConvState:
    history: List[Dict[str, Any]] = field(default_factory=list)

# ---- Tool declaration ----
FUNCTIONS = [{
    "name": "expert_derm_consult",
    "description": "Run ABCDE + metadata rules and return findings/explanations.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "diameter_mm": {"type": "NUMBER", "description": "Lesion diameter in millimeters"},
            "asymmetry": {"type": "NUMBER", "description": "0..1"},
            "border_irregularity": {"type": "NUMBER", "description": "0..1"},
            "color_variegation": {"type": "NUMBER", "description": "0..1"},
            "evolution_weeks": {"type": "NUMBER", "description": "Weeks of noticeable change"},
            "patient_age": {"type": "NUMBER"},
            "body_site": {"type": "STRING"}
        },
        "required": ["diameter_mm", "patient_age"]
    }
}]

MODEL = genai.GenerativeModel(
    model_name=MODEL_NAME,
    tools=[{"function_declarations": FUNCTIONS}],
    system_instruction=(
        "You are a derm triage assistant embedded in a research prototype. "
        "You are NOT a doctor; do not diagnose. Use the expert_derm_consult tool "
        "whenever the user provides lesion details or asks for an assessment. "
        "Ask concise follow-up questions if critical fields are missing."
    ),
)

# ---- Rule stub (replace with your expert system) ----
def _run_rules(payload: Dict[str, Any]) -> Dict[str, Any]:
    score = 0.0
    reasons = []
    if payload.get("diameter_mm", 0) >= 6:
        score += 0.4; reasons.append("Diameter ≥ 6 mm")
    if 0 < payload.get("evolution_weeks", 0) <= 8:
        score += 0.3; reasons.append("Rapid evolution")
    if (payload.get("color_variegation") or 0) > 0.5:
        score += 0.2; reasons.append("Variegated color")
    return {
        "findings": [
            {"label": "melanoma_suspected", "score": round(min(score, 0.95), 2)},
            {"label": "nevus_atypical", "score": round(1 - min(score, 0.95), 2)},
        ],
        "rule_explanations": [{"rule_id": "R-ABCDE-demo", "why": ", ".join(reasons) or "No major flags"}],
        "safety_flags": ["not_a_diagnosis"],
        "next_questions": ["Has it bled or crusted recently?"],
        "audit": {"rules_fired": ["R-ABCDE-demo"]}
    }

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
def step(state: ConvState, user_text: Optional[str], img) -> Dict[str, Any]:
    chat = MODEL.start_chat(history=state.history)

    # 1) call model (guarded)
    try:
        initial = chat.send_message(user_text or "")
    except Exception as e:
        msg = (
            f"Model error: {e}\n"
            "Try setting GEMINI_MODEL to a supported name (e.g., "
            "gemini-2.0-flash, gemini-1.5-flash-8b, or gemini-1.5-pro-latest)."
        )
        return {"reply": msg, "message": msg, "assistant": msg, "text": msg}

    # 2) tool call handling
    reply_text = None
    tool_payload = None
    cand = (initial.candidates or [None])[0]
    parts = getattr(getattr(cand, "content", None), "parts", []) if cand else []
    for part in parts:
        if getattr(part, "function_call", None):
            call = part.function_call
            if call.name == "expert_derm_consult":
                args = json.loads(call.args or "{}")
                tool_payload = _run_rules(args)
                followup = chat.send_message([
                    {"tool_call": call},
                    {"tool_result": {"name": call.name, "content": json.dumps(tool_payload)}}
                ])
                reply_text = _resp_text(followup)
                break

    # 3) fallback to model text if no tool used
    if not reply_text:
        reply_text = _resp_text(initial)

    # 3b) absolute fallback, never empty
    if not reply_text:
        reply_text = "I’m here. Share diameter, color changes, evolution (weeks), age, and body site."

    # 4) keep compact history
    state.history.append({"role": "user", "parts": [user_text or ""]})
    state.history.append({"role": "model", "parts": [reply_text]})

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
