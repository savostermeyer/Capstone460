# expertSystem/app.py
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
EXP_DIR  = os.path.join(ROOT, "expertSystem")


app = Flask(__name__, static_folder=FRONT_DIR, static_url_path="")

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
    # return send_from_directory(FRONT_DIR, "index.html")
    # to run demo code:
    return send_from_directory(EXP_DIR, "indexdemo.html")  # <- fixed indent

# Serve other front-end files (about.html, upload.html, team.html, etc.)
@app.get("/<path:path>")
def static_pages(path):
    try:
        return send_from_directory(FRONT_DIR, path)
    except Exception:
        return jsonify(error=f"{path} not found"), 404

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

# ---------- Chatbot wiring ----------

# hold per-session state in memory for dev; switch to a store later
_SESS: Dict[str, ConvState] = {}

@app.post("/chat")
def chat():
    sid = request.args.get("sid", "demo")   # TODO: replace with real session id
    st = _SESS.get(sid) or ConvState()
    user_text = request.form.get("text")
    img_file = request.files.get("image")

    img = None
    if img_file and img_file.filename:
        img = Image.open(img_file.stream).convert("RGB")

    out = chat_step(st, user_text, img)
    _SESS[sid] = st

    # add absolute URLs for any image results
    base = request.host_url.rstrip("/")
    for r in out.get("results", []) or []:
        rel = f"/ham/{r['image_id']}.jpg"
        r["url"] = rel
        r["abs_url"] = f"{base}{rel}"
    return jsonify(out)

if __name__ == "__main__":
    # Ensure all routes are defined BEFORE running
    app.run(host="127.0.0.1", port=5000, debug=True)
