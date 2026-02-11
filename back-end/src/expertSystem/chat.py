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
import time
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
    
    def trim_history(self, max_turns: int = 10):
        """
        Keep only the most recent N turns to prevent unbounded token growth.
        Each 'turn' is typically 2 messages (user + model reply).
        """
        max_messages = max_turns * 2
        if len(self.history) > max_messages:
            # Keep only the last N messages; discard old context
            self.history = self.history[-max_messages:]

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
  "This tool does not provide medical diagnosis or treatment. I am an AI, not a doctor. "
  "Always recommend consulting a licensed clinician for medical decisions.\n\n"

  "CONVERSATION RULES:\n"
  "• NEVER repeat questions the user has already answered in this conversation.\n"
  "• Track what information you already have (body site, size, changes, colors, symptoms, age, skin type).\n"
  "• Build naturally on previous answers; reference what they told you.\n"
  "• Do NOT say 'I am an AI' or 'I cannot provide medical advice' more than once per conversation.\n\n"

  "QUESTION STYLE (patient-friendly):\n"
  "• Avoid numbers/scales unless the user already gave them. Use plain language + examples.\n"
  "• Ask 1 question per turn. Offer simple choices and 'Not sure'.\n"
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
  "• If unsure, leave the field null and ask only ONE key follow-up next turn.\n\n"

  "TOOL USE:\n"
  "• When you have body_site + diameter_mm + change status + at least some ABCDE/symptoms, call expert_derm_consult. "
  "Otherwise ask the single most important MISSING question.\n\n"

  "STYLE:\n"
  "• Be concise and natural; avoid repetition. Use brief bullets for findings/next steps. "
  "• If high-risk features (rapid change, bleeding, ulceration, diameter ≥ 6 mm, clearly uneven edges/colors), "
  "recommend prompt in-person evaluation.\n"
)

# Lazy model init with fallbacks (no network on import)
# PRIORITY: Use preferred model first (from .env), then try alternatives if available
PREFERRED = MODEL_NAME
CANDIDATES = [PREFERRED, "gemini-1.5-flash-8b", "gemini-1.5-flash", "gemini-1.5-pro"]

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
# this is where the medical logic lives
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
        needed.append("Has it been changing? (stable, slow, moderate, or rapid)")
    if payload.get("bleeding") is None and not needed:  # Only ask if we don't have critical info
        needed.append("Has it bled or crusted?")
    if payload.get("number_of_colors") is None and not needed:  # Only ask if we don't have critical info
        needed.append("Roughly how many colors do you see (1, 2, or 3+)?")
    
    out["next_questions"] = needed[:1]  # Ask only 1 question at a time (was 3)
    
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


