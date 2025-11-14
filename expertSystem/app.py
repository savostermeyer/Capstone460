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
from typing import Dict
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image, ImageOps
from expertSystem.chat import ConvState, step as chat_step


# --- Project roots & import path setup ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

# Import after sys.path is prepared
from query import search  # noqa: E402

FRONT_DIR = os.path.join(ROOT, "front-end")
DATA_DIR = os.path.join(ROOT, "data")
EXP_DIR = os.path.join(ROOT, "expertSystem")


app = Flask(__name__, static_folder=FRONT_DIR, static_url_path="")

from flask_cors import CORS

CORS(app)


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


# Serve other front-end files (about.html, upload.html, team.html, etc.)
@app.get("/<path:path>")
def static_pages(path):
    try:
        return send_from_directory(FRONT_DIR, path)
    except Exception:
        return jsonify(error=f"{path} not found"), 404


# ---------- Chatbot wiring ----------

# hold per-session state in memory for dev; switch to a store later
_SESS: Dict[str, ConvState] = {}


@app.post("/chat")
def chat():
    try:
        sid = request.args.get("sid", "demo")  # TODO: real session id later
        st = _SESS.get(sid) or ConvState()

        # read text and image from upload form
        user_text = request.form.get("text")
        img_file = request.files.get("image")

        img = None
        if img_file and img_file.filename:
            img = Image.open(img_file.stream).convert("RGB")

        # capture all other metadata from the intake form
        metadata = {k: v for k, v in request.form.items() if k not in ("text",)}
        print("[UPLOAD] Metadata received:", metadata)
        print("[UPLOAD] Text:", user_text)
        print("[UPLOAD] Image received", bool(img))

        #   call AI logic
        out = chat_step(st, user_text, img, metadata)
        _SESS[sid] = st

        # add absolute URLs for any image results
        out["metadata"] = metadata

        # add absolute URLs for any image results
        base = request.host_url.rstrip("/")
        for r in out.get("results", []) or []:
            image_id = r.get("image_id")
            if image_id:  # guard in case field missing
                rel = f"/ham/{image_id}.jpg"
                r["url"] = rel
                r["abs_url"] = f"{base}{rel}"

        return jsonify(out)

    except Exception as e:
        # Log full traceback to console for debugging
        import traceback

        traceback.print_exc()
        msg = f"Server error: {e}"
        # Keep 200 so the frontend can render the message in the chat bubble
        return (
            jsonify({"reply": msg, "message": msg, "assistant": msg, "text": msg}),
            200,
        )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3720"))
    app.run(host="0.0.0.0", port=port, debug=True)
