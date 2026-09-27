"""Where the server keeps things (spec section 2, Storage).

One Object Storage bucket holds everything: `recordings/`, `corpus/`,
`sessions/`, `failures/` and `costs/`. Local runs write under `dev/` in the
same bucket, or to a local folder when no bucket key is at hand. Keys are
always given without the `dev/` prefix; the store adds it.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class Store(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes | None:
        """The object, or None if there is none."""
    async def list(self, prefix: str) -> list[str]:
        """Every key under `prefix`, sorted."""
    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object under `prefix`; return how many there were."""


class MemoryStore:
    """For tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = bytes(data)

    async def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    async def list(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list(prefix)
        for key in keys:
            del self.objects[key]
        return len(keys)


class FolderStore:
    """A local folder standing in for the bucket, for runs without a bucket key."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"key outside the store: {key!r}")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return await asyncio.to_thread(path.read_bytes) if path.is_file() else None

    async def list(self, prefix: str) -> list[str]:
        if not self.root.exists():
            return []
        keys = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        return sorted(k for k in keys if k.startswith(prefix))

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list(prefix)
        for key in keys:
            self._path(key).unlink()
        return len(keys)


class BucketStore:
    """The Scaleway Object Storage bucket, through boto3 off the event loop."""

    def __init__(self, bucket: str, endpoint: str, region: str, access_key: str, secret_key: str, prefix: str = ""):
        import boto3

        self.bucket, self.prefix = bucket, prefix
        self.s3 = boto3.client(
            "s3", endpoint_url=endpoint, region_name=region,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
        )

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.s3.put_object, Bucket=self.bucket, Key=self.prefix + key, Body=data)

    async def get(self, key: str) -> bytes | None:
        def get() -> bytes | None:
            try:
                return self.s3.get_object(Bucket=self.bucket, Key=self.prefix + key)["Body"].read()
            except self.s3.exceptions.NoSuchKey:
                return None

        return await asyncio.to_thread(get)

    async def list(self, prefix: str) -> list[str]:
        def list_keys() -> list[str]:
            keys = []
            for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.prefix + prefix):
                keys += [o["Key"].removeprefix(self.prefix) for o in page.get("Contents", [])]
            return sorted(keys)

        return await asyncio.to_thread(list_keys)

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list(prefix)

        def delete() -> None:
            for i in range(0, len(keys), 1000):
                objects = [{"Key": self.prefix + k} for k in keys[i : i + 1000]]
                self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})

        await asyncio.to_thread(delete)
        return len(keys)


def make_store(environ: Mapping[str, str] = os.environ) -> Store:
    """The bucket, under `dev/` unless this is the cloud container (CARL_CLOUD=1).

    Without a bucket key, a local run uses the folder `.carl-store/`.
    """
    prefix = "" if environ.get("CARL_CLOUD") == "1" else "dev/"
    if environ.get("S3_ACCESS_KEY") and environ.get("S3_SECRET_KEY"):
        return BucketStore(
            environ.get("S3_BUCKET", "carl-faktat"),
            environ.get("S3_ENDPOINT", "https://s3.fr-par.scw.cloud"),
            environ.get("S3_REGION", "fr-par"),
            environ["S3_ACCESS_KEY"],
            environ["S3_SECRET_KEY"],
            prefix,
        )
    if not prefix:
        raise RuntimeError("the cloud container needs its bucket key (S3_ACCESS_KEY, S3_SECRET_KEY)")
    return FolderStore(Path(".carl-store"))
