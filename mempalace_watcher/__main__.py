from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from threading import Event
import sys

from .desktop import run_desktop
from .service import WatcherService
from .web import build_server


def make_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="mempalace-watcher")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover")
    sub.add_parser("scan")
    sync = sub.add_parser("sync")
    sync.add_argument("--apply", action="store_true", help="Refresh stale projects after scan")
    serve = sub.add_parser("serve")
    serve.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    sub.add_parser("desktop")
    sub.add_parser("watch")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    service = WatcherService(Path(args.project_root))

    if args.command == "discover":
        projects = service.discover()
        print(f"Discovered {len(projects)} project(s).")
        return 0

    if args.command == "scan":
        results = service.scan()
        print(f"Scanned {len(results)} project(s).")
        for result in results:
            print(f"{result.status:14} {result.drift_score:3} {result.name} ({result.path})")
        return 0

    if args.command == "sync":
        results = service.rescan_all(apply_refresh=bool(args.apply))
        print(f"Synced {len(results)} project(s).")
        return 0

    if args.command == "serve":
        service.serve_dashboard(open_browser=not bool(getattr(args, "no_browser", False)))
        return 0

    if args.command == "desktop":
        run_desktop(service)
        return 0

    if args.command == "watch":
        stop_event = Event()
        try:
            service.run_loop(stop_event)
        except KeyboardInterrupt:
            stop_event.set()
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
