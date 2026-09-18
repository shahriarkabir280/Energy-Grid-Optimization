import json
from pathlib import Path
import pytest


@pytest.fixture(scope="session")
def sample_pack():
    return json.loads(Path("data/public_sample_cases.json").read_text())


@pytest.fixture(scope="session")
def sample_cases(sample_pack):
    return sample_pack["cases"]
