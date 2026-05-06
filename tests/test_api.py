"""Integration tests for HSE API endpoints.

Tests use FastAPI TestClient with monkeypatched run_sfm_pipeline to avoid
running actual COLMAP during tests. Fixture zips are generated at runtime.
"""
import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure src/ is on path so `from api.main import app` resolves
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api import main as api_main


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with COLMAP pipeline stubbed and writable temp dirs."""

    # Stub the actual COLMAP pipeline — tests should not invoke it
    async def fake_pipeline(task_id: str):
        return None

    monkeypatch.setattr(api_main, "run_sfm_pipeline", fake_pipeline)

    # Redirect data dirs to temp so tests don't pollute real data/
    monkeypatch.setattr(api_main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(api_main, "OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)

    return TestClient(api_main.app)


def _make_zip(files: dict) -> bytes:
    """Build an in-memory zip from {name: bytes} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _make_dummy_jpeg(width: int = 32, height: int = 32) -> bytes:
    """Smallest valid JPEG bytes for upload tests."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


# ---------- TEST 1: Happy path (upload accepted, processing returned) ----------

def test_upload_valid_zip_returns_processing(client):
    """Valid zip with images is accepted; pipeline dispatched in background."""
    jpeg_bytes = _make_dummy_jpeg()
    zip_bytes = _make_zip({
        "img1.jpg": jpeg_bytes,
        "img2.jpg": jpeg_bytes,
        "img3.jpg": jpeg_bytes,
    })

    resp = client.post(
        "/api/v1/reconstruct",
        files={"file": ("sample.zip", zip_bytes, "application/zip")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "task_id" in body
    assert body["status"] == "processing"
    assert len(body["task_id"]) > 0


# ---------- TEST 2: Status query on unknown task_id returns 404 ----------

def test_status_unknown_task_returns_404(client):
    resp = client.get("/api/v1/status/nonexistent-task-id")
    assert resp.status_code == 404
    assert "Unknown task_id" in resp.json()["detail"]


# ---------- TEST 3: Non-zip upload rejected ----------

def test_upload_non_zip_rejected(client):
    resp = client.post(
        "/api/v1/reconstruct",
        files={"file": ("not_a_zip.txt", b"this is not a zip", "text/plain")},
    )
    assert resp.status_code == 400
    assert "Expected .zip upload" in resp.json()["detail"]


# ---------- TEST 4: Corrupt zip rejected ----------

def test_upload_corrupt_zip_rejected(client):
    resp = client.post(
        "/api/v1/reconstruct",
        files={"file": ("broken.zip", b"PK\x03\x04 garbage data", "application/zip")},
    )
    assert resp.status_code == 400
    assert "Corrupt zip payload" in resp.json()["detail"]


# ---------- TEST 5: Empty zip (no images) rejected ----------

def test_upload_zip_without_images_rejected(client):
    """Zip with non-image files only is rejected."""
    zip_bytes = _make_zip({
        "readme.txt": b"This zip has no images",
        "data.csv": b"col1,col2\n1,2\n",
    })

    resp = client.post(
        "/api/v1/reconstruct",
        files={"file": ("empty.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 400
    assert "0 citra spasial" in resp.json()["detail"]