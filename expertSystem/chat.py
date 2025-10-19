# expertSystem/chat.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import re
from src.query import search as image_search

# ---- Slots we care about (HAM-aligned + symptoms) ----
SITES = {
    "back","trunk","chest","abdomen","upper extremity","lower extremity",
    "face","scalp","neck","ear","hand","foot","genital","unknown"
}
SYMPTOMS = ["itching","bleeding","pain","tender","growth","color change","border change","ulcer"]

@dataclass
class ConvState:
    # User facts (slots)
    age: Optional[int] = None
    sex: Optional[str] = None        # "male" / "female" / None
    site: Optional[str] = None       # normalized to HAM localization where possible
    duration_weeks: Optional[float] = None
    symptoms: List[str] = field(default_factory=list)  # subset of SYMPTOMS
    image_attached: bool = False

    # Internal
    asked: Dict[str, bool] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def missing(self) -> List[str]:
        need = []
        if self.age is None: need.append("age")
        if self.sex is None: need.append("sex")
        if self.site is None: need.append("site")
        if self.duration_weeks is None: need.append("duration")
        if not self.symptoms: need.append("symptoms")
        if not self.image_attached: need.append("image")
        return need

# ---- Normalizers ----
def norm_sex(s: str|None) -> str|None:
    if not s: return None
    s = s.strip().lower()
    if s.startswith("m"): return "male"
    if s.startswith("f"): return "female"
    return None

def norm_site(s: str|None) -> str|None:
    if not s: return None
    s = s.strip().lower()
    # light mapping: map “arm” -> upper extremity, “leg” -> lower extremity, etc.
    if "arm" in s: return "upper extremity"
    if "leg" in s: return "lower extremity"
    if s in SITES: return s
    return s  # fallback; your index just won’t filter strictly

def parse_symptoms(text: str) -> List[str]:
    text = (text or "").lower()
    return [w for w in SYMPTOMS if re.search(rf"\b{re.escape(w)}\b", text)]

# ---- Dialog policy: what to ask next ----
def next_question(st: ConvState) -> str|None:
    for slot in st.missing():
        if st.asked.get(slot): continue
        st.asked[slot] = True
        if slot == "image":
            return "Please upload a clear photo of the spot (close-up and one from ~20cm)."
        if slot == "site":
            return "Where on the body is the spot (e.g., back, face, arm, leg)?"
        if slot == "sex":
            return "What is your sex (male/female)?"
        if slot == "age":
            return "How old are you?"
        if slot == "duration":
            return "How long has the spot been present (weeks)? Has it changed recently?"
        if slot == "symptoms":
            return "Any symptoms like itching, bleeding, pain, rapid growth, or color/border change?"
    return None  # ready to reason

# ---- Core step function ----
def step(st: ConvState, user_text: str|None, img=None) -> Dict[str, Any]:
    # 1) Ingest new info
    if user_text:
        # try to extract/fill simple slots
        m = re.search(r"(\d{1,3})\s*(yo|years? old|y/o)?", user_text.lower())
        if m:
            st.age = min(110, int(m.group(1)))
        sx = norm_sex(user_text)
        if sx: st.sex = sx
        site = norm_site(user_text)
        if site: st.site = site
        if "week" in user_text.lower():
            mw = re.search(r"(\d+(\.\d+)?)\s*week", user_text.lower())
            if mw: st.duration_weeks = float(mw.group(1))
        # symptoms from free text
        sy = parse_symptoms(user_text)
        st.symptoms = sorted(set(st.symptoms + sy))

    if img is not None:
        st.image_attached = True

    # 2) If missing info, ask next question
    q = next_question(st)
    if q:
        return {"ask": q, "state": st.__dict__}

    # 3) We have enough to produce a result. Build form for your image_search()
    form = {
        "sex": st.sex or "",
        "localization": st.site or "",
        "age": st.age if st.age is not None else "",
        # knobs: strict/alpha/top_k can be set from policy or UI
        "strict": "0",
        "alpha": "0.85",
        "top_k": "6",
    }

    # 4) Run tools: image NN search (required), web knowledge (optional later)
    nn = None
    if img is not None:
        nn = image_search(img, form, top_k=int(form["top_k"]))
    else:
        # image required for best results; return ask if missing
        return {"ask": "Please upload an image to compare against reference cases.", "state": st.__dict__}

    # 5) Summarize neighbors + reasons (no medical diagnosis)
    results = nn.get("results", [])
    tally = nn.get("tally", {})
    st.reasons.extend(nn.get("reasons", []))

    explanation = []
    if st.site: explanation.append(f"Site reported: {st.site}.")
    if st.age is not None and st.sex:
        explanation.append(f"Age/Sex: {st.age}, {st.sex}.")
    if st.symptoms:
        explanation.append(f"Symptoms: {', '.join(st.symptoms)}.")
    explanation.append("Similar reference cases were retrieved based on visual features; these are not diagnoses.")
    if tally:
        # show top neighbor categories by vote
        tv = sorted(tally.items(), key=lambda x: x[1], reverse=True)[:3]
        explanation.append("Common neighbor labels: " + ", ".join(f"{k} (n={v})" for k,v in tv) + ".")

    return {
        "results": results,
        "explanation": " ".join(explanation),
        "reasons": st.reasons,
        "state": st.__dict__,
        "next": "This information cannot provide a medical diagnosis. If the spot changes rapidly, bleeds, ulcerates, or you’re worried, seek in-person care."
    }
