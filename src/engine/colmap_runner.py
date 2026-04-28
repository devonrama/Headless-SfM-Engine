import os
import sys
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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

    async def _exec(self, cmd: str, phase: str):
        self._log(f"[{phase}] EXEC: {cmd}")
        redirected = f'{cmd} >> "{self.log_path.as_posix()}" 2>&1'
        proc = await asyncio.create_subprocess_shell(redirected)
        await proc.wait()
        if proc.returncode != 0:
            self._log(f"[{phase}] FAILED rc={proc.returncode}")
            raise RuntimeError(f"COLMAP {phase} failed rc={proc.returncode}")

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
    await ColmapRunner(task_id).run()


if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else "default"
    asyncio.run(run_sfm_pipeline(tid))
