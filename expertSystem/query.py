# src/query.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import math

from expertSystem import infer_from_form   # your single entrypoint

# ----- 1) Hook to your team's model/retriever -----
def _cnn_retrieve_candidates(img, top_k: int = 30) -> List[Dict[str, Any]]:
    """
    Placeholder: replace with your team's actual retrieval.
    Return a list of dicts with keys:
      image_id, dx, similarity (float, higher is better),
      sex, age, localization
    """
    # Example dummy structure (REMOVE once wired to real retriever):
    return [
        {
            "image_id": "ISIC_0000000",
            "dx": "nv",
            "similarity": 0.71,
            "sex": "male",
            "age": 38,
            "localization": "back",
        },
        # ... more candidates ...
    ][:top_k]

# ----- 2) Filtering helpers -----
def _pass_filters(row: Dict[str, Any], ex) -> bool:
    # sex
    if ex.filter_sex and str(row.get("sex") or "").lower() != ex.filter_sex:
        return False
    # localization
    if ex.filter_localization and str(row.get("localization") or "").lower() != ex.filter_localization:
        return False
    # age
    if ex.filter_age_min is not None or ex.filter_age_max is not None:
        age = row.get("age")
        if age is None:
            return False
        if ex.filter_age_min is not None and age < ex.filter_age_min:
            return False
        if ex.filter_age_max is not None and age > ex.filter_age_max:
            return False
    return True

def _apply_bonus(sim: float, dx: str, bonus_map: Dict[str, float]) -> float:
    # additive reweighting; keep within sensible bounds
    b = float(bonus_map.get(dx, 0.0))
    return sim + b

# ----- 3) Main entry, used by app.py -----
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
    # Run expert system on the user inputs (NOT on the image)
    ex = infer_from_form(form_dict)

    # Get candidates from model/retriever
    cands = _cnn_retrieve_candidates(img, top_k=50)

    # Hard-filter
    filtered = [r for r in cands if _pass_filters(r, ex)]
    if not filtered:
        # If filters are too strict, fall back to unfiltered but note the reason
        filtered = cands
        ex.reasons.append("No candidates matched filters; showing closest overall matches.")

    # Apply soft bonuses & sort
    for r in filtered:
        r["_score"] = _apply_bonus(float(r.get("similarity", 0.0)), str(r.get("dx","")), ex.class_bonus)

    filtered.sort(key=lambda x: x["_score"], reverse=True)
    results = []
    for r in filtered[:top_k]:
        results.append({
            "image_id": r.get("image_id"),
            "dx": r.get("dx"),
            "similarity": float(r.get("similarity", 0.0)),
            "sex": r.get("sex"),
            "age": r.get("age"),
            "localization": r.get("localization"),
        })

    return {"reasons": ex.reasons, "results": results}
