"""LivingColor Server CLI entry — desktop backend launcher."""

from __future__ import annotations

import argparse
import os
import sys


def _cmd_dashboard(args: argparse.Namespace) -> int:
    os.environ.setdefault("LIVINGCOLOR_API_ONLY", "1")

    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:
        print("LivingColor Server requires fastapi and uvicorn.")
        print(f"Install with: {sys.executable} -m pip install -e .")
        print(f"Import error: {exc}")
        return 1

    if "HERMES_WEB_DIST" not in os.environ:
        os.environ["HERMES_WEB_DIST"] = os.path.join(
            os.path.dirname(__file__), "..", "hermes_cli", "web_dist"
        )

    try:
        from hermes_cli.plugins import discover_plugins

        discover_plugins()
    except Exception as exc:
        print(f"Plugin discovery warning: {exc}", file=sys.stderr)

    from lc_server.server import start_server

    start_server(
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
        allow_public=args.insecure,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="livingcolor-server", description="LivingColor Server")
    sub = parser.add_subparsers(dest="command", required=True)

    dash = sub.add_parser("dashboard", help="Start the LivingColor API server")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=9119)
    dash.add_argument("--no-open", action="store_true", dest="no_open")
    dash.add_argument("--insecure", action="store_true", help="Allow public bind without auth gate")
    dash.set_defaults(func=_cmd_dashboard)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
