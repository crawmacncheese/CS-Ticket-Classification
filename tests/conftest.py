import sys
from pathlib import Path

import pytest

# Ensure src layout on path when running pytest without editable install
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture
def repo_root() -> Path:
    return _ROOT
