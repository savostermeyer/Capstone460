from __future__ import annotations

import argparse
import json
from pathlib import Path

from expertSystem.medical_references_cache import refresh_references


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh trusted medical reference cache.")
    parser.add_argument(
        "--input",
        type=str,
        default="",
        help="Optional JSON file with snippets array [{source,title,url,snippet}].",
    )
    args = parser.parse_args()

    snippets = None
    if args.input:
        in_path = Path(args.input)
        content = json.loads(in_path.read_text(encoding="utf-8"))
        snippets = content.get("snippets") if isinstance(content, dict) else content

    out = refresh_references(snippets)
    print(json.dumps({
        "status": "ok",
        "updated_at": out.get("updated_at"),
        "count": len(out.get("snippets", [])),
        "cache_file": out.get("cache_file"),
    }, indent=2))


if __name__ == "__main__":
    main()
