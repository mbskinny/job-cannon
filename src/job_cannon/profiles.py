"""Profiles: several people sharing one install, each with their own data folder.

The data folder resolved by ``config.resolve`` is the *root*. It holds
``profiles.json`` (the registry and which profile is active) and the first
profile's data, which lives in the root itself (``dir`` ".") so installs from
before profiles keep working without moving anything. Later profiles live in
``profiles/<id>/``. Each profile's folder is an ordinary ``Config`` data folder.
"""

import html
import json
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import BinaryIO

from job_cannon import config as config_mod
from job_cannon.config import Config

REGISTRY = "profiles.json"
PROFILES_DIR = "profiles"
ENV_VAR = "JOB_CANNON_PROFILE"
JOB_SEARCH_FILE = "job-search.md"

# Job sectors a profile can pick. Each has a guide for the skills at
# .claude/sectors/<key>.md and may have starter questions in prep.SECTOR_QUESTIONS.
SECTORS = {"software": "Software engineering", "teaching": "Teaching"}


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    dir: str
    sector: str = ""  # a SECTORS key, or "" for general

    @property
    def sector_label(self) -> str:
        return SECTORS.get(self.sector, "General")

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


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save(root: Path, reg: Registry) -> None:
    data = {"active": reg.active, "profiles": [asdict(p) for p in reg.profiles]}
    _atomic_write(root / REGISTRY, json.dumps(data, indent=2) + "\n")


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


def _check_sector(sector: str) -> str:
    if sector and sector not in SECTORS:
        raise ValueError(f"Unknown sector {sector!r}")
    return sector


def create(root: Path, name: str, sector: str = "") -> Profile:
    reg = load(root)
    name = _clean_name(reg, name)
    sector = _check_sector(sector)
    taken = {p.id for p in reg.profiles}
    base = _slug(name)
    pid, n = base, 2
    while pid in taken or (root / PROFILES_DIR / pid).exists():
        pid, n = f"{base}-{n}", n + 1
    profile = Profile(pid, name, f"{PROFILES_DIR}/{pid}", sector)
    profile.config(root).ensure_dirs()
    reg.profiles.append(profile)
    save(root, reg)
    return profile


def rename(root: Path, key: str, name: str) -> Profile:
    reg = load(root)
    p = reg.find(key)
    if p is None:
        raise ValueError(f"No profile named {key!r}")
    return _replace(root, reg, replace(p, name=_clean_name(reg, name, exclude=p.id)))


def set_sector(root: Path, key: str, sector: str) -> Profile:
    reg = load(root)
    p = reg.find(key)
    if p is None:
        raise ValueError(f"No profile named {key!r}")
    return _replace(root, reg, replace(p, sector=_check_sector(sector)))


def _replace(root: Path, reg: Registry, changed: Profile) -> Profile:
    reg.profiles = [changed if q.id == changed.id else q for q in reg.profiles]
    save(root, reg)
    return changed


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


# --- job-search notes and résumé ------------------------------------------
#
# Each profile folder may hold job-search.md (résumé location plus personal
# notes, read by the Claude skills) and an uploaded resume.<ext>. Both are
# edited from the app and included in backups. A relative résumé path in the
# notes is relative to the profile folder, so the folder stays portable.

RESUME_STEM = "resume"
RESUME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
MAX_RESUME_BYTES = 20 * 1024 * 1024
MAX_NOTES_CHARS = 50_000

SECTOR_NOTE_HINTS = {
    "": "What the résumé doesn't say: where you want to work (towns, remote), contract preferences, roles to avoid, "
        "salary floor, work permits, languages.",
    "software": "What the résumé doesn't say: the stack and domains you want to focus on, remote terms and regions "
                "(e.g. remote across Europe), contract vs. employee, salary floor, citizenship or work permits.",
    "teaching": "What the résumé doesn't say: subjects and classi di concorso (e.g. A022), school levels, whether you "
                "have the abilitazione, whether you're in the GPS and for which province, how far you'll commute, "
                "state schools vs. private or international ones, languages you teach in.",
}

_HEADER = """# Job search profile

Read by the Job Cannon skills (find-jobs, tailor-cover-letter, answer-application-question).
Edit it in the app (profile menu → Profile settings), or by hand.
"""


@dataclass(frozen=True)
class JobSearch:
    resume: str = ""
    notes: str = ""
    extra: str = ""  # other "## " sections, kept as written


def _section_key(title: str) -> str:
    return title.strip().lower().replace("é", "e")


