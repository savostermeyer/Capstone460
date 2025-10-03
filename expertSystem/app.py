# expertSystem/app.py
import os
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image

from src.query import search

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data")

app = Flask(__name__, static_folder=None)

@app.get("/")
def index():
    # serve your existing expertSystem/index.html
    return send_from_directory(os.path.join(ROOT, "expertSystem"), "index.html")

@app.get("/ham/<image_id>.jpg")
def serve_ham(image_id: str):
    # serve HAM images by id from either part folder
    for sub in ("HAM10000_images_part_1","HAM10000_images_part_2"):
        p = os.path.join(DATA, sub, f"{image_id}.jpg")
        if os.path.exists(p):
            return send_from_directory(os.path.join(DATA, sub), f"{image_id}.jpg")
    return ("not found", 404)

@app.post("/query")
def query():
    if "image" not in request.files:
        return jsonify(error="image file required"), 400
    img = Image.open(request.files["image"].stream)

    # everything else (sex, age, site, flags) comes in as form fields
    payload = dict(request.form.items())
    out = search(img, payload, top_k=5)

    # attach URLs the UI can render
    for r in out["results"]:
        r["url"] = f"/ham/{r['image_id']}.jpg"
    return jsonify(out)

if __name__ == "__main__":
    app.run(debug=True)
