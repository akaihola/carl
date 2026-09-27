import json
import random
import wave

import pytest
from botocore.stub import Stubber

from carl import cli, owner
from carl.owner import OwnerError
from carl.recording import Recorder
from carl.storage import BucketStore, FolderStore, MemoryStore

ENDED = "20260927T180211Z-a1b2c3"  # ended, with a corpus file
NEIGHBOUR = "20260927T180211Z-a1b2c4"  # started the same second
RUNNING = "20260920T170000Z-0f0f0f"  # no end event, no corpus file
CORPUS_ONLY = "20260301T120000Z-cccccc"  # its recording has expired


def pcm(seconds: float, seed: int) -> bytes:
    return random.Random(seed).randbytes(int(seconds * owner.BYTES_PER_S))


def jsonl(*events: dict) -> bytes:
    return b"".join(json.dumps(e).encode() + b"\n" for e in events)


def start(time: str) -> dict:
    return {"time": time, "event": "session start", "record": True, "commit": "abc123", "config": "…", "mic": {}}


@pytest.fixture
def store() -> MemoryStore:
    store = MemoryStore()
    ended = f"recordings/{ENDED}/"
    store.objects = {
        # Written out of order: the export must sort them.
        ended + "audio/000002.pcm": pcm(0.5, 2),
        ended + "audio/000001.pcm": pcm(1, 1),
        ended + "events/000001.jsonl": jsonl(
            start("2026-09-27T18:02:11.000Z"),
            {"time": "2026-09-27T18:03:12.000Z", "event": "audio", "key": "audio/000001.pcm", "bytes": 32000},
        ),
        # A part that lacks its final newline.
        ended + "events/000002.jsonl": json.dumps(
            {"time": "2026-09-27T18:03:46.000Z", "event": "session end", "listening_s": 95.0}
        ).encode(),
        # The last audio object's event, written at close after the end.
        ended + "events/000003.jsonl": jsonl(
            {"time": "2026-09-27T18:03:46.001Z", "event": "audio", "key": "audio/000002.pcm", "bytes": 16000},
        ),
        f"corpus/{ENDED}.md": b"# Session\n\nS1: Helsinki was founded in 1550.\n",
        f"recordings/{NEIGHBOUR}/audio/000001.pcm": pcm(0.25, 3),
        f"recordings/{NEIGHBOUR}/events/000001.jsonl": jsonl(
            start("2026-09-27T18:02:11Z"),
            {"time": "2026-09-27T18:02:20Z", "event": "session end", "listening_s": 9.0},
        ),
        f"corpus/{NEIGHBOUR}.md": b"# Another\n",
        f"recordings/{RUNNING}/audio/000001.pcm": pcm(3, 4),
        f"recordings/{RUNNING}/events/000001.jsonl": jsonl(start("2026-09-20T17:00:00Z")),
        f"corpus/{CORPUS_ONLY}.md": b"# Kept\n",
        # Not a recording session's, and never touched.
        f"sessions/{ENDED}/state.json": b"{}",
        f"dev/recordings/{ENDED}/audio/000001.pcm": pcm(0.1, 5),
        "costs/month-2026-09.json": b"{}",
        "failures/2026-09-27.jsonl": b"{}\n",
    }
    return store


def kept(store: MemoryStore, session_id: str) -> int:
    return sum(len(v) for k, v in store.objects.items()
               if k.startswith(f"recordings/{session_id}/") or k == f"corpus/{session_id}.md")


def row(out: str, session_id: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(session_id))


async def test_list_shows_sessions_newest_first_with_start_duration_and_size(store, capsys):
    assert await owner.list_sessions(store) == 0
    out = capsys.readouterr().out
    ids = [line.split()[0] for line in out.splitlines()[1:5]]
    assert ids == [NEIGHBOUR, ENDED, RUNNING, CORPUS_ONLY]
    ended = row(out, ENDED)
    assert "2026-09-27 21:02" in ended  # Helsinki summer time
    assert "0:01:35" in ended  # the end event's listening time
    assert owner.human_size(kept(store, ENDED)) in ended
    assert ended.endswith("corpus")
    running = row(out, RUNNING)
    assert "2026-09-20 20:00" in running
    assert "~0:00:03" in running  # no end event: the audio kept, 96,000 bytes
    assert running.endswith("no end event")
    corpus_only = row(out, CORPUS_ONLY)
    assert "2026-03-01 14:00" in corpus_only and corpus_only.endswith("corpus only")
    assert "4 sessions" in out
    assert "~ no end event" in out
    assert "dev/" not in out and "sessions/" not in out


async def test_list_says_when_there_are_none(capsys):
    assert await owner.list_sessions(MemoryStore()) == 0
    assert capsys.readouterr().out == "No recording sessions.\n"


