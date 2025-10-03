# src/query.py
from __future__ import annotations
import os
from typing import Any, Dict, List
import random

import pandas as pd

# NOTE: lazy import of infer_from_form to avoid circular import
# (expertSystem.app -> src.query -> expertSystem.*)
def _infer_from_form(form_dict: dict):
    from expertSystem.interface import infer_from_form
    return infer_from_form(form_dict)

# ---------- Paths ----------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")
CSV_PATH = os.path.join(DATA_DIR, "HAM10000_metadata.csv")

# ---------- Metadata cache ----------
_DF: pd.DataFrame | None = None

def _load_metadata() -> pd.DataFrame:
    global _DF
    if _DF is not None:
        return _DF

    df = pd.read_csv(CSV_PATH)

    # Normalize cols we need
    # Expected columns in HAM10000 CSV: image_id, dx, age (or age_approx), sex, localization
    # Some releases name age column "age". Others "age_approx". Handle both.
    if "age" not in df.columns and "age_approx" in df.columns:
        df["age"] = df["age_approx"]

    # Clean/normalize types
    df["sex"] = (df["sex"].astype(str).str.lower()).fillna("unknown").replace({"nan": "unknown"})
    df["localization"] = df["localization"].astype(str).str.lower()
    # age can be NaN; keep as float then convert to Int when returning
    # dx already a string label in {"akiec","bcc","bkl","df","mel","nv","vasc"}

    _DF = df
    return _DF

# ---------- Filter helpers ----------
def _apply_hard_filters(df: pd.DataFrame, ex) -> pd.DataFrame:
    m = pd.Series([True] * len(df), index=df.index)

    if ex.filter_sex:
        m &= (df["sex"] == ex.filter_sex)

    if ex.filter_localization:
        m &= (df["localization"] == ex.filter_localization)

    if ex.filter_age_min is not None or ex.filter_age_max is not None:
        amin = ex.filter_age_min if ex.filter_age_min is not None else -10**9
        amax = ex.filter_age_max if ex.filter_age_max is not None else 10**9
        # age may be NaN; drop NaNs when filtering
        m &= df["age"].notna() & (df["age"] >= amin) & (df["age"] <= amax)

    filtered = df[m]
    return filtered

def _base_similarity(row: pd.Series) -> float:
    # For demo: give a plausible-looking base similarity
    # You can swap this with real cosine similarity from embeddings later.
    return round(random.uniform(0.60, 0.95), 3)

def _apply_bonus(sim: float, dx: str, bonus_map: Dict[str, float]) -> float:
    return sim + float(bonus_map.get(dx, 0.0))

# ---------- Public API used by app.py ----------
def search(img, form_dict: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
    """
    Returns:
      {
        "reasons": [str, ...],
        "results": [
           {"image_id":..., "dx":..., "similarity":float, "sex":..., "age":..., "localization":...},
           ...
        ]
      }
    """
    # 1) Expert-system inference from form fields
    ex = _infer_from_form(form_dict)

    # 2) Load metadata and apply hard filters
    df = _load_metadata()
    filt_df = _apply_hard_filters(df, ex)

    # If filters are too strict, fall back (and note reason)
    if len(filt_df) == 0:
        ex.reasons.append("No candidates matched filters; showing closest overall matches.")
        filt_df = df

    # 3) Sample some candidates, assign a base similarity
    # Grab up to N rows to score (keep it lightweight)
    N = min(len(filt_df), 200)  # cap for speed
    sample_df = filt_df.sample(n=N, random_state=None) if len(filt_df) > N else filt_df.copy()

    sample_df = sample_df.copy()
    sample_df["similarity"] = sample_df.apply(_base_similarity, axis=1)

    # 4) Apply soft bonuses and re-rank
    sample_df["_score"] = sample_df.apply(lambda r: _apply_bonus(r["similarity"], str(r["dx"]), ex.class_bonus), axis=1)
    sample_df = sample_df.sort_values("_score", ascending=False).head(top_k)

    # 5) Build results
    results: List[Dict[str, Any]] = []
    for _, r in sample_df.iterrows():
        age_val = r["age"]
        # convert NaN -> None, else int
        age_out = int(age_val) if pd.notna(age_val) else None

        results.append({
            "image_id": str(r["image_id"]),
            "dx": str(r["dx"]),
            "similarity": float(r["similarity"]),
            "sex": (str(r["sex"]).lower() if pd.notna(r["sex"]) else "unknown"),
            "age": age_out,
            "localization": (str(r["localization"]).lower() if pd.notna(r["localization"]) else None),
        })

    return {"reasons": ex.reasons, "results": results}
