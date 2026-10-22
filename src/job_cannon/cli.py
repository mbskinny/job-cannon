"""Command line entry point: ``job-cannon [serve|backup|profiles]``."""

import argparse
import json
import os
import socket
import tempfile
import threading
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from job_cannon import config as config_mod
from job_cannon import db, profiles
from job_cannon.config import DB_NAME, FILES_DIR, Config


def serve(root: Path, profile: str | None, host: str, port: int, open_browser: bool) -> None:
    import uvicorn

    from job_cannon.web.app import create_app

    # Check before opening a browser tab, which would otherwise land on
    # whatever else is already serving this port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            raise SystemExit(
                f"Port {port} is already in use (is Job Cannon already running?).\n"
                f"Stop the other copy, or pick another port: job-cannon serve --port {port + 1}"
            )

    app = create_app(root, profile)
    url = f"http://{host}:{port}/"
    active = app.state.profiles[app.state.active]
    print(f"Job Cannon data folder: {root}")
    print(f"Profile: {active.name} ({active.config(root).data_dir})")
    print(f"Serving at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


def backup(cfg: Config, out_dir: Path, label: str | None = None) -> Path:
    """Zip the database (consistent snapshot), all attachments and the job-search notes.

    ``label`` (a profile id) goes in the file name, for one zip per profile.
    """
    if not cfg.db_path.exists():
        raise SystemExit(f"No database found at {cfg.db_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = out_dir / f"jobcannon-backup-{label + '-' if label else ''}{stamp}.zip"
    conn = db.connect(cfg.db_path)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / DB_NAME
            db.backup_to(conn, snapshot)
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(snapshot, DB_NAME)
                notes = cfg.data_dir / profiles.JOB_SEARCH_FILE
                if notes.is_file():
                    zf.write(notes, profiles.JOB_SEARCH_FILE)
                if cfg.files_dir.exists():
                    for f in sorted(cfg.files_dir.iterdir()):
                        if f.is_file():
                            zf.write(f, f"{FILES_DIR}/{f.name}")
    finally:
        conn.close()
    return dest


def profile_info(root: Path, profile: profiles.Profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "sector": profile.sector,
        "sector_label": profile.sector_label,
        "data_dir": str(profile.config(root).data_dir),
        "job_search_file": str(profile.job_search_file(root)),
    }


def profiles_command(root: Path, selected: profiles.Profile, args) -> None:
    if args.action == "use":
        if not args.name:
            raise SystemExit("usage: job-cannon profiles use NAME")
        try:
            p = profiles.set_active(root, args.name)
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(f"Active profile: {p.name}. A running app picks this up after a restart.")
    elif args.action == "sector":
        if not args.name or args.value is None:
            choices = ", ".join(profiles.SECTORS)
            raise SystemExit(f"usage: job-cannon profiles sector NAME SECTOR  (one of: {choices}, or '' for general)")
        try:
            p = profiles.set_sector(root, args.name, args.value)
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(f"{p.name}: {p.sector_label}")
    elif args.json:
        print(json.dumps(profile_info(root, selected), indent=2))
    else:
        reg = profiles.load(root)
        for p in reg.profiles:
            mark = "*" if p.id == reg.active else " "
            print(f"{mark} {p.id}\t{p.name}\t{p.sector_label}\t{p.config(root).data_dir}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="job-cannon", description="Local job-search manager.")
    parser.add_argument(
        "--data-dir",
        help=f"data folder (default: ${config_mod.ENV_VAR} or {config_mod.DEFAULT_DIR})",
    )
    parser.add_argument("--profile", help=f"profile name or id (default: ${profiles.ENV_VAR} or the active one)")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="run the app (default)")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--no-browser", action="store_true", help="don't open a browser tab")

    p_backup = sub.add_parser("backup", help="write a .zip of the data folder")
    p_backup.add_argument("--out", type=Path, default=Path.cwd(), help="where to write the zip")
    p_backup.add_argument("--all", action="store_true", help="one zip per profile")

    p_profiles = sub.add_parser(
        "profiles", help="list profiles; switch with: profiles use NAME; set a sector with: profiles sector NAME SECTOR"
    )
    p_profiles.add_argument("action", nargs="?", choices=["list", "use", "sector"], default="list")
    p_profiles.add_argument("name", nargs="?")
    p_profiles.add_argument("value", nargs="?")
    p_profiles.add_argument("--json", action="store_true", help="print the active (or --profile) profile as JSON")

    # Accept --data-dir and --profile after the subcommand too (job-cannon serve --data-dir X).
    for p in (p_serve, p_backup, p_profiles):
        p.add_argument("--data-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        p.add_argument("--profile", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    root = config_mod.resolve(args.data_dir).data_dir
    profile = args.profile or os.environ.get(profiles.ENV_VAR)
    try:
        selected = profiles.get(root, profile) if profile else profiles.active(root)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if args.command == "profiles":
        profiles_command(root, selected, args)
    elif args.command == "backup":
        chosen = profiles.load(root).profiles if args.all else [selected]
        for p in chosen:
            if p.config(root).db_path.exists() or not args.all:
                print(backup(p.config(root), args.out, label=p.id))
    else:
        serve(
            root,
            profile,
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
            open_browser=not getattr(args, "no_browser", False),
        )


if __name__ == "__main__":
    main()
