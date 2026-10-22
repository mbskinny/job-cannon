"""Profiles: several people sharing one install, each with their own data folder.

The data folder resolved by ``config.resolve`` is the *root*. It holds
``profiles.json`` (the registry and which profile is active) and the first
profile's data, which lives in the root itself (``dir`` ".") so installs from
before profiles keep working without moving anything. Later profiles live in
``profiles/<id>/``. Each profile's folder is an ordinary ``Config`` data folder.
"""

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from job_cannon import config as config_mod
from job_cannon.config import Config

REGISTRY = "profiles.json"
PROFILES_DIR = "profiles"
ENV_VAR = "JOB_CANNON_PROFILE"
JOB_SEARCH_FILE = "job-search.md"


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    dir: str

    def config(self, root: Path) -> Config:
        return Config((root / self.dir).resolve())

    def job_search_file(self, root: Path) -> Path:
        return self.config(root).data_dir / JOB_SEARCH_FILE


@dataclass
class Registry:
    active: str
    profiles: list[Profile]

    def find(self, key: str) -> Profile | None:
        """Look up by id, or by name ignoring case."""
        for p in self.profiles:
            if p.id == key:
                return p
        for p in self.profiles:
            if p.name.lower() == key.strip().lower():
                return p
        return None

    def active_profile(self) -> Profile:
        return self.find(self.active) or self.profiles[0]


def load(root: Path) -> Registry:
    """Read the registry. Without one there is a single profile, kept in the root itself."""
    path = root / REGISTRY
    if not path.exists():
        return Registry("default", [Profile("default", "Default", ".")])
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Registry(raw["active"], [Profile(**p) for p in raw["profiles"]])


def save(root: Path, reg: Registry) -> None:
    data = {"active": reg.active, "profiles": [asdict(p) for p in reg.profiles]}
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / (REGISTRY + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, root / REGISTRY)


def get(root: Path, key: str) -> Profile:
    p = load(root).find(key)
    if p is None:
        raise ValueError(f"No profile named {key!r}")
    return p


def active(root: Path) -> Profile:
    return load(root).active_profile()


def set_active(root: Path, key: str) -> Profile:
    reg = load(root)
    p = reg.find(key)
    if p is None:
        raise ValueError(f"No profile named {key!r}")
    reg.active = p.id
    save(root, reg)
    return p


def _clean_name(reg: Registry, name: str, exclude: str | None = None) -> str:
    name = " ".join(name.split())
    if not name:
        raise ValueError("Profile name is required")
    if len(name) > 60:
        raise ValueError("Profile name is too long")
    if any(p.name.lower() == name.lower() and p.id != exclude for p in reg.profiles):
        raise ValueError(f"There is already a profile named {name!r}")
    return name


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "profile"


def create(root: Path, name: str) -> Profile:
    reg = load(root)
    name = _clean_name(reg, name)
    taken = {p.id for p in reg.profiles}
    base = _slug(name)
    pid, n = base, 2
    while pid in taken or (root / PROFILES_DIR / pid).exists():
        pid, n = f"{base}-{n}", n + 1
    profile = Profile(pid, name, f"{PROFILES_DIR}/{pid}")
    profile.config(root).ensure_dirs()
    reg.profiles.append(profile)
    save(root, reg)
    return profile


def rename(root: Path, key: str, name: str) -> Profile:
    reg = load(root)
    p = reg.find(key)
    if p is None:
        raise ValueError(f"No profile named {key!r}")
    renamed = Profile(p.id, _clean_name(reg, name, exclude=p.id), p.dir)
    reg.profiles = [renamed if q.id == p.id else q for q in reg.profiles]
    save(root, reg)
    return renamed


def check_delete(root: Path, key: str) -> Profile:
    """Raise ValueError unless the profile can be deleted: not the active one, nor the root's own."""
    reg = load(root)
    p = reg.find(key)
    if p is None:
        raise ValueError(f"No profile named {key!r}")
    if p.id == reg.active:
        raise ValueError("Switch to another profile before deleting this one")
    if p.dir == ".":
        raise ValueError(f"{p.name!r} keeps its data in the main data folder and can't be deleted")
    return p


def delete(root: Path, key: str) -> Profile:
    """Remove a profile and its whole data folder (see ``check_delete``)."""
    p = check_delete(root, key)
    reg = load(root)
    reg.profiles = [q for q in reg.profiles if q.id != p.id]
    save(root, reg)
    shutil.rmtree(p.config(root).data_dir, ignore_errors=True)
    return p


def resolve_profile(data_dir: str | os.PathLike | None = None, profile: str | None = None) -> tuple[Path, Profile]:
    """(root, profile): --profile, then JOB_CANNON_PROFILE, then the active one."""
    root = config_mod.resolve(data_dir).data_dir
    key = profile or os.environ.get(ENV_VAR)
    return root, (get(root, key) if key else active(root))


def resolve(data_dir: str | os.PathLike | None = None, profile: str | None = None) -> Config:
    """Data folder of a profile, chosen as in ``resolve_profile``."""
    root, p = resolve_profile(data_dir, profile)
    return p.config(root)
