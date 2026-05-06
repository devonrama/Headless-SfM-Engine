import os
import sys
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUBPROCESS_TIMEOUT_SEC = int(os.getenv("HSE_SUBPROCESS_TIMEOUT", "1800"))


class ColmapRunner:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.root = PROJECT_ROOT
        self.image_path = self.root / "data" / "raw" / task_id
        self.task_output = self.root / "data" / "output" / task_id
        self.sparse_path = self.task_output / "sparse"
        self.database_path = self.task_output / "database.db"
        self.log_path = self.task_output / "exec.log"
        self.image_path.mkdir(parents=True, exist_ok=True)
        self.sparse_path.mkdir(parents=True, exist_ok=True)
        self.colmap = os.getenv("COLMAP_BIN", "colmap")

    def _log(self, msg: str):
        with open(self.log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(msg + "\n")

    def _exec_sync(self, cmd: str, phase: str) -> int:
        """Sync subprocess execution. Called via asyncio.to_thread from async context."""
        import subprocess
        self._log(f"[{phase}] EXEC: {cmd}")
        with open(self.log_path, "a", encoding="utf-8", errors="replace") as logf:
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    timeout=SUBPROCESS_TIMEOUT_SEC,
                    check=False,
                )
                return result.returncode
            except subprocess.TimeoutExpired:
                self._log(f"[{phase}] TIMEOUT after {SUBPROCESS_TIMEOUT_SEC}s")
                raise RuntimeError(f"COLMAP {phase} timeout")

    async def _exec(self, cmd: str, phase: str):
        rc = await asyncio.to_thread(self._exec_sync, cmd, phase)
        if rc != 0:
            self._log(f"[{phase}] FAILED rc={rc}")
            raise RuntimeError(f"COLMAP {phase} failed rc={rc}")

    async def feature_extraction(self):
        cmd = (
            f"{self.colmap} feature_extractor "
            f"--database_path {self.database_path.as_posix()} "
            f"--image_path {self.image_path.as_posix()} "
            f"--ImageReader.single_camera 1"
        )
        await self._exec(cmd, "SIFT")

    async def matching(self):
        cmd = (
            f"{self.colmap} exhaustive_matcher "
            f"--database_path {self.database_path.as_posix()}"
        )
        await self._exec(cmd, "MATCH")

    async def mapper(self):
        cmd = (
            f"{self.colmap} mapper "
            f"--database_path {self.database_path.as_posix()} "
            f"--image_path {self.image_path.as_posix()} "
            f"--output_path {self.sparse_path.as_posix()}"
        )
        await self._exec(cmd, "MAPPER")

    async def model_converter(self):
        sparse0 = (self.sparse_path / "0").as_posix()
        cmd = (
            f"{self.colmap} model_converter "
            f"--input_path {sparse0} "
            f"--output_path {sparse0} "
            f"--output_type TXT"
        )
        await self._exec(cmd, "CONVERT")

    async def run(self):
        await self.feature_extraction()
        await self.matching()
        await self.mapper()
        await self.model_converter()


async def run_sfm_pipeline(task_id: str):
    runner = ColmapRunner(task_id)
    try:
        await runner.run()
    except Exception as e:
        runner._log(f"FAILED: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else "default"
    asyncio.run(run_sfm_pipeline(tid))
