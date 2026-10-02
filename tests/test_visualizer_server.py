"""Tests for the visualizer API server's access controls."""

import os
import tempfile

import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_cors")

from antomnievo_visualizer import server


@pytest.fixture(scope="module", autouse=True)
def loopback_security():
    server.configure_security("127.0.0.1", 5173)
    yield
    server.ALLOWED_HOSTS = None


@pytest.fixture
def client():
    server.WORKSPACE_ROOT = None
    with server.app.test_client() as c:
        yield c
    server.WORKSPACE_ROOT = None


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "candidates"))
        yield tmpdir


def _set_workspace(client, path):
    return client.post("/api/config/workspace", json={"path": path})


class TestWorkspaceConfig:
    def test_rejects_non_workspace_dir(self, client):
        resp = _set_workspace(client, "/")
        assert resp.status_code == 400
        assert server.WORKSPACE_ROOT is None

    def test_accepts_workspace_dir(self, client, workspace):
        resp = _set_workspace(client, workspace)
        assert resp.status_code == 200
        assert workspace == server.WORKSPACE_ROOT

    def test_file_outside_workspace_is_rejected(self, client, workspace):
        _set_workspace(client, workspace)
        resp = client.get("/api/file", query_string={"file": "/etc/hosts"})
        assert resp.status_code == 403

    def test_open_directory_rejects_traversal(self, client, workspace):
        _set_workspace(client, workspace)
        resp = client.post("/api/open-directory", json={"candidate_id": "../.."})
        assert resp.status_code == 403


class TestHostHeader:
    def test_loopback_host_allowed(self, client):
        assert client.get("/health", headers={"Host": "localhost:3001"}).status_code == 200
        assert client.get("/health", headers={"Host": "127.0.0.1:3001"}).status_code == 200
        assert client.get("/health", headers={"Host": "[::1]:3001"}).status_code == 200

    def test_foreign_host_rejected(self, client):
        resp = client.get("/health", headers={"Host": "attacker.example:3001"})
        assert resp.status_code == 403


class TestCors:
    def test_frontend_origin_allowed(self, client):
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"

    def test_other_origin_not_allowed(self, client):
        resp = client.get("/health", headers={"Origin": "http://attacker.example"})
        assert "Access-Control-Allow-Origin" not in resp.headers
