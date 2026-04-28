import os
import re
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

import aiofiles
from PIL import Image
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.colmap_runner import run_sfm_pipeline, PROJECT_ROOT

import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="Headless SfM Engine")

RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")

_RE_REGISTERED = re.compile(r"Registered\s+images\s*[:=]\s*(\d+)", re.IGNORECASE)
_RE_POINTS = re.compile(r"\bPoints\s*[:=]\s*(\d+)", re.IGNORECASE)
_IMG_EXTS = (".jpg", ".jpeg", ".png")


def _flatten_image_dir(root: Path):
    for dirpath, _, filenames in os.walk(root):
        if Path(dirpath) == root:
            continue
        for fn in filenames:
            if fn.lower().endswith(_IMG_EXTS):
                src = Path(dirpath) / fn
                dst = root / fn
                if dst.exists():
                    i = 1
                    while (root / f"{src.stem}_{i}{src.suffix}").exists():
                        i += 1
                    dst = root / f"{src.stem}_{i}{src.suffix}"
                shutil.move(str(src), str(dst))
    for p in root.iterdir():
        if p.is_file() and p.suffix.lower() in _IMG_EXTS:
            with Image.open(p) as img:
                if max(img.size) > 1024:
                    img.thumbnail((1024, 1024), Image.LANCZOS)
                    img.save(p)
    for dirpath, _, _ in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root:
            continue
        try:
            p.rmdir()
        except OSError:
            pass


def _count_data_lines(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                n += 1
    return n


@app.post("/api/v1/reconstruct")
async def reconstruct(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected .zip upload")

    task_id = str(uuid.uuid4())
    raw_dir = RAW_DIR / task_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "_upload.zip"

    async with aiofiles.open(zip_path, "wb") as f:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            await f.write(chunk)

    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(raw_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Corrupt zip payload")
    finally:
        zip_path.unlink(missing_ok=True)

    _flatten_image_dir(raw_dir)

    img_count = sum(
        1 for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _IMG_EXTS
    )
    if img_count == 0:
        shutil.rmtree(raw_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="Terminasi: Arsip tidak valid, korup, atau memiliki 0 citra spasial.",
        )

    background_tasks.add_task(run_sfm_pipeline, task_id)
    return {"task_id": task_id, "status": "processing"}


@app.get("/api/v1/status/{task_id}")
async def status(task_id: str, request: Request):
    task_out = OUTPUT_DIR / task_id
    if not task_out.exists():
        raise HTTPException(status_code=404, detail="Unknown task_id")

    cameras_txt = task_out / "sparse" / "0" / "cameras.txt"
    log_path = task_out / "exec.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    if not cameras_txt.exists():
        if "FAILED" in log_text:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": "Rekonstruksi gagal. Validasi kualitas citra dan tingkat overlap.",
            }
        return {"task_id": task_id, "status": "processing"}

    sparse0 = task_out / "sparse" / "0"
    m_reg = _RE_REGISTERED.search(log_text)
    m_pts = _RE_POINTS.search(log_text)
    if m_reg:
        registered = int(m_reg.group(1))
    else:
        registered = _count_data_lines(sparse0 / "images.txt") // 2
    if m_pts:
        points = int(m_pts.group(1))
    else:
        points = _count_data_lines(sparse0 / "points3D.txt")

    base = str(request.base_url).rstrip("/")
    return {
        "task_id": task_id,
        "status": "completed",
        "registered_images": registered,
        "points": points,
        "download_urls": {
            "cameras": f"{base}/files/{task_id}/sparse/0/cameras.txt",
            "images": f"{base}/files/{task_id}/sparse/0/images.txt",
            "points": f"{base}/files/{task_id}/sparse/0/points3D.txt",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
