import shutil
import sys
from pathlib import Path

import pytest

KV = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KV))            # import kvfos
sys.path.insert(0, str(KV / "tools"))  # import make_sample_data

from make_sample_data import build  # noqa: E402

MONTH = "2026-06"


@pytest.fixture
def root(tmp_path):
    """Isolated kv-fos root: real knowledge base + generated sample month."""
    shutil.copytree(KV / "knowledge", tmp_path / "knowledge")
    build(tmp_path / "months" / MONTH / "inputs", MONTH)
    return tmp_path