def read_job_search(path: Path) -> JobSearch:
    """Parse job-search.md into its Résumé and Notes sections (empty if missing)."""
    if not path.is_file():
        return JobSearch()
    sections: list[tuple[str, list[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    found = {"resume": "", "notes": ""}
    extra = []
    for title, lines in sections:
        body = "\n".join(lines).strip()
        key = _section_key(title)
        if key in found and not found[key]:
            found[key] = body
        else:
            extra.append(f"## {title}\n\n{body}".rstrip())
    return JobSearch(found["resume"], found["notes"], "\n\n".join(extra))


def write_job_search(path: Path, resume: str, notes: str, extra: str = "") -> JobSearch:
    resume = " ".join(resume.split())
    notes = notes.replace("\r\n", "\n").strip()
    if len(resume) > 2000 or len(notes) > MAX_NOTES_CHARS:
        raise ValueError("That's too long to save")
    if notes.startswith("## ") or "\n## " in notes:
        raise ValueError("Notes can't contain '## ' headings (they would split the file into sections)")
    parts = [_HEADER, f"## Résumé\n\n{resume}".rstrip(), f"## Notes\n\n{notes}".rstrip()]
    if extra.strip():
        parts.append(extra.strip())
    _atomic_write(path, "\n\n".join(p.strip("\n") for p in parts) + "\n")
    return JobSearch(resume, notes, extra.strip())


def resume_file(data_dir: Path) -> Path | None:
    for ext in RESUME_TYPES:
        candidate = data_dir / f"{RESUME_STEM}{ext}"
        if candidate.is_file():
            return candidate
    return None


def save_resume(data_dir: Path, filename: str, stream: BinaryIO) -> str:
    """Store an uploaded résumé as resume<ext>, replacing any earlier one. Returns the stored name."""
    ext = Path(filename or "").suffix.lower()
    if ext not in RESUME_TYPES:
        raise ValueError("Upload a PDF, Word (.docx), OpenDocument (.odt), text or Markdown file")
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / f"{RESUME_STEM}.upload.tmp"
    size = 0
    with tmp.open("wb") as out:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_RESUME_BYTES:
                out.close()
                tmp.unlink(missing_ok=True)
                raise ValueError("That file is over 20 MB")
            out.write(chunk)
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise ValueError("That file is empty")
    delete_resume(data_dir)
    stored = f"{RESUME_STEM}{ext}"
    os.replace(tmp, data_dir / stored)
    return stored


def delete_resume(data_dir: Path) -> str | None:
    """Remove the uploaded résumé, if any; returns the name it had."""
    existing = resume_file(data_dir)
    if existing is None:
        return None
    existing.unlink()
    return existing.name


def profile_files(data_dir: Path) -> list[Path]:
    """Files besides the database and files/ that belong to a profile (for backups)."""
    found = [data_dir / JOB_SEARCH_FILE, resume_file(data_dir)]
    return [f for f in found if f is not None and f.is_file()]


def resolve_resume(data_dir: Path, value: str) -> str | None:
    """The Résumé field as a URL, or an absolute path (relative ones are against the profile folder)."""
    value = value.strip()
    if not value:
        return None
    if re.match(r"https?://", value, re.IGNORECASE):
        return value
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else (data_dir / path).resolve())


def resume_text(path: Path) -> str:
    """Plain text of a .docx, .odt, .txt or .md résumé (PDFs are read directly by the skills)."""
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".docx":
        xml_name, para_end = "word/document.xml", r"</w:p>"
    elif ext == ".odt":
        xml_name, para_end = "content.xml", r"</text:p>|</text:h>"
    else:
        raise ValueError(f"Can't extract text from {ext or 'this'} files")
    with zipfile.ZipFile(path) as zf:
        xml = zf.read(xml_name).decode("utf-8")
    paragraphs = []
    for chunk in re.split(para_end, xml):
        if ext == ".docx":
            # Only text runs (<w:t>) carry content; tabs and breaks become runs too.
            chunk = re.sub(r"<w:tab\b[^>]*/>", "<w:t> </w:t>", chunk)
            chunk = re.sub(r"<w:br\b[^>]*/>", "<w:t>\n</w:t>", chunk)
            text = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", chunk))
        else:
            chunk = re.sub(r"<text:(?:tab|s)\b[^>]*/>", " ", chunk)
            chunk = re.sub(r"<text:line-break\b[^>]*/>", "\n", chunk)
            text = re.sub(r"<[^>]+>", "", chunk)
        paragraphs.append(html.unescape(text).strip())
    return "\n".join(p for p in paragraphs if p)
