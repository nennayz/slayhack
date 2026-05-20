from __future__ import annotations
import importlib
import sys
import types
from unittest.mock import MagicMock

def _ensure_google_submodule(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = MagicMock(spec=types.ModuleType)
        sys.modules[name] = module
    return module


# Stub only the optional Google AI client modules used by some tests.
# Do not replace the top-level `google` package, because real namespace
# packages under google.auth/googleapiclient must remain importable.
_google_genai = _ensure_google_submodule("google.genai")
if not hasattr(_google_genai, "Client"):
    setattr(_google_genai, "Client", MagicMock())

try:
    _google_pkg = importlib.import_module("google")
except ModuleNotFoundError:
    _google_pkg = types.ModuleType("google")
    _google_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["google"] = _google_pkg

if not hasattr(_google_pkg, "genai"):
    setattr(_google_pkg, "genai", _google_genai)

# Stub anthropic for tests that don't need real API calls
if "anthropic" not in sys.modules:
    _anthropic = MagicMock()
    sys.modules["anthropic"] = _anthropic

# Stub google.generativeai for tests
if "google.generativeai" not in sys.modules:
    _genai = MagicMock(spec=types.ModuleType)
    sys.modules["google.generativeai"] = _genai
    sys.modules.setdefault("google.generativeai.types", MagicMock())
