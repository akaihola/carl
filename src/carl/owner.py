"""The owner-only script (spec section 2, The owner-only script): `carl owner …`.

Run by the owner from their own computer with the bucket key, so the server
needs no admin route. Step 2 brings `list`, `export <id>` and `delete <id>`,
which answer access and deletion requests (spec section 9):

    carl owner list [--dev]                          # recording sessions, newest first
    carl owner export <id> [--out DIR] [--dev]       # DIR/<id>/: audio.wav, events.jsonl, corpus.md
    carl owner delete <id> [--yes] [--dev]           # recordings/<id>/ and corpus/<id>.md

The bucket key comes from the environment or the gitignored
`.secrets.bucket.env` at the repo root, the environment winning. Without
`--dev` it reads the cloud's recordings; with it, local runs' ones under
`dev/` (or in `.carl-store/` when there is no bucket key, as a local run
without one writes there).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import wave
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .storage import BucketStore, FolderStore, Store

SECRETS = Path(__file__).resolve().parents[2] / ".secrets.bucket.env"
EXPORTS = Path.home() / "carl-exports"
SESSION_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}")
SAMPLE_RATE, SAMPLE_BYTES = 16000, 2
BYTES_PER_S = SAMPLE_RATE * SAMPLE_BYTES
HELSINKI = ZoneInfo("Europe/Helsinki")


class OwnerError(Exception):
    pass


def add_parser(sub: argparse._SubParsersAction) -> None:
    owner = sub.add_parser("owner", help="the owner's recording sessions in the bucket")
    commands = owner.add_subparsers(dest="owner_command", required=True)
    where = argparse.ArgumentParser(add_help=False)
    where.add_argument("--dev", action="store_true", help="local runs' recordings, under dev/ (default: the cloud's)")
    commands.add_parser("list", parents=[where], help="recording sessions, newest first, with duration and size")
    export_ = commands.add_parser("export", parents=[where], help="download everything kept for a session")
    export_.add_argument("id", help="the session id, as `list` shows it")
    export_.add_argument("--out", type=Path, default=EXPORTS, help="where the <id>/ folder goes (default: %(default)s)")
    delete_ = commands.add_parser("delete", parents=[where], help="delete everything kept for a session, for good")
    delete_.add_argument("id", help="the session id, as `list` shows it")
    delete_.add_argument("--yes", action="store_true", help="don't ask first")
    owner.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    try:
        store = open_store(args.dev)
        if args.owner_command == "list":
            return asyncio.run(list_sessions(store))
        if args.owner_command == "export":
            return asyncio.run(export(store, args.id, args.out))
        return asyncio.run(delete(store, args.id, yes=args.yes))
    except OwnerError as e:
        print(f"carl owner: {e}", file=sys.stderr)
        return 1


def bucket_env(path: Path = SECRETS, environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """`.secrets.bucket.env`'s KEY=VALUE lines, with the environment winning."""
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.removeprefix("export ").split("=", 1)
                values[name.strip()] = value.strip().strip("'\"")
    return values | dict(environ)


def open_store(dev: bool, environ: Mapping[str, str] | None = None) -> Store:
    """The bucket with the owner's key: the cloud's objects, or with `dev` local runs' ones under `dev/`.

    Unlike `make_store`, the prefix doesn't depend on CARL_CLOUD.
    """
    env = bucket_env() if environ is None else environ
    if env.get("S3_ACCESS_KEY") and env.get("S3_SECRET_KEY"):
        return BucketStore(
            env.get("S3_BUCKET", "carl-faktat"),
            env.get("S3_ENDPOINT", "https://s3.fr-par.scw.cloud"),
            env.get("S3_REGION", "fr-par"),
            env["S3_ACCESS_KEY"],
            env["S3_SECRET_KEY"],
            "dev/" if dev else "",
        )
    if dev:
        return FolderStore(Path(".carl-store"))
    raise OwnerError("no bucket key: set S3_ACCESS_KEY and S3_SECRET_KEY, or put them in .secrets.bucket.env")


async def sizes(store: Store, prefix: str) -> dict[str, int]:
    """Every key under `prefix` with its size in bytes.

    The Store interface has no sizes, so the bucket's own listing is read, a
    folder's files are looked at, and any other store's objects are read whole.
    """
    if isinstance(store, BucketStore):
        def list_sizes() -> dict[str, int]:
            found, paginator = {}, store.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=store.bucket, Prefix=store.prefix + prefix):
                found |= {o["Key"].removeprefix(store.prefix): o["Size"] for o in page.get("Contents", [])}
            return found

        return await asyncio.to_thread(list_sizes)
    if isinstance(store, FolderStore):
        return {k: (store.root / k).stat().st_size for k in await store.list(prefix)}
    return {k: len(await store.get(k) or b"") for k in await store.list(prefix)}


