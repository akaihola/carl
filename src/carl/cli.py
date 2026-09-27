"""The `carl` command: `serve` runs the server, `hash-password` makes an access pass."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .gate import MIN_PASS_LENGTH, GateError, Passes, generate_passphrase, hash_password
from .prompts import PromptError, load_prompts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="carl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the server: the page, the WebSocket and the API")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (default: %(default)s)")
    serve.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", 8080)), help="port (default: $PORT or 8080)"
    )
    serve.add_argument("--config", type=Path, default=Path("config.toml"), help="the config file")
    serve.add_argument("--prompts", type=Path, default=Path("prompts"), help="the prompts folder")

    pw = sub.add_parser(
        "hash-password", help="make a CARL_PASSWORDS entry for an access pass, generating a passphrase if none is given"
    )
    pw.add_argument("password", nargs="?", help="the access pass (default: a new four-word passphrase)")

    args = parser.parse_args(argv)
    if args.command == "hash-password":
        password = args.password or generate_passphrase()
        if len(password) < MIN_PASS_LENGTH:
            parser.error(f"an access pass must be at least {MIN_PASS_LENGTH} characters")
        print(f"access pass: {password}")
        print(f"entry:       {hash_password(password)}")
        print("Add the entry to the CARL_PASSWORDS secret (comma-separated, one entry per access pass).")
        return 0
    return serve_command(args)


def serve_command(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
        prompts = load_prompts(args.prompts)
        passes = Passes.from_env()
    except (ConfigError, PromptError, GateError) as e:
        print(f"carl: can't start: {e}", file=sys.stderr)
        return 2

    from aiohttp import web

    from .server import create_app

    logging.getLogger(__name__).info(
        "commit %s, config %s, prompts %s",
        os.environ.get("CARL_COMMIT", "unknown"),
        config.version,
        ", ".join(f"{p.name} {p.version}" for p in prompts.values()) or "none yet",
    )
    web.run_app(create_app(config, prompts, passes), host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
