"""The `carl` command: `serve` runs the server, `hash-password` makes an access pass."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .gate import MIN_PASS_LENGTH, GateError, Passes, generate_passphrase, hash_password
from .prompts import PromptError, load_prompts
from .storage import make_store


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

    from . import devsource, examples, owner

    owner.add_parser(sub)
    examples.add_parser(sub)
    devsource.add_parser(sub)

    args = parser.parse_args(argv)
    if hasattr(args, "run"):
        return args.run(args)
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
    # The first line: how much of a cold start is Scaleway's and how much Carl's.
    logging.getLogger(__name__).info("starting")
    try:
        config = load_config(args.config)
        prompts = load_prompts(args.prompts)
        passes = Passes.from_env()
        if not os.environ.get("SONIOX_API_KEY"):
            raise ConfigError("SONIOX_API_KEY not set: Carl can't hear without speech-to-text")
        store = make_store()
    except (ConfigError, PromptError, GateError, RuntimeError) as e:
        print(f"carl: can't start: {e}", file=sys.stderr)
        return 2

    from aiohttp import web

    from .server import create_app
    from .session import Sessions
    from .stt import make_speech_to_text

    stt = make_speech_to_text(config.stages.speech_to_text, os.environ)
    sessions = Sessions(config, prompts, store, stt, commit())
    from . import checks, decision, location, settle

    try:
        decision.install(sessions, os.environ)
        location.install(sessions, os.environ)
        checks.install(sessions, os.environ)
        settle.install(sessions)
    except (ValueError, PromptError) as e:
        print(f"carl: can't start: {e}", file=sys.stderr)
        return 2

    logging.getLogger(__name__).info(
        "commit %s, config %s, prompts %s, store %s",
        sessions.commit,
        config.version,
        ", ".join(f"{p.name} {p.version}" for p in prompts.values()) or "none yet",
        type(store).__name__,
    )
    web.run_app(create_app(config, prompts, passes, sessions), host=args.host, port=args.port, print=None)
    return 0


def commit() -> str:
    """The build's git commit: baked into the image, or read from the checkout."""
    if os.environ.get("CARL_COMMIT"):
        return os.environ["CARL_COMMIT"]
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5).stdout
        return out.stdout.strip() + ("-dirty" if dirty.strip() else "") if out.returncode == 0 else "unknown"
    except OSError:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
