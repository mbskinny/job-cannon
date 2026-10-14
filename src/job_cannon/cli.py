"""Command line entry point: ``job-cannon [serve|backup]``."""

import argparse
import socket
import tempfile
import threading
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from job_cannon import config as config_mod
from job_cannon import db
from job_cannon.config import DB_NAME, FILES_DIR, Config


def serve(cfg: Config, host: str, port: int, open_browser: bool) -> None:
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

    app = create_app(cfg)
    url = f"http://{host}:{port}/"
    print(f"Job Cannon data folder: {cfg.data_dir}")
    print(f"Serving at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


def backup(cfg: Config, out_dir: Path) -> Path:
    """Zip the database (consistent snapshot) and all attachments."""
    if not cfg.db_path.exists():
        raise SystemExit(f"No database found at {cfg.db_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = out_dir / f"jobcannon-backup-{stamp}.zip"
    conn = db.connect(cfg.db_path)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / DB_NAME
            db.backup_to(conn, snapshot)
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(snapshot, DB_NAME)
                if cfg.files_dir.exists():
                    for f in sorted(cfg.files_dir.iterdir()):
                        if f.is_file():
                            zf.write(f, f"{FILES_DIR}/{f.name}")
    finally:
        conn.close()
    return dest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="job-cannon", description="Local job-search manager.")
    parser.add_argument(
        "--data-dir",
        help=f"data folder (default: ${config_mod.ENV_VAR} or {config_mod.DEFAULT_DIR})",
    )
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="run the app (default)")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--no-browser", action="store_true", help="don't open a browser tab")

    p_backup = sub.add_parser("backup", help="write a .zip of the data folder")
    p_backup.add_argument("--out", type=Path, default=Path.cwd(), help="where to write the zip")

    # Accept --data-dir after the subcommand too (job-cannon serve --data-dir X).
    for p in (p_serve, p_backup):
        p.add_argument("--data-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    cfg = config_mod.resolve(args.data_dir)

    if args.command == "backup":
        print(backup(cfg, args.out))
    else:
        serve(
            cfg,
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
            open_browser=not getattr(args, "no_browser", False),
        )


if __name__ == "__main__":
    main()
