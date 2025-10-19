# src/query.py
from __future__ import annotations
import os, json
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from PIL import Image
import torch, faiss
from torchvision import models

# lazy import to avoid circular import
def _infer_from_form(form_dict: dict):
    from expertSystem.interface import infer_from_form
    return infer_from_form(form_dict)

# ---------- Paths ----------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")
IDX_DIR  = os.path.join(DATA_DIR, "index")
FAISS_PATH = os.path.join(IDX_DIR, "faiss.index")
IDS_JSON   = os.path.join(IDX_DIR, "image_ids.json")
META_JSON  = os.path.join(IDX_DIR, "meta.json")

# ---------- Config ----------
HARD_FILTERS = False  # keep False for “AI expert” vibe; True = enforce sex/site/age match
FETCH_K = 100
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ---------- Lazy globals ----------
_index: faiss.Index | None = None
_IMAGE_IDS: List[str] | None = None
_META: Dict[str, Dict[str, Any]] | None = None
_backbone = None
_preproc = None

def _load_index() -> faiss.Index:
    global _index
    if _index is None:
        if not os.path.exists(FAISS_PATH):
            raise FileNotFoundError("FAISS index not found. Run: python expertSystem\\build_index.py")
        _index = faiss.read_index(FAISS_PATH)
    return _index

def _load_meta() -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    global _IMAGE_IDS, _META
    if _IMAGE_IDS is None or _META is None:
        _IMAGE_IDS = json.load(open(IDS_JSON, "r"))
        _META = json.load(open(META_JSON, "r"))
    return _IMAGE_IDS, _META

def _load_model():
    global _backbone, _preproc
    if _backbone is None or _preproc is None:
        w = models.ResNet50_Weights.IMAGENET1K_V2
        m = models.resnet50(weights=w)
        m.fc = torch.nn.Identity()      # 2048-D features
        m.eval().to(DEVICE)
        _backbone = m
        _preproc  = w.transforms()
    return _backbone, _preproc

@torch.inference_mode()
def _embed_pil(img: Image.Image) -> np.ndarray:
    m, pre = _load_model()
    x = pre(img.convert("RGB")).unsqueeze(0).to(DEVICE)   # (1,3,224,224)
    v = m(x).cpu().numpy().astype("float32")              # (1,2048)
    faiss.normalize_L2(v)                                 # cosine via dot
    return v

def _passes_filters(iid: str, ex) -> bool:
    if not HARD_FILTERS:
        return True
    _, META = _load_meta()
    m = META.get(iid, {})
    if ex.sex and m.get("sex") and ex.sex != m["sex"]:
        return False
    if ex.localization and m.get("localization") and ex.localization != m["localization"]:
        return False
    if ex.age is not None:
        age = m.get("age")
        try:
            return age is not None and int(age) == int(ex.age)
        except Exception:
            return False
    return True

def search(img, form_dict: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
    ex = _infer_from_form(form_dict)

    # per-request knobs
    try:
        req_top_k = int(form_dict.get("top_k", top_k))
        top_k = max(1, min(20, req_top_k))  # clamp 1..20
    except Exception:
        pass
    strict = str(form_dict.get("strict", "0")).lower() in {"1","true","yes","y","on"}

    # embed query
    q = _embed_pil(img)

    # load index & sanity-check dims (helps catch mismatched index/model)
    index = _load_index()
    if index.d != q.shape[1]:
        raise RuntimeError(
            f"Index dim {index.d} != query dim {q.shape[1]}. "
            "Rebuild the index with the same backbone (ResNet50)."
        )

    image_ids, META = _load_meta()
    k = max(FETCH_K, top_k)
    D, I = index.search(q, k)  # cosine sims
    D, I = D[0], I[0]

    # collect candidates
    cand: List[Dict[str, Any]] = []
    for dist, idx in zip(D, I):
        if idx < 0:
            continue
        iid = image_ids[idx]
        if strict and not _passes_filters(iid, ex):
            continue
        m = META.get(iid, {})
        cand.append({
            "image_id": iid,
            "dx": m.get("dx"),
            "similarity": float(dist),
            "sex": m.get("sex"),
            "age": (int(m["age"]) if isinstance(m.get("age"), (int, float)) and not pd.isna(m.get("age")) else None),
            "localization": m.get("localization"),
        })
        if len(cand) >= top_k * 5:
            break

    cand.sort(key=lambda r: r["similarity"], reverse=True)
    results = cand[:top_k]

    # neighbor vote tally (optional but handy)
    tally: Dict[str, int] = {}
    for r in cand[:max(50, top_k)]:
        dx = r.get("dx")
        if dx:
            tally[dx] = tally.get(dx, 0) + 1

    if not results:
        ex.reasons.append("No candidates matched filters; showing closest overall matches.")
        # fallback to unfiltered top_k
        results = []
        for dist, idx in zip(D, I):
            if idx < 0:
                continue
            iid = image_ids[idx]
            m = META.get(iid, {})
            results.append({
                "image_id": iid,
                "dx": m.get("dx"),
                "similarity": float(dist),
                "sex": m.get("sex"),
                "age": (int(m["age"]) if isinstance(m.get("age"), (int, float)) and not pd.isna(m.get("age")) else None),
                "localization": m.get("localization"),
            })
            if len(results) >= top_k:
                break

    return {"reasons": ex.reasons, "results": results, "tally": tally}
