"""Write openapi.json from the FastAPI app, so the contract never drifts from the code.

Usage (from backend/):
    python -m scripts.export_openapi           # rewrite openapi.json
    python -m scripts.export_openapi --check   # exit 1 if openapi.json is stale (CI)

After rewriting, regenerate the frontend types: `npm run gen:api` in frontend/.

Owner: shared
"""

import json
import sys
from pathlib import Path

from app.main import app

OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    expected = render()
    if "--check" in argv:
        current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
        if current.replace("\r\n", "\n") != expected:
            print("openapi.json is stale. Run: python -m scripts.export_openapi")
            return 1
        print("openapi.json is up to date.")
        return 0
    OPENAPI_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Wrote {OPENAPI_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