def check_id(session_id: str) -> str:
    """The id, if it is a whole session id, so that a typo can't name a wider prefix."""
    if not SESSION_ID.fullmatch(session_id) or id_time(session_id) is None:
        raise OwnerError(f"not a session id: {session_id!r} (one looks like 20260927T180211Z-a1b2c3)")
    return session_id


def id_time(session_id: str) -> datetime | None:
    """When the session started, from its id."""
    try:
        return datetime.strptime(session_id[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def corpus_key(session_id: str) -> str:
    return f"corpus/{session_id}.md"


@dataclass
class Recording:
    """What the bucket keeps for one recording session."""

    id: str
    objects: dict[str, int]  # key → bytes, under recordings/<id>/
    corpus: int | None  # bytes of corpus/<id>.md, None when there is none
    started: datetime | None = None
    duration_s: float | None = None  # None when only the corpus is left
    ended: bool = False  # the log holds its `session end` event

    @property
    def prefix(self) -> str:
        return f"recordings/{self.id}/"

    @property
    def size(self) -> int:
        return sum(self.objects.values()) + (self.corpus or 0)

    def keys(self, part: str) -> list[str]:
        """The keys under `recordings/<id>/<part>/`, in order."""
        return sorted(k for k in self.objects if k.startswith(f"{self.prefix}{part}/"))


def parse_events(data: bytes | None) -> list[dict[str, Any]]:
    """A log part's events, skipping any line that isn't a JSON object."""
    events = []
    for line in (data or b"").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def event_time(event: dict[str, Any] | None) -> datetime | None:
    try:
        return datetime.fromisoformat(event["time"]) if event else None
    except (TypeError, KeyError, ValueError):
        return None


async def summarize(store: Store, session_id: str, objects: dict[str, int], corpus: int | None) -> Recording:
    """Start and duration from the first log part and the last few.

    The duration is the end event's listening time (paused time excluded) or,
    for a session with no end event, the length of the audio kept.
    """
    r = Recording(session_id, objects, corpus, started=id_time(session_id))
    if not objects:
        return r
    events = r.keys("events")
    first = parse_events(await store.get(events[0])) if events else []
    start = next((e for e in first if e.get("event") == "session start"), None)
    end = None
    for key in reversed(events[-3:]):  # the last audio object's event can follow the end in a part of its own
        part = first if key == events[0] else parse_events(await store.get(key))
        if end := next((e for e in reversed(part) if e.get("event") == "session end"), None):
            break
    r.started = r.started or event_time(start)
    r.ended = end is not None
    listening = end.get("listening_s") if end else None
    t0, t1 = event_time(start), event_time(end)
    if isinstance(listening, int | float):
        r.duration_s = float(listening)
    elif t0 and t1:
        r.duration_s = (t1 - t0).total_seconds()
    else:
        r.duration_s = sum(objects[k] for k in r.keys("audio")) / BYTES_PER_S
    return r


async def recording(store: Store, session_id: str) -> Recording:
    """What is kept for one session."""
    objects = await sizes(store, f"recordings/{session_id}/")
    corpus = (await sizes(store, corpus_key(session_id))).get(corpus_key(session_id))
    if not objects and corpus is None:
        raise OwnerError(f"nothing is kept for session {session_id}")
    return await summarize(store, session_id, objects, corpus)


async def recordings(store: Store) -> list[Recording]:
    """Every session with a recording or a corpus file, newest first."""
    by_id: dict[str, dict[str, int]] = {}
    for key, size in (await sizes(store, "recordings/")).items():
        if len(parts := key.split("/")) > 2:
            by_id.setdefault(parts[1], {})[key] = size
    corpus = {}
    for key, size in (await sizes(store, "corpus/")).items():
        if m := re.fullmatch(r"corpus/([^/]+)\.md", key):
            corpus[m[1]] = size
    found = [await summarize(store, i, by_id.get(i, {}), corpus.get(i)) for i in by_id.keys() | corpus.keys()]
    return sorted(found, key=lambda r: (r.started or datetime.min.replace(tzinfo=UTC), r.id), reverse=True)


def clock(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def count(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' * (n != 1)}"


def human_size(n: int) -> str:
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= scale:
            return f"{n / scale:.1f} {unit}"
    return f"{n} B"


def describe(r: Recording) -> tuple[str, str, str, str, str]:
    """A `list` row: id, start in Helsinki time, duration, size and notes."""
    started = r.started.astimezone(HELSINKI).strftime("%Y-%m-%d %H:%M") if r.started else "?"
    duration = "–" if r.duration_s is None else ("" if r.ended else "~") + clock(r.duration_s)
    if not r.objects:
        notes = "corpus only"
    else:
        notes = ", ".join(n for n, on in (("no end event", not r.ended), ("corpus", r.corpus is not None)) if on)
    return r.id, started, duration, human_size(r.size), notes


async def list_sessions(store: Store) -> int:
    """Print the recording sessions as a table, newest first."""
    found = await recordings(store)
    if not found:
        print("No recording sessions.")
        return 0
    rows = [("session", "started (Helsinki)", "duration", "size", ""), *map(describe, found)]
    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    for row in rows:
        cells = [c.rjust(w) if i in (2, 3) else c.ljust(w) for i, (c, w) in enumerate(zip(row, widths))]
        print("  ".join(cells).rstrip())
    print(f"{count(len(found), 'session')}, {human_size(sum(r.size for r in found))}")
    if any(r.objects and not r.ended for r in found):
        print("~ no end event: the length of the audio kept. The session may still be running, or the server stopped.")
    return 0


async def fetch(store: Store, keys: list[str], batch: int = 8) -> AsyncIterator[bytes]:
    """Each object in order, fetching a few at a time."""
    for i in range(0, len(keys), batch):
        for data in await asyncio.gather(*(store.get(k) for k in keys[i : i + batch])):
            yield data or b""


async def export(store: Store, session_id: str, out: Path) -> int:
    """Download everything kept for a session to `out/<id>/`, for an access request.

    `audio.wav` is every audio object joined in order, `events.jsonl` every
    log part, and `corpus.md` the corpus Markdown. Anything else under
    `recordings/<id>/` is copied as it is.
    """
    r = await recording(store, check_id(session_id))
    folder = out.expanduser() / r.id
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Session {r.id} → {folder.resolve()}/")
    audio, events = r.keys("audio"), r.keys("events")
    if audio:
        with wave.open(str(folder / "audio.wav"), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(SAMPLE_BYTES)
            wav.setframerate(SAMPLE_RATE)
            async for data in fetch(store, audio):
                wav.writeframes(data)
            frames = wav.getnframes()
        size = (folder / "audio.wav").stat().st_size
        print(f"  audio.wav     {clock(frames / SAMPLE_RATE)} of audio from {count(len(audio), 'object')}, {human_size(size)}")
    if events:
        lines = 0
        with (folder / "events.jsonl").open("wb") as f:
            async for part in fetch(store, events):
                f.write(part if not part or part.endswith(b"\n") else part + b"\n")
                lines += sum(1 for line in part.splitlines() if line.strip())
        print(f"  events.jsonl  {count(lines, 'event')} from {count(len(events), 'part')}")
    for key in sorted(set(r.objects) - set(audio) - set(events)):
        target = folder / key.removeprefix(r.prefix)
        if not target.resolve().is_relative_to(folder.resolve()):
            raise OwnerError(f"{key} points outside {folder}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(await store.get(key) or b"")
        print(f"  {target.relative_to(folder)}  {human_size(target.stat().st_size)}")
    if r.corpus is not None:
        (folder / "corpus.md").write_bytes(await store.get(corpus_key(r.id)) or b"")
        print("  corpus.md     the corpus Markdown")
    else:
        print("  (no corpus Markdown for this session)")
    return 0


async def delete(store: Store, session_id: str, *, yes: bool = False) -> int:
    """Remove `recordings/<id>/` and `corpus/<id>.md`, asking first unless `yes`."""
    r = await recording(store, check_id(session_id))
    what = [f"{r.prefix} ({count(len(r.objects), 'object')})"] if r.objects else []
    what += [corpus_key(r.id)] if r.corpus is not None else []
    if not yes:
        _, started, duration, size, _ = describe(r)
        print(f"Session {r.id}: started {started} Helsinki time, {duration} long, {size}.")
        if r.objects and not r.ended:
            print("It has no end event, so it may still be running: stop its recording in Carl first.")
        try:
            answer = input(f"Delete {' and '.join(what)} for good? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("Nothing deleted.")
            return 1
    n = await store.delete_prefix(r.prefix) if r.objects else 0
    if r.corpus is not None:
        n += await store.delete_prefix(corpus_key(r.id))
    left = await store.list(r.prefix) + [k for k in await store.list(corpus_key(r.id)) if k == corpus_key(r.id)]
    if left:
        raise OwnerError(f"deleted {count(n, 'object')}, but {len(left)} are still there, such as {left[0]}")
    print(f"Deleted {count(n, 'object')}: {' and '.join(what)}.")
    return 0
