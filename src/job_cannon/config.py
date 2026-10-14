"""Resolve where Job Cannon keeps its data.

Everything lives in one folder (database + attachments) so moving to another
machine is just copying that folder.
"""

import os
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "JOB_CANNON_DATA"
DEFAULT_DIR = Path.home() / "JobCannon"
DB_NAME = "jobcannon.db"
FILES_DIR = "files"


@dataclass(frozen=True)
class Config:
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_NAME

    @property
    def files_dir(self) -> Path:
        return self.data_dir / FILES_DIR

    def ensure_dirs(self) -> None:
        self.files_dir.mkdir(parents=True, exist_ok=True)


def resolve(data_dir: str | os.PathLike | None = None) -> Config:
    """--data-dir flag, then JOB_CANNON_DATA, then ~/JobCannon."""
    raw = data_dir or os.environ.get(ENV_VAR) or DEFAULT_DIR
    return Config(Path(raw).expanduser().resolve())
