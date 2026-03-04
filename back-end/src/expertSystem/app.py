# File: expertSystem/app.py
# Role: Flask web server for the demo + APIs.

# Linked to:
# - expertSystem/chat.py → imports ConvState and step(...) to run the intake chat at POST /chat
# - src/query.py        → imports search(...) for image kNN at POST /query (optional)
# - expertSystem/indexdemo.html → served at GET / as the minimal demo UI
# - data/HAM10000_images_part_1|2 → served via GET /ham/<image_id>.jpg

# Endpoints:
# - GET  /                    → indexdemo.html
# - POST /chat                → runs the Gemini intake assistant (chat only)
# - POST /query               → (optional) image similarity search using FAISS (if index exists)
# - GET  /ham/<image_id>.jpg  → serve dataset images
# - GET  /<path>              → serve other static front-end files (if present)

# Env:
# - GEMINI_API_KEY (required), GEMINI_MODEL (default: gemini-2.0-flash)
# - PORT (optional; defaults to 3720)

# Notes:
# - Keeps an in-memory session dict for chat state during dev.
# - Adds absolute image URLs in responses for convenience.


import os
import sys
import json
from pathlib import Path
from keras_predictor import KerasResNetPredictor
from dotenv import load_dotenv

# --- Static path to .env in project root ---
# Resolves from: expertSystem/app.py -> back-end/src/ -> back-end/ -> Capstone/
APP_DIR = Path(__file__).resolve().parent
BACK_END_SRC = APP_DIR.parent
BACK_END = BACK_END_SRC.parent
PROJECT_ROOT = BACK_END.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load environment variables FIRST from explicit path, before any imports that need them
if ENV_FILE.exists():
    load_dotenv(str(ENV_FILE))
    print(f"[env] Loaded from {ENV_FILE}")
else:
    print(f"[env] WARNING: .env not found at {ENV_FILE}, using system env")
    load_dotenv()

from typing import Dict
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image, ImageOps
from expertSystem.chat import ConvState, step as chat_step
import time
from collections import deque

# ---------- Chatbot wiring ----------

# hold per-session state in memory for dev; switch to a store later
_SESS: Dict[str, ConvState] = {}
_SESSION_CASE_STORE: Dict[str, dict] = {}
_LAST_REQUEST: Dict[str, float] = {}
# Keep recent request timestamps per session for sliding-window rate limiting
_REQ_TIMES: Dict[str, deque] = {}

