# expertSystem/app.py
import os
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image, ImageOps
from src.query import search

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")
EXP_DIR  = os.path.join(ROOT, "expertSystem")

app = Flask(__name__, static_folder=None)

def _strip_exif(img: Image.Image) -> Image.Image:
    try: img = ImageOps.exif_transpose(img)
    except Exception: pass
    out = Image.new(img.mode, img.size); out.putdata(list(img.getdata()))
    return out

@app.get("/")
def index():
    return send_from_directory(EXP_DIR, "index.html")

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
    for r in out.get("results", []):
        r["url"] = f"/ham/{r['image_id']}.jpg"
    return jsonify(out)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
