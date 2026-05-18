from __future__ import annotations
import sys
from unittest.mock import MagicMock

# Stub out google.genai so tests that import main/orchestrator don't fail
# in environments where google-cloud packages aren't installed.
_google = MagicMock()
_google.genai = MagicMock()
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.genai", _google.genai)

# Stub anthropic for tests that don't need real API calls
if "anthropic" not in sys.modules:
    _anthropic = MagicMock()
    sys.modules["anthropic"] = _anthropic

# Stub google.generativeai for tests
if "google.generativeai" not in sys.modules:
    _genai = MagicMock()
    sys.modules["google.generativeai"] = _genai
    sys.modules.setdefault("google.generativeai.types", MagicMock())
