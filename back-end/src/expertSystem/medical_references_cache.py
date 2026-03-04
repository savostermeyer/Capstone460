from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import json


DEFAULT_REFERENCES: List[Dict[str, Any]] = [
    {
        "source": "CDC",
        "title": "What Does a Melanoma Look Like?",
        "url": "https://www.cdc.gov/skin-cancer/signs-symptoms/index.html",
        "snippet": "Use the ABCDE rule (Asymmetry, Border, Color, Diameter, Evolving) to identify concerning skin changes.",
    },
    {
        "source": "AAD",
        "title": "ABCDEs of melanoma",
        "url": "https://www.aad.org/public/diseases/skin-cancer/find/at-risk/abcdes",
        "snippet": "Warning signs include asymmetry, irregular border, multiple colors, diameter over 6 mm, and evolving lesions.",
    },
    {
        "source": "MedlinePlus",
        "title": "Skin Cancer",
        "url": "https://medlineplus.gov/skincancer.html",
        "snippet": "General education on skin cancer risk, warning signs, and when to seek medical evaluation.",
    },
    {
        "source": "NIH/NCI",
        "title": "Skin Cancer—Patient Version",
        "url": "https://www.cancer.gov/types/skin",
        "snippet": "Overview of skin cancer types, diagnosis, treatment pathways, and prevention guidance.",
    },
]


_CACHE_PATH = Path(__file__).resolve().parent / "reference_cache.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_snippet(item: Dict[str, Any]) -> Dict[str, str]:
    return {
        "source": str(item.get("source") or "Trusted source").strip(),
        "title": str(item.get("title") or "Reference").strip(),
        "url": str(item.get("url") or "").strip(),
        "snippet": str(item.get("snippet") or "Trusted medical background reference.").strip(),
    }


def get_cached_references() -> Dict[str, Any]:
    if _CACHE_PATH.exists():
        try:
            content = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            snippets = content.get("snippets") if isinstance(content, dict) else None
            if isinstance(snippets, list) and snippets:
                return {
                    "updated_at": str(content.get("updated_at") or ""),
                    "snippets": [_normalize_snippet(s) for s in snippets if isinstance(s, dict)],
                    "cache_file": str(_CACHE_PATH),
                }
        except Exception:
            pass

    return {
        "updated_at": "",
        "snippets": [_normalize_snippet(s) for s in DEFAULT_REFERENCES],
        "cache_file": str(_CACHE_PATH),
    }


def refresh_references(new_snippets: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    snippets = new_snippets if new_snippets else DEFAULT_REFERENCES
    normalized = [_normalize_snippet(s) for s in snippets if isinstance(s, dict)]
    if not normalized:
        normalized = [_normalize_snippet(s) for s in DEFAULT_REFERENCES]

    payload = {
        "updated_at": _now_iso(),
        "snippets": normalized,
    }
    _CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "updated_at": payload["updated_at"],
        "snippets": normalized,
        "cache_file": str(_CACHE_PATH),
    }


def format_references_section() -> str:
    cached = get_cached_references()
    lines = ["Medical references (general education):"]
    for item in cached.get("snippets", [])[:4]:
        lines.append(f"- {item['source']}: {item['title']} — {item['url']}")
    lines.append("These references are educational and not patient-specific diagnosis.")
    return "\n".join(lines)
