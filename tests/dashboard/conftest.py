import pytest
from fastapi.testclient import TestClient

from .helpers import _dm


@pytest.fixture
def client(tmp_path):
    _dm.app.state.root = tmp_path
    return TestClient(_dm.app, raise_server_exceptions=True)