# Rate limit settings (configurable via env)
# Minimum seconds between consecutive requests from same session (debounce)
CHAT_MIN_INTERVAL = float(os.getenv("CHAT_MIN_INTERVAL", "1.0"))
# Maximum allowed requests per minute per session
CHAT_MAX_PER_MINUTE = int(os.getenv("CHAT_MAX_PER_MINUTE", "20"))
# --- Project roots & import path setup ---
ROOT = BACK_END
SRC_DIR = os.path.join(ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

# Import after sys.path is prepared
from query import search  # noqa: E402
from expert_pipeline import run_expert_pipeline  # noqa: E402
from pipeline_stages import (  # noqa: E402
    CONTRACT_VERSION,
    MODEL_OUTPUT_SCHEMA,
    EXPERT_OUTPUT_SCHEMA,
    FUSED_OUTPUT_SCHEMA,
    EVIDENCE_LOOKUP_SCHEMA,
    run_model_stage,
    run_expert_stage,
    run_fusion_stage,
    run_evidence_lookup,
)
from expertSystem.clinical_risk import build_combined_risk_summary  # noqa: E402
from expertSystem.medical_references_cache import (  # noqa: E402
    get_cached_references,
    refresh_references,
)
from expertSystem.cf_probability_integration import run_cf_disease_fusion  # noqa: E402

FRONT_DIR = os.path.join(ROOT, "front-end")
DATA_DIR = os.path.join(ROOT, "data")
EXP_DIR = os.path.join(ROOT, "expertSystem")


app = Flask(__name__, static_folder=FRONT_DIR, static_url_path="")

from flask_cors import CORS

CORS(app)

CHAT_DISCLAIMER = "This tool does not provide a medical diagnosis."
CHAT_EXPOSE_INTERNAL = str(os.getenv("CHAT_EXPOSE_INTERNAL", "false")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# --- MongoDB client for reports storage (optional) ---
mongo_client = None
reports_coll = None
MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
if MONGO_URI:
    try:
        from pymongo import MongoClient

        mongo_client = MongoClient(MONGO_URI)
        reports_coll = mongo_client.get_database("skin-images").get_collection(
            "reports"
        )
        print("[mongo] reports collection ready")
    except Exception as e:
        print("[mongo] could not connect:", e)


def _strip_exif(img: Image.Image) -> Image.Image:
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    out = Image.new(img.mode, img.size)
    out.putdata(list(img.getdata()))
    
    
    return out


@app.get("/")
def index():
    return send_from_directory(FRONT_DIR, "index.html")


#   to run demo code:
#   return send_from_directory(EXP_DIR, "indexdemo.html")  # <- fixed indent


@app.get("/ham/<image_id>.jpg")
def ham(image_id: str):
    for sub in ("HAM10000_images_part_1", "HAM10000_images_part_2"):
        folder = os.path.join(DATA_DIR, sub)
        path = os.path.join(folder, f"{image_id}.jpg")
        if os.path.exists(path):
            return send_from_directory(folder, f"{image_id}.jpg")
    return jsonify(error=f"{image_id} not found"), 404


@app.post("/query")
def do_query():
    if "image" not in request.files:
        return jsonify(error="image file required (field name: 'image')"), 400
    f = request.files["image"]
    if not f.filename:
        return jsonify(error="empty filename"), 400
    try:
        img = Image.open(f.stream).convert("RGB")
        img = _strip_exif(img)
    except Exception as e:
        return jsonify(error=f"failed to read image: {e}"), 400

    out = search(img, dict(request.form.items()), top_k=5)

    # Add relative + absolute URLs to each result (handy for external front-ends)
    base = request.host_url.rstrip("/")  # e.g., http://127.0.0.1:5000
    for r in out.get("results", []) or []:
        rel = f"/ham/{r['image_id']}.jpg"
        r["url"] = rel
        r["abs_url"] = f"{base}{rel}"

    return jsonify(out)

def _analysis_to_chat_message(pipeline_result: dict) -> str:
    seed = pipeline_result.get("explanation_seed", {}) or {}
    topk = pipeline_result.get("ml", {}).get("topK", []) or []
    reasoning = pipeline_result.get("reasoning", {}) or {}

    primary = (seed.get("triage") or seed.get("primary_result") or "unknown").replace("_", " ")
    risk_level = str(seed.get("risk_level") or "unknown")
    disclaimer = seed.get(
        "disclaimer",
        "This is not medical advice. This is a preliminary AI-assisted analysis."
    )

    preds = ", ".join([f"{p['label']}: {p['prob']:.4f}" for p in topk]) or "None"
    triggered = reasoning.get("triggered_facts", []) or seed.get("triggered_facts", []) or []
    triggered_txt = ", ".join(
        f"{x.get('fact')} ({x.get('cf')})" for x in triggered[:6]
    ) or "None"

    return (
        f"{disclaimer}\n"
        f"Current triage signal: {primary} (risk: {risk_level}).\n"
        f"Model probabilities: {preds}.\n"
        f"Triggered facts: {triggered_txt}.\n\n"
        "Interview mode instructions:\n"
        "- Ask exactly ONE focused follow-up question at a time.\n"
        "- Keep responses short and clinical.\n"
        "- Do not invent facts.\n"
        "- Provide a brief provisional impression only after enough answers are collected or if user asks for assessment."
    )


def _risk_label_to_api(level: str) -> str:
    low = str(level or "").strip().lower()
    if low == "high":
        return "high_risk"
    if low == "moderate":
        return "moderate_risk"
    return "low_risk"


def _parse_json_or_default(value: object, default: object) -> object:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _build_chat_internal_payload(metadata: dict, model_out: dict) -> dict:
    model_topk = _parse_json_or_default(metadata.get("model_topk"), [])
    facts = _parse_json_or_default(metadata.get("facts"), {})

    triggered_facts = []
    if isinstance(facts, dict):
        for key, value in facts.items():
            try:
                numeric = float(value)
            except Exception:
                continue
            if abs(numeric) < 1e-9:
                continue
            triggered_facts.append(
                {
                    "fact": key,
                    "cf": round(numeric, 4),
                    "direction": "support" if numeric >= 0 else "oppose",
                }
            )

    session_case_state = metadata.get("session_case_state") if isinstance(metadata, dict) else {}

    return {
        "triage": metadata.get("primary_result") or metadata.get("triage") or "unknown",
        "model_probabilities": model_topk,
        "triggered_facts": triggered_facts,
        "pending_slot": model_out.get("pending_slot"),
        "awaiting_more_info_choice": bool(model_out.get("awaiting_more_info_choice", False)),
        "case_context": session_case_state or {},
    }


def _build_chat_display_payload(model_out: dict) -> dict:
    message = str(
        model_out.get("message")
        or model_out.get("reply")
        or model_out.get("assistant")
        or model_out.get("text")
        or ""
    ).strip()
    follow_up_question = str(model_out.get("follow_up_question") or "None").strip()
    fields_needed = model_out.get("fields_needed", [])
    ready_for_assessment = bool(model_out.get("ready_for_assessment", False))

    return {
        "message": message,
        "message_sections": model_out.get("message_sections", []),
        "follow_up_question": follow_up_question,
        "fields_needed": fields_needed,
        "ready_for_assessment": ready_for_assessment,
        "awaiting_more_info_choice": bool(model_out.get("awaiting_more_info_choice", False)),
        "disclaimer": CHAT_DISCLAIMER,
    }


def _merge_intake_into_session_store(sid: str, incoming: dict) -> dict:
    current = dict(_SESSION_CASE_STORE.get(sid) or {})

    for key, value in (incoming or {}).items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            merged = dict(current.get(key) or {})
            for nested_key, nested_value in value.items():
                if nested_value in (None, "", [], {}):
                    continue
                merged[nested_key] = nested_value
            current[key] = merged
        else:
            current[key] = value

    _SESSION_CASE_STORE[sid] = current
    return current


def _build_llm_case_state(sid: str) -> dict:
    return dict(_SESSION_CASE_STORE.get(sid) or {})

@app.post("/analyze_skin")
def analyze_skin():
    """
    Endpoint: POST /analyze_skin
    Required fields:
    - image (file): skin lesion image
    - age (int, optional)
    - sex_at_birth (str, optional): M/F/other
    - location (str, optional): lesion location
    - duration_days (int, optional)
    - rapid_change (bool, optional)
    - bleeding (bool, optional)
    - itching (bool, optional)
    - pain (bool, optional)

    Returns JSON with:
    - top_predictions: [{'label': 'mel', 'confidence': 0.62}, ...]
    - risk_score: 'high_risk' | 'moderate_risk' | 'low_risk'
    - explanation_summary: structured data for Gemini
    - follow_up_questions: array of suggested questions (from Gemini chat)
    """
    try:
        # Get image
        if "image" not in request.files:
            return jsonify(error="image file required (field name: 'image')"), 400
        f = request.files["image"]
        if not f.filename:
            return jsonify(error="empty filename"), 400

        image_bytes = f.read()

        # Extract patient intake fields
        upload_fields = {
            "age": request.form.get("age"),
            "sex_at_birth": request.form.get("sex_at_birth"),
            "location": request.form.get("location"),
            "duration_days": request.form.get("duration_days"),
        }
        

        # Extract chat/symptom flags
        chat_flags = {
            "rapid_change": request.form.get("rapid_change"),
            "bleeding": request.form.get("bleeding"),
            "itching": request.form.get("itching"),
            "pain": request.form.get("pain"),
        }

        # Run the expert pipeline
        pipeline_result = run_expert_pipeline(
            image_bytes=image_bytes,
            upload_fields=upload_fields,
            chat_flags=chat_flags,
            predictor=KerasResNetPredictor(),  
        )
        # ---- Seed chatbot with analysis explanation ----
        sid = request.args.get("sid") or request.form.get("sid") or "demo"
        st = _SESS.get(sid) or ConvState()

        # Extract and structure intermediate values before persisting state
        topk = pipeline_result["ml"]["topK"]
        reasoning = pipeline_result["reasoning"]
        triage = reasoning.get("triage", reasoning.get("primary_result", "unknown"))

        chat_message = _analysis_to_chat_message(pipeline_result)

        # Persist structured case state so subsequent chat turns have full context.
        st.case_state.update(
            {
                "age": pipeline_result.get("intake", {}).get("age"),
                "skin_type": request.form.get("skinType"),
                "lesion_location": pipeline_result.get("intake", {}).get("location")
                or request.form.get("location"),
                "duration_days": pipeline_result.get("intake", {}).get("duration_days"),
                "family_history": request.form.get("familyHistory"),
                "symptom_flags": {
                    "rapid_change": pipeline_result.get("intake", {}).get("rapid_change"),
                    "bleeding": pipeline_result.get("intake", {}).get("bleeding"),
                    "itching": pipeline_result.get("intake", {}).get("itching"),
                    "pain": pipeline_result.get("intake", {}).get("pain"),
                },
                "model_probabilities": topk,
                "current_triage": triage,
            }
        )
        _merge_intake_into_session_store(
            sid,
            {
                "age": pipeline_result.get("intake", {}).get("age"),
                "skin_type": request.form.get("skinType"),
                "lesion_location": pipeline_result.get("intake", {}).get("location")
                or request.form.get("location"),
                "duration_days": pipeline_result.get("intake", {}).get("duration_days"),
                "family_history": request.form.get("familyHistory"),
                "symptom_flags": {
                    "rapid_change": pipeline_result.get("intake", {}).get("rapid_change"),
                    "bleeding": pipeline_result.get("intake", {}).get("bleeding"),
                    "itching": pipeline_result.get("intake", {}).get("itching"),
                    "pain": pipeline_result.get("intake", {}).get("pain"),
                },
                "model_probabilities": topk,
                "current_triage": triage,
                "expert_facts": reasoning.get("facts", {}),
            },
        )

        # Also seed known slots from intake when present.
        if pipeline_result.get("intake", {}).get("location"):
            st.slots["body_site"] = pipeline_result.get("intake", {}).get("location")
        if pipeline_result.get("intake", {}).get("age") is not None:
            st.slots["patient_age"] = pipeline_result.get("intake", {}).get("age")

        st.history.append({
            "role": "model",
            "parts": [{"text": chat_message}]
        })

        _SESS[sid] = st

        # Extract and structure the response
        explanation_seed = pipeline_result["explanation_seed"]

        # Format top predictions with confidence scores
        top_predictions = [
            {"label": pred["label"], "confidence": round(pred["prob"], 3)}
            for pred in topk
        ]

        # Determine risk score
        risk_score = reasoning["primary_result"]

        ranked_diseases = reasoning.get("ranked_diseases", []) or [
            {
                "label": pred["label"],
                "model_prob": round(pred["prob"], 4),
                "fused_cf": round(pred["prob"], 4),
                "confidence": round(pred["prob"], 4),
            }
            for pred in topk
        ]
        triage = reasoning.get("triage", risk_score)
        risk_level = reasoning.get("risk_level", "low")
        review_flag = bool(reasoning.get("review_flag", triage in {"high_risk", "clinician_review"}))
        triggered_facts = reasoning.get("triggered_facts", []) or []
        triggered_rules = reasoning.get("triggered_rules", []) or []

        symptom_flags = pipeline_result.get("intake", {}) or {}
        clinical_inputs = {
            "bleeding": symptom_flags.get("bleeding"),
            "rapid_change": symptom_flags.get("rapid_change"),
            "width_mm": symptom_flags.get("width_mm") or symptom_flags.get("diameter_mm"),
            "border_0_10": symptom_flags.get("border_0_10") or symptom_flags.get("border_irregularity"),
            "num_colors": symptom_flags.get("num_colors") or symptom_flags.get("number_of_colors"),
            "elevation": symptom_flags.get("elevation"),
            "itching_0_10": symptom_flags.get("itching_0_10") or symptom_flags.get("itching"),
            "pain_0_10": symptom_flags.get("pain_0_10") or symptom_flags.get("pain"),
        }
        combined_risk = build_combined_risk_summary(
            answers=clinical_inputs,
            model_topk=topk,
            model_label_hint=risk_level,
            extras={
                "age": pipeline_result.get("intake", {}).get("age"),
                "duration_days": pipeline_result.get("intake", {}).get("duration_days"),
                "familyHistory": request.form.get("familyHistory"),
            },
        )
        final_level = combined_risk.get("final", {}).get("level", "low")
        risk_score = _risk_label_to_api(final_level)
        risk_level = final_level
        references_cache = get_cached_references()
        cf_fusion = pipeline_result.get("probability_fusion") or run_cf_disease_fusion(
            patient_inputs={
                **clinical_inputs,
                "rapid_change": symptom_flags.get("rapid_change"),
            },
            model_topk=topk,
        )

        explanation_inputs = {
            "model_probs": topk,
            "intake": pipeline_result.get("intake", {}),
            "facts": reasoning.get("facts", {}),
            "trace": reasoning.get("trace", []),
            "triggered_rules": triggered_rules,
            "triggered_facts": triggered_facts,
            "clinical_risk": combined_risk.get("clinical", {}),
            "model_risk": combined_risk.get("model", {}),
            "final_risk": combined_risk.get("final", {}),
            "constraints": {
                "no_new_facts": True,
                "clinical_style": True,
                "single_follow_up_question": True,
            },
        }

        # Build response
        response = {
            # New stable contract
            "ranked_diseases": ranked_diseases,
            "triage": triage,
            "triggered_facts": triggered_facts,
            "explanation_inputs": explanation_inputs,
            "risk_level": risk_level,
            "review_flag": review_flag,

            "top_predictions": top_predictions,
            "risk_score": risk_score,
            "clinical_risk": combined_risk.get("clinical", {}),
            "model_risk": combined_risk.get("model", {}),
            "final_risk": combined_risk.get("final", {}),
            "explanation_summary": explanation_seed,
            "result_summary": {
                "facts": combined_risk.get("clinical", {}).get("facts", []),
                "risk": combined_risk.get("final", {}),
                "recommended_next_step": combined_risk.get("final", {}).get("recommended_next_step"),
            },
            "patient_inputs": cf_fusion.get("patient_inputs", {}),
            "model_probabilities": cf_fusion.get("model_probabilities", {}),
            "certainty_factor_scores": cf_fusion.get("certainty_factor_scores", {}),
            "certainty_factor_probabilities": cf_fusion.get("certainty_factor_probabilities", {}),
            "final_combined_probabilities": cf_fusion.get("final_combined_probabilities", {}),
            "most_likely_disease": cf_fusion.get("most_likely_disease", {}),
            "explanation_of_reasoning": cf_fusion.get("explanation_of_reasoning", {}),
            "recommended_next_step": cf_fusion.get("recommended_next_step"),
            "inputs": cf_fusion.get("inputs", {}),
            "model_probs": cf_fusion.get("model_probs", {}),
            "expert_probs": cf_fusion.get("expert_probs", {}),
            "final_probs": cf_fusion.get("final_probs", {}),
            "top3": cf_fusion.get("top3", []),
            "reasoning": cf_fusion.get("reasoning", []),
            "top_disease_breakdown": cf_fusion.get("top_disease_breakdown", {}),
            "medical_references": {
                "updated_at": references_cache.get("updated_at"),
                "snippets": references_cache.get("snippets", []),
                "note": "General trusted references only; no patient-specific web diagnosis.",
            },
            "assistant_seed": "I have your analysis. I will ask one focused follow-up question to refine the risk assessment.",
            "follow_up_questions": [
                "Has this lesion been changing in size or color?",
                "Do you have a family history of skin cancer?",
                "When did you first notice this lesion?",
            ],
        }

        return jsonify(response)

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=f"Analysis failed: {str(e)}"), 500


@app.post("/predict_model")
def predict_model():
    """
    Stage 1: CNN/image model output only.
    Returns: { top_class, top_prob, top_k }
    """
    try:
        if "image" not in request.files:
            return jsonify(error="image file required (field name: 'image')"), 400
        f = request.files["image"]
        if not f.filename:
            return jsonify(error="empty filename"), 400

        image_bytes = f.read()
        output = run_model_stage(KerasResNetPredictor(), image_bytes=image_bytes, k=3)
        return jsonify(output)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=f"predict_model failed: {str(e)}"), 500