# ---- API call retry helper ----
def _retry_api_call(fn, *args, max_retries: int = 4, base_delay: float = 1.0):
    """
    Call `fn(*args)` with an exponential backoff retry for transient rate-limit/resource errors.
    Retries when the exception message contains indicators of rate limiting (429 / Resource exhausted).
    On final failure the exception is propagated.
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
                # Non-rate errors should not be retried
                raise
            if attempt == max_retries:
                # give up and re-raise the last exception
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(f"[retry] attempt {attempt} failed: {msg[:180]} -- sleeping {delay}s")
            time.sleep(delay)
    # if somehow we exit loop
    raise last_err

# ---- Main step ----
def step(state: ConvState, user_text: Optional[str], img, metadata: Optional[Dict[str,Any]]=None) -> Dict[str, Any]:
    
    # --- NEW: parse classifier_probs (coming later from CNN team) ---
    # Accept JSON string or dict. If it's invalid, ignore safely.
    if metadata and "classifier_probs" in metadata:
        raw = metadata["classifier_probs"]
        if isinstance(raw, str):
            try:
                metadata["classifier_probs"] = json.loads(raw)
            except Exception:
                metadata["classifier_probs"] = {}  # fail-safe

    # Merge metadata into AI input (provided from upload.html)
    summary_text = ""

    if metadata:
        parts = []
        
        if metadata.get("name"):
            parts.append(f"Patient: {metadata['name']}")
            
        if metadata.get("age"):
            parts.append(f"Age: {metadata['age']}")
            
        if metadata.get("fitzpatrick"):
            parts.append(f"Skin type: {metadata['fitzpatrick']}")
            
        if metadata.get("body_site"):
            parts.append(f"Lesion location: {metadata['body_site']}")
            
        if metadata.get("duration_days"):
            parts.append(f"Duration: {metadata['duration_days']} day(s)")
            
        if metadata.get("symptom"):
            parts.append(f"Main symptom: {metadata['symptom']}")
            
        summary_text = " • ".join(parts)
        
        if user_text:
            user_text = summary_text + "\n\nUser notes: " + user_text
        else:
            user_text = summary_text
    
    # Build a summary of what we already know from conversation history
    # This helps the model avoid repeating questions
    context_summary = ""
    if len(state.history) > 0:
        # Extract key data points from conversation
        known_info = []
        conversation_text = " ".join([msg.get("parts", [{}])[0].get("text", "") for msg in state.history])
        
        # Check for previously mentioned information
        if any(word in conversation_text.lower() for word in ["forearm", "arm", "leg", "ankle", "shin", "calf", "back", "chest", "face", "palm"]):
            known_info.append("(We know the body location)")
        if any(word in conversation_text.lower() for word in ["mm", "millimeter", "millimeters", "pencil", "eraser"]):
            known_info.append("(We know the diameter)")
        if any(word in conversation_text.lower() for word in ["changing", "changed", "growing", "stable"]):
            known_info.append("(We know about changes)")
        if any(word in conversation_text.lower() for word in ["color", "colors", "brown", "red", "black"]):
            known_info.append("(We know about colors)")
            
        if known_info:
            context_summary = f"\n\n[Context: {' '.join(known_info)}]"
    
    # start the model chat
    # BEFORE: Trim old history to prevent unbounded token growth (issue at diagnostic stage)
    initial_history_size = len(state.history)
    state.trim_history(max_turns=10)  # Keep ~20 messages (10 turns)
    trimmed_history_size = len(state.history)
    print(f"[step] History trimmed: {initial_history_size} → {trimmed_history_size} messages")
    
    # Append context summary to current message to help model track state
    if context_summary and user_text:
        user_text = user_text + context_summary
    
    chat = _get_model().start_chat(history=state.history)
    
    

    # 1) call model (guarded)
    try:
        initial = _retry_api_call(chat.send_message, user_text or "")
    except Exception as e:
        msg = str(e)
        # Log 429 errors specifically for debugging
        if "429" in msg or "Resource exhausted" in msg or "rate limit" in msg.lower():
            print(f"[step] 429 Rate limit detected after retries: {msg[:200]}")
        return {
            "reply": f"Model error: {e}\n"
                     "Try setting GEMINI_MODEL to a supported name (e.g., "
                     "gemini-2.0-flash, gemini-1.5-flash-8b, or gemini-1.5-pro).",
            "message": str(e),
            "assistant": "[Error - please retry]",
            "text": str(e),
            "error": str(e)
        }

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
                # Preferred path (new SDKs) with retry for transient rate limits
                followup = _retry_api_call(
                    chat.submit_tool_outputs,
                    tool_outputs=[{"call_id": call_id, "output": json.dumps(tool_payload)}],
                )
                reply_text = _resp_text(followup)
            except Exception as e:
                print(f"[step] submit_tool_outputs failed (after retries): {str(e)[:200]}")
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
    # Store user input in history (extract original message without context_summary)
    user_msg_for_history = user_text
    if context_summary and user_msg_for_history and context_summary in user_msg_for_history:
        user_msg_for_history = user_msg_for_history.replace(context_summary, "").strip()
    
    state.history.append({"role": "user", "parts": [{"text": user_msg_for_history or ""}]})
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
