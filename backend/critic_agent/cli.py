from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .critic import review_recommendation


def main() -> None:
    parser = argparse.ArgumentParser(description="Review trade recommendation JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    review = subparsers.add_parser("review")
    review.add_argument("--input", help="Path to recommendation JSON. Reads stdin when omitted.")
    review.add_argument("--fail-on-reject", action="store_true", help="Exit with code 2 when verdict is REJECT.")
    args = parser.parse_args()

    payload = _load_payload(args.input)
    critique = review_recommendation(payload)
    print(json.dumps(critique.to_dict(), indent=2))

    if args.fail_on_reject and critique.verdict == "REJECT":
        raise SystemExit(2)


def _load_payload(path: str | None) -> dict[str, Any]:
    if path:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(f"Could not read input file: {path}") from exc
    else:
        content = sys.stdin.read()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Recommendation JSON must be an object.")
    return payload


if __name__ == "__main__":
    main()