@app.post("/predict_expert")
def predict_expert():
    """
    Stage 2: Expert CF/rule engine using user answers only.
    Returns: { expert_label, triage, explanation }
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        user_answers = payload.get("user_answers", payload)

        if not isinstance(user_answers, dict):
            return jsonify(error="user_answers must be an object"), 400

        output = run_expert_stage(user_answers)
        return jsonify(output)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=f"predict_expert failed: {str(e)}"), 500


@app.post("/predict_fused")
def predict_fused():
    """
    Stage 3: Fusion output.

    Accepted payloads:
    1) JSON with model_output + expert_output
    2) multipart with image + optional user_answers (JSON string)
    """
    try:
        model_output = None
        expert_output = None

        if request.is_json:
            payload = request.get_json(force=True, silent=True) or {}
            model_output = payload.get("model_output")
            expert_output = payload.get("expert_output")

            if model_output is None and "top_k" in payload:
                model_output = {
                    "contract_version": CONTRACT_VERSION,
                    "top_class": payload.get("top_class", "unknown"),
                    "top_prob": payload.get("top_prob", 0.0),
                    "top_k": payload.get("top_k", []),
                }

            if expert_output is None and "triage" in payload:
                expert_output = {
                    "contract_version": CONTRACT_VERSION,
                    "expert_label": payload.get("expert_label", "unknown"),
                    "triage": payload.get("triage", "low_risk"),
                    "explanation": payload.get("explanation", {}),
                    "one_follow_up_question": payload.get("one_follow_up_question", "None"),
                }
        else:
            if "image" in request.files and request.files["image"].filename:
                image_bytes = request.files["image"].read()
                model_output = run_model_stage(KerasResNetPredictor(), image_bytes=image_bytes, k=3)

            raw_answers = request.form.get("user_answers")
            user_answers = {}
            if raw_answers:
                try:
                    user_answers = json.loads(raw_answers)
                except Exception:
                    return jsonify(error="user_answers must be valid JSON when sent as form-data"), 400

            if user_answers:
                expert_output = run_expert_stage(user_answers)

        if model_output is None:
            return jsonify(error="model_output is required (or provide image)") , 400
        if expert_output is None:
            return jsonify(error="expert_output is required (or provide user_answers)") , 400

        fused = run_fusion_stage(model_output, expert_output)
        return jsonify(
            {
                **fused,
                "model_output": model_output,
                "expert_output": expert_output,
            }
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=f"predict_fused failed: {str(e)}"), 500


@app.post("/evidence_lookup")
def evidence_lookup():
    """
    Optional stage: trusted evidence references lookup.
    Prefers web search (if BRAVE_SEARCH_API_KEY is configured), otherwise
    falls back to curated trusted references.
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        query = payload.get("query", "")
        limit = payload.get("limit", 5)
        use_web = bool(payload.get("use_web", True))

        output = run_evidence_lookup(query=query, limit=limit, use_web=use_web)
        return jsonify(output)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=f"evidence_lookup failed: {str(e)}"), 500