async def test_export_writes_a_playable_wav_the_event_log_and_the_corpus(store, tmp_path, capsys):
    before = dict(store.objects)
    assert await owner.export(store, ENDED, tmp_path) == 0
    folder = tmp_path / ENDED
    assert sorted(p.name for p in folder.iterdir()) == ["audio.wav", "corpus.md", "events.jsonl"]

    audio = before[f"recordings/{ENDED}/audio/000001.pcm"] + before[f"recordings/{ENDED}/audio/000002.pcm"]
    with wave.open(str(folder / "audio.wav"), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        assert wav.getcomptype() == "NONE"
        assert wav.getnframes() == 24000
        assert wav.readframes(wav.getnframes()) == audio

    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["session start", "audio", "session end", "audio"]
    assert (folder / "corpus.md").read_bytes() == before[f"corpus/{ENDED}.md"]

    out = capsys.readouterr().out
    assert str(folder.resolve()) in out
    assert "audio.wav     0:00:02 of audio from 2 objects" in out
    assert "events.jsonl  4 events from 3 parts" in out
    assert "corpus.md" in out
    assert store.objects == before


async def test_export_without_a_corpus_file_or_an_end_event(store, tmp_path, capsys):
    store.objects[f"recordings/{RUNNING}/extra/note.txt"] = b"kept as it is"
    assert await owner.export(store, RUNNING, tmp_path) == 0
    folder = tmp_path / RUNNING
    assert sorted(p.name for p in folder.iterdir()) == ["audio.wav", "events.jsonl", "extra"]
    assert (folder / "extra" / "note.txt").read_bytes() == b"kept as it is"
    with wave.open(str(folder / "audio.wav"), "rb") as wav:
        assert wav.getnframes() == 48000
        assert wav.readframes(48000) == store.objects[f"recordings/{RUNNING}/audio/000001.pcm"]
    assert "no corpus Markdown" in capsys.readouterr().out


async def test_export_of_a_corpus_only_session(store, tmp_path):
    assert await owner.export(store, CORPUS_ONLY, tmp_path) == 0
    assert [p.name for p in (tmp_path / CORPUS_ONLY).iterdir()] == ["corpus.md"]


async def test_export_of_an_unknown_session_writes_nothing(store, tmp_path):
    with pytest.raises(OwnerError, match="nothing is kept"):
        await owner.export(store, "20260101T000000Z-000000", tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_delete_removes_the_session_and_nothing_else(store, capsys):
    before = dict(store.objects)
    gone = {k for k in before if k.startswith(f"recordings/{ENDED}/")} | {f"corpus/{ENDED}.md"}
    assert await owner.delete(store, ENDED, yes=True) == 0
    assert store.objects == {k: v for k, v in before.items() if k not in gone}
    out = capsys.readouterr().out
    assert out == f"Deleted 6 objects: recordings/{ENDED}/ (5 objects) and corpus/{ENDED}.md.\n"


async def test_delete_asks_first(store, monkeypatch, capsys):
    before = dict(store.objects)
    prompts = []
    answers = iter(["", "n", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or next(answers))

    assert await owner.delete(store, RUNNING) == 1
    assert await owner.delete(store, RUNNING) == 1
    assert store.objects == before
    out = capsys.readouterr().out
    assert "started 2026-09-20 20:00 Helsinki time, ~0:00:03 long" in out
    assert "may still be running" in out
    assert out.count("Nothing deleted.") == 2
    assert prompts[0] == f"Delete recordings/{RUNNING}/ (2 objects) for good? [y/N] "

    assert await owner.delete(store, RUNNING) == 0
    assert not any(RUNNING in k for k in store.objects)
    assert len(store.objects) == len(before) - 2


async def test_delete_of_a_corpus_only_session(store):
    assert await owner.delete(store, CORPUS_ONLY, yes=True) == 0
    assert f"corpus/{CORPUS_ONLY}.md" not in store.objects


async def test_delete_of_an_unknown_session_deletes_nothing(store):
    before = dict(store.objects)
    with pytest.raises(OwnerError, match="nothing is kept"):
        await owner.delete(store, "20260101T000000Z-000000", yes=True)
    assert store.objects == before


async def test_a_recorders_recording_lists_exports_and_deletes(tmp_path, capsys):
    store = MemoryStore()
    recorder = Recorder(store, ENDED)
    recorder.log("session start", record=True)
    first, second = pcm(1, 1), pcm(0.5, 2)
    recorder.audio(first)
    recorder.audio_break()  # a Pause
    recorder.audio(second)
    recorder.log("session end", listening_s=95.0)
    await recorder.flush()  # so the last audio object's event gets a part of its own
    await recorder.close()

    await owner.list_sessions(store)
    listed = row(capsys.readouterr().out, ENDED)
    assert "0:01:35" in listed and "no end event" not in listed

    await owner.export(store, ENDED, tmp_path)
    with wave.open(str(tmp_path / ENDED / "audio.wav"), "rb") as wav:
        assert wav.readframes(wav.getnframes()) == first + second
    events = [json.loads(line) for line in (tmp_path / ENDED / "events.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["session start", "audio", "session end", "audio"]

    await owner.delete(store, ENDED, yes=True)
    assert store.objects == {}


BAD_IDS = [
    "20260927T180211Z-a1b2c",  # a typo that would be a wider prefix
    "20260927T180211Z",
    "2026",
    "",
    f"{ENDED}/",
    f"{ENDED}/../{RUNNING}",
    "20260927T180211Z-A1B2C3",
    f"{ENDED}\n",
    "20261327T180211Z-a1b2c3",  # no 13th month
    "*",
]


@pytest.mark.parametrize("bad", BAD_IDS)
async def test_a_bad_id_is_refused(store, tmp_path, bad):
    before = dict(store.objects)
    with pytest.raises(OwnerError, match="not a session id"):
        await owner.delete(store, bad, yes=True)
    with pytest.raises(OwnerError, match="not a session id"):
        await owner.export(store, bad, tmp_path)
    assert store.objects == before
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def opened(store, monkeypatch) -> list[bool]:
    """`carl owner …` through the CLI, with the in-memory store; records each `--dev`."""
    devs: list[bool] = []
    monkeypatch.setattr(owner, "open_store", lambda dev: devs.append(dev) or store)
    return devs


def test_the_cli_runs_the_commands(store, opened, tmp_path, capsys):
    assert cli.main(["owner", "list", "--dev"]) == 0
    assert ENDED in capsys.readouterr().out
    assert cli.main(["owner", "export", ENDED, "--out", str(tmp_path)]) == 0
    assert (tmp_path / ENDED / "audio.wav").is_file()
    assert cli.main(["owner", "delete", ENDED, "--yes"]) == 0
    assert not any(ENDED in k for k in store.objects if not k.startswith(("sessions/", "dev/")))
    assert opened == [True, False, False]


def test_the_cli_refuses_a_bad_id(store, opened, capsys):
    before = dict(store.objects)
    assert cli.main(["owner", "delete", "20260927T180211Z-a1b2c", "--yes"]) == 1
    assert "carl owner: not a session id" in capsys.readouterr().err
    assert store.objects == before


def test_the_bucket_key_comes_from_the_secrets_file_with_the_environment_winning(tmp_path):
    secrets = tmp_path / ".secrets.bucket.env"
    secrets.write_text("# the bucket key\nS3_ACCESS_KEY=from-file\nexport S3_SECRET_KEY='secret'\nS3_BUCKET=b\n")
    env = owner.bucket_env(secrets, {"S3_ACCESS_KEY": "from-env"})
    assert env == {"S3_ACCESS_KEY": "from-env", "S3_SECRET_KEY": "secret", "S3_BUCKET": "b"}
    assert owner.bucket_env(tmp_path / "missing", {"X": "1"}) == {"X": "1"}


def test_the_store_is_the_clouds_or_dev_whatever_carl_cloud_says():
    env = {"S3_ACCESS_KEY": "k", "S3_SECRET_KEY": "s", "S3_BUCKET": "b", "CARL_CLOUD": "1"}
    cloud, dev = owner.open_store(False, env), owner.open_store(True, env)
    assert isinstance(cloud, BucketStore) and (cloud.bucket, cloud.prefix) == ("b", "")
    assert isinstance(dev, BucketStore) and dev.prefix == "dev/"
    folder = owner.open_store(True, {})
    assert isinstance(folder, FolderStore) and folder.root.name == ".carl-store"
    with pytest.raises(OwnerError, match="no bucket key"):
        owner.open_store(False, {"S3_ACCESS_KEY": "k"})


async def test_sizes_come_from_the_bucket_listing_without_downloading():
    store = owner.open_store(True, {"S3_ACCESS_KEY": "k", "S3_SECRET_KEY": "s", "S3_BUCKET": "b"})
    listing = {"Contents": [{"Key": f"dev/recordings/{ENDED}/audio/000001.pcm", "Size": 1_920_000}], "IsTruncated": False}
    with Stubber(store.s3) as stub:
        stub.add_response("list_objects_v2", listing, {"Bucket": "b", "Prefix": "dev/recordings/"})
        assert await owner.sizes(store, "recordings/") == {f"recordings/{ENDED}/audio/000001.pcm": 1_920_000}
        stub.assert_no_pending_responses()


async def test_sizes_in_a_folder_store(store, tmp_path):
    folder = FolderStore(tmp_path)
    for key in [k for k in store.objects if k.startswith(f"recordings/{ENDED}/")]:
        await folder.put(key, store.objects[key])
    assert await owner.sizes(folder, "recordings/") == await owner.sizes(store, f"recordings/{ENDED}/")
