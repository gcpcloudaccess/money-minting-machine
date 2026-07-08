"""pytest always imports conftest.py before collecting any test file, so this
is a second, test-time-only guarantee (alongside app/__init__.py, which covers
every runtime entry point) that backend/vendor/ is on sys.path before a test
file's own top-level `from algo_agent...` / `from risk_agent...` imports run -
several integration test files import a vendored package directly without
going through `app.*` first, which wouldn't otherwise trigger the bootstrap."""

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