@app.post("/admin/references/refresh")
def admin_refresh_references():
    """
    Refresh cached trusted medical-reference snippets.
    Optional JSON body:
      {"snippets": [{"source": "CDC", "title": "...", "url": "...", "snippet": "..."}]}
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        snippets = payload.get("snippets") if isinstance(payload, dict) else None
        if snippets is not None and not isinstance(snippets, list):
            return jsonify(error="snippets must be an array when provided"), 400

        refreshed = refresh_references(snippets)
        return jsonify(
            {
                "status": "ok",
                "updated_at": refreshed.get("updated_at"),
                "count": len(refreshed.get("snippets", [])),
                "cache_file": refreshed.get("cache_file"),
            }
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=f"admin refresh failed: {str(e)}"), 500


@app.get("/pipeline_contracts")
def pipeline_contracts():
    """Expose stage contracts/schemas for frontend/backend integration."""
    return jsonify(
        {
            "contract_version": CONTRACT_VERSION,
            "predict_model": MODEL_OUTPUT_SCHEMA,
            "predict_expert": EXPERT_OUTPUT_SCHEMA,
            "predict_fused": FUSED_OUTPUT_SCHEMA,
            "evidence_lookup": EVIDENCE_LOOKUP_SCHEMA,
        }
    )



@app.post("/reports/save")
def save_report():
    """Save analysis JSON to MongoDB. Accepts JSON body with analysis and metadata."""
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify(error="JSON body required"), 400

        if reports_coll is None:
            return jsonify(error="Reports storage not configured"), 503

        user_email = (
            str(
                payload.get("user_email")
                or payload.get("userEmail")
                or (payload.get("input", {}) or {}).get("user_email")
                or (payload.get("input", {}) or {}).get("userEmail")
                or ""
            )
            .strip()
            .lower()
        )
        if not user_email:
            return jsonify(error="user_email is required"), 400

        payload["user_email"] = user_email
        payload.setdefault("input", {})
        if isinstance(payload["input"], dict):
            payload["input"]["user_email"] = user_email

        # attach timestamp
        payload["createdAt"] = (
            payload.get("createdAt")
            or __import__("datetime").datetime.utcnow().isoformat()
        )
        res = reports_coll.insert_one(payload)
        return jsonify({"report_id": str(res.inserted_id)})
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=str(e)), 500


@app.get("/reports")
def list_reports():
    try:
        if reports_coll is None:
            return jsonify([])

        user_email = str(request.args.get("user_email") or "").strip().lower()
        query = {}
        if user_email:
            query["user_email"] = user_email

        docs = list(reports_coll.find(query).sort("createdAt", -1).limit(100))
        out = []
        for d in docs:
            d["id"] = str(d.pop("_id"))
            out.append(d)
        return jsonify(out)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(error=str(e)), 500


# Serve other front-end files (about.html, upload.html, team.html, etc.)
@app.get("/<path:path>")
def static_pages(path):
    try:
        return send_from_directory(FRONT_DIR, path)
    except Exception:
        return jsonify(error=f"{path} not found"), 404




@app.post("/chat")
def chat():
    try:
        sid = request.args.get("sid", "demo")  # TODO: real session id later
        st = _SESS.get(sid) or ConvState()

        # --- simple per-session debounce/rate-limit ---
        now = time.time()
        last = _LAST_REQUEST.get(sid)
        if last is not None and (now - last) < CHAT_MIN_INTERVAL:
            wait = CHAT_MIN_INTERVAL - (now - last)
            msg = (
                f"You're sending messages too quickly. Please wait {wait:.1f}s and try again."
            )
            print(f"[CHAT][rate] Debounce: sid={sid} wait={wait:.2f}s")
            return (
                jsonify({
                    "reply": msg,
                    "message": "Rate limit: debounce",
                    "assistant": "[Slow down]",
                    "text": msg,
                    "error_code": "RATE_LIMIT_DEBOUNCE",
                }),
                200,
            )

        # sliding window per-minute counter
        dq = _REQ_TIMES.get(sid)
        if dq is None:
            dq = deque()
            _REQ_TIMES[sid] = dq
        # purge older than 60s
        cutoff = now - 60
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= CHAT_MAX_PER_MINUTE:
            msg = (
                "Too many requests from this session in the last minute. Please wait a bit."
            )
            print(f"[CHAT][rate] Sliding-window limit exceeded: sid={sid} count={len(dq)}")
            return (
                jsonify({
                    "reply": msg,
                    "message": "Rate limit: burst",
                    "assistant": "[Try later]",
                    "text": msg,
                    "error_code": "RATE_LIMIT_BURST",
                }),
                200,
            )
        # record this request
        dq.append(now)
        _LAST_REQUEST[sid] = now

        # read text and image from upload form
        user_text = request.form.get("text")
        img_file = request.files.get("image")

        img = None
        if img_file and img_file.filename:
            img = Image.open(img_file.stream).convert("RGB")

        # capture all other metadata from the intake form
        metadata = {k: v for k, v in request.form.items() if k not in ("text",)}

        merged_case_state = _merge_intake_into_session_store(
            sid,
            {
                "age": metadata.get("age") or metadata.get("patient_age"),
                "skin_type": metadata.get("skinType") or metadata.get("fitzpatrick"),
                "lesion_location": metadata.get("location") or metadata.get("body_site"),
                "duration_days": metadata.get("duration_days"),
                "family_history": metadata.get("familyHistory") or metadata.get("family_melanoma_history"),
                "current_triage": metadata.get("primary_result") or metadata.get("triage"),
                "model_probabilities": _parse_json_or_default(metadata.get("model_topk"), []),
                "expert_facts": _parse_json_or_default(metadata.get("facts"), {}),
                "symptom_flags": {
                    "rapid_change": metadata.get("rapid_change"),
                    "bleeding": metadata.get("bleeding"),
                    "itching": metadata.get("itching"),
                    "pain": metadata.get("pain"),
                },
            },
        )
        metadata["session_case_state"] = _build_llm_case_state(sid)
        st.case_state.update(merged_case_state)

        case_ctx = metadata.get("session_case_state") or {}
        print(
            "[CHAT][CaseContext]",
            {
                "sid": sid,
                "age": case_ctx.get("age"),
                "lesion_location": case_ctx.get("lesion_location"),
                "duration_days": case_ctx.get("duration_days"),
                "current_triage": case_ctx.get("current_triage"),
            },
        )

        print("[CHAT] Session:", sid)
        print("[CHAT] Metadata received:", metadata)
        print("[CHAT] Text:", user_text)
        print("[CHAT] Image received:", bool(img))
        print(f"[CHAT] History size before: {len(st.history)} messages")

        #   call AI logic
        try:
            out = chat_step(st, user_text, img, metadata)
        except Exception as e:
            error_str = str(e)
            # Detect 429 (Resource exhausted / rate limit) errors
            if "429" in error_str or "Resource exhausted" in error_str:
                print(
                    f"[CHAT] 429 Resource exhausted (history size: {len(st.history)})"
                )
                print(f"[CHAT] Consider reducing context or using a faster model.")
                out = {
                    "reply": "The AI service is temporarily overloaded. Please wait a moment and try again.",
                    "message": "Service overloaded (429)",
                    "assistant": "[Retry later]",
                    "text": "[Service busy]",
                    "error_code": "RATE_LIMIT",
                }
            else:
                raise

        _SESS[sid] = st
        print(f"[CHAT] History size after: {len(st.history)} messages")

        display = _build_chat_display_payload(out)
        response_payload = {"display": display}
        response_payload["internal"] = _build_chat_internal_payload(metadata, out)

        # Legacy compatibility fields (clean text only)
        response_payload["reply"] = display["message"]
        response_payload["message"] = display["message"]
        response_payload["assistant"] = display["message"]
        response_payload["text"] = display["message"]
        response_payload["message_sections"] = display.get("message_sections", [])
        response_payload["follow_up_question"] = display["follow_up_question"]
        response_payload["fields_needed"] = out.get("fields_needed", [])
        response_payload["ready_for_assessment"] = bool(out.get("ready_for_assessment", False))
        response_payload["awaiting_more_info_choice"] = bool(display.get("awaiting_more_info_choice", False))

        return jsonify(response_payload)

    except Exception as e:
        # Log full traceback to console for debugging
        import traceback

        traceback.print_exc()
        msg = f"Server error: {e}"
        # Keep 200 so the frontend can render the message in the chat bubble
        return (
            jsonify(
                {
                    "display": {
                        "message": msg,
                        "follow_up_question": "None",
                        "fields_needed": [],
                        "ready_for_assessment": False,
                        "disclaimer": CHAT_DISCLAIMER,
                    },
                    "internal": {},
                    "reply": msg,
                    "message": msg,
                    "assistant": msg,
                    "text": msg,
                }
            ),
            200,
        )

        return jsonify(out)


@app.post("/chat/reset")
def chat_reset():
    """Explicitly reset a conversation session (clear history to recover from rate limits)."""
    try:
        sid = request.args.get("sid")
        if sid and sid in _SESS:
            old_size = len(_SESS[sid].history)
            _SESS[sid] = ConvState()
            _SESSION_CASE_STORE.pop(sid, None)
            _LAST_REQUEST.pop(sid, None)
            _REQ_TIMES.pop(sid, None)
            print(f"[CHAT] Reset session {sid} (cleared {old_size} messages)")
            return jsonify({"message": "Chat session reset", "sid": sid})
        else:
            return jsonify({"message": "Session not found or already cleared"}), 404
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Use BACKEND_PORT if set, else PORT, else default to 3720
    port = int(os.getenv("BACKEND_PORT") or os.getenv("PORT") or 3720)
    print(f"[app] Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
