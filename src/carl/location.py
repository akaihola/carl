"""Location (spec section 12): the phone's fixes become a place name on the
server, through Nominatim, and each stage gets the place context it may have.
Coordinates never go to any model.

The page sends a fix (coordinates, accuracy and time) first, then only after
a move or a better accuracy level, and a denied permission once
(docs/websocket.md). For each session the locator keeps the latest fix in
server memory and cuts it to a level by its accuracy: the full place, the
town only, or none. It geocodes a fix only when it falls outside the last
result's neighbourhood (its bounding box), and at most once a minute. A
geocoder failure keeps the last place. `session.place` holds what stages may
know: a `Place`, never coordinates.

A recording's event log gets every raw fix, every geocoder response or
failure, a denial once and each change of place. Coordinates go nowhere
else: not the server's log, not the failure log. They are gone at End.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from .config import Location
from .session import Session, Sessions

log = logging.getLogger(__name__)

# Nominatim's usage policy (operations.osmfoundation.org/policies/nominatim):
# the application's own User-Agent, at most 1 request a second over all
# users, and results cached. CARL_NOMINATIM_URL switches to another server
# without a new build, as the policy asks.
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "Carl (+https://github.com/akaihola/carl)"
NOMINATIM_GAP_S = 1.0
ZOOM = 14  # neighbourhood level
DECIMALS = 3  # coordinates are sent, and cached, to about 100 m
TIMEOUT_S = 10.0
CACHE_SIZE = 512
RETRY_MAX_S = 1800.0  # a failing geocoder is tried again after 1, 2, 4… minutes, up to 30

# Nominatim's address fields for each part of a place name, the first found wins.
NEIGHBOURHOOD = ("neighbourhood", "suburb", "quarter", "city_district")
CITY = ("city", "town", "village", "municipality")
REGION = ("state", "region", "county")

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


class Level(IntEnum):
    """What a fix's accuracy lets stages know."""

    NONE = 0
    TOWN = 1
    FULL = 2


def level(accuracy_m: float, config: Location) -> Level:
    """Worse than `town_only_accuracy_m`: the town only. Worse than
    `no_location_accuracy_m`: no location."""
    if accuracy_m > config.no_location_accuracy_m:
        return Level.NONE
    if accuracy_m > config.town_only_accuracy_m:
        return Level.TOWN
    return Level.FULL


@dataclass(frozen=True)
class Place:
    """A place name as Nominatim gives it, never coordinates. `country_code`
    is ISO 3166-1 alpha-2, in capitals."""

    neighbourhood: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None

    def cut(self, level: Level) -> Place | None:
        """What stages may know of it at `level`."""
        if level is Level.NONE:
            return None
        return replace(self, neighbourhood=None) if level is Level.TOWN else self

    def name(self) -> str:
        """"Kallio, Helsinki, Suomi / Finland": the neighbourhood, the city
        (the region without one) and the country."""
        parts: list[str] = []
        for part in (self.neighbourhood, self.city or self.region, self.country):
            if part and part not in parts:
                parts.append(part)
        return ", ".join(parts)


def place_from(address: Mapping[str, Any]) -> Place | None:
    """The place in a Nominatim `address`, with names kept as they come."""

    def first(keys: tuple[str, ...]) -> str | None:
        return next((str(address[k]) for k in keys if address.get(k)), None)

    code = first(("country_code",))
    place = Place(first(NEIGHBOURHOOD), first(CITY), first(REGION), first(("country",)), code and code.upper())
    return place if any(asdict(place).values()) else None


@dataclass(frozen=True)
class Fix:
    """One fix as the page sent it. `time` is the page's, in ISO 8601."""

    lat: float
    lon: float
    accuracy_m: float
    time: str


def parse_fix(value: Any) -> Fix | None:
    """A fix from a `location` message, or None if it isn't a usable one."""
    if not isinstance(value, dict):
        return None
    numbers = [value.get(k) for k in ("lat", "lon", "accuracy_m")]
    if not all(isinstance(n, int | float) and not isinstance(n, bool) and math.isfinite(n) for n in numbers):
        return None
    lat, lon, accuracy = (float(n) for n in numbers)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and accuracy >= 0):
        return None
    stamp = value.get("time")
    return Fix(lat, lon, accuracy, stamp[:64] if isinstance(stamp, str) else "")


@dataclass(frozen=True)
class Geocoded:
    """One Nominatim answer: its place (None where it knows none, as at sea),
    the bounding box of what it found, and the body as it came."""

    place: Place | None
    bbox: tuple[float, float, float, float] | None  # south, north, west, east
    response: Any

    def covers(self, fix: Fix) -> bool:
        if self.bbox is None:
            return False
        south, north, west, east = self.bbox
        return south <= fix.lat <= north and west <= fix.lon <= east


class GeocodeError(Exception):
    """A failed request. `kind` is `timeout`, `unavailable` or `bad output`;
    `detail` may hold the request's coordinates, so it goes only to the
    recording."""

    def __init__(self, kind: str, detail: str, status: int | None = None):
        super().__init__(kind)
        self.kind, self.detail, self.status = kind, detail, status


def parse_answer(body: Any) -> Geocoded:
    if not isinstance(body, dict):
        raise GeocodeError("bad output", f"not a JSON object: {json.dumps(body)[:200]}")
    if "error" in body:  # "Unable to geocode": nothing there, such as the open sea
        return Geocoded(None, None, body)
    address = body.get("address")
    place = place_from(address) if isinstance(address, dict) else None
    try:
        south, north, west, east = (float(x) for x in body["boundingbox"])
        bbox: tuple[float, float, float, float] | None = (south, north, west, east)
    except (KeyError, TypeError, ValueError):
        bbox = None
    return Geocoded(place, bbox, body)


class Nominatim:
    """Reverse geocoding by Nominatim within its usage policy: one request at
    a time over all sessions, each starting at least `gap_s` after the last
    one ended, and answers cached by coordinates rounded to about 100 m."""

    def __init__(self, base_url: str = NOMINATIM_URL, *, gap_s: float = NOMINATIM_GAP_S,
                 timeout_s: float = TIMEOUT_S) -> None:
        self.base_url, self.gap_s, self.timeout_s = base_url.rstrip("/"), gap_s, timeout_s
        self.cache: OrderedDict[tuple[float, float], Geocoded] = OrderedDict()
        self.lock = asyncio.Lock()
        self.last = -math.inf  # when the last request ended, in monotonic time
        self.requests = 0

    @staticmethod
    def key(fix: Fix) -> tuple[float, float]:
        return round(fix.lat, DECIMALS), round(fix.lon, DECIMALS)

    def cached(self, fix: Fix) -> Geocoded | None:
        key = self.key(fix)
        if (hit := self.cache.get(key)) is not None:
            self.cache.move_to_end(key)
        return hit

    async def reverse(self, fix: Fix) -> tuple[Geocoded, float | None]:
        """The answer for `fix`, and the request's time in seconds, or None
        when it came from the cache. Raises GeocodeError."""
        async with self.lock:
            if (hit := self.cached(fix)) is not None:  # asked for while this one waited
                return hit, None
            await asyncio.sleep(max(0.0, self.last + self.gap_s - time.monotonic()))
            started = time.monotonic()
            try:
                answer = parse_answer(await self.request(*self.key(fix)))
            finally:
                self.last = time.monotonic()
            self.cache[self.key(fix)] = answer
            while len(self.cache) > CACHE_SIZE:
                self.cache.popitem(last=False)
            return answer, round(self.last - started, 3)

    async def request(self, lat: float, lon: float) -> Any:
        self.requests += 1
        params = {"format": "jsonv2", "lat": f"{lat:.{DECIMALS}f}", "lon": f"{lon:.{DECIMALS}f}",
                  "zoom": str(ZOOM), "addressdetails": "1"}
        timeout = aiohttp.ClientTimeout(total=self.timeout_s)
        try:
            async with (
                aiohttp.ClientSession(trust_env=True, timeout=timeout, headers={"User-Agent": USER_AGENT}) as http,
                http.get(f"{self.base_url}/reverse", params=params) as response,
            ):
                status, text = response.status, await response.text()
        except TimeoutError as e:
            raise GeocodeError("timeout", f"no answer in {self.timeout_s:g} s") from e
        except (aiohttp.ClientError, OSError) as e:
            raise GeocodeError("unavailable", repr(e)) from e
        if status != 200:
            raise GeocodeError("unavailable", f"HTTP {status}: {text[:1000]}", status)
        try:
            return json.loads(text)
        except ValueError as e:
            raise GeocodeError("bad output", f"not JSON: {text[:200]}", status) from e


@dataclass
class Track:
    """A session's location in server memory: never in the session state."""

    fix: Fix | None = None
    level: Level = Level.NONE
    result: Geocoded | None = None
    result_level: Level = Level.NONE  # the best level among the fixes its bounding box holds
    answered: Fix | None = None  # the last fix the geocoder answered
    last_request: float = -math.inf  # monotonic
    failures: int = 0
    denied: bool = False
    task: asyncio.Task | None = None


class Locator:
    """Location for every session: `sessions.locator`."""

    def __init__(self, config: Location, geocoder: Nominatim) -> None:
        self.config, self.geocoder = config, geocoder
        self.tracks: dict[str, Track] = {}

    # --- What each stage gets ----------------------------------------------------------

    def place_and_time(self, session: Session, *, with_place: bool) -> str:
        """"Kallio, Helsinki, Suomi / Finland. Sunday 27 September 2026,
        21:04 (Europe/Helsinki)" for the decision call and the fact-finders'
        prompts; the date, time and timezone alone without the place (the
        settle call, the fact-checking model) or when Carl has none."""
        when = date_time(session.timezone)
        name = session.place.name() if with_place and session.place is not None else ""
        return f"{name}. {when}" if name else when

    def openai_user_location(self, session: Session) -> dict[str, str]:
        """OpenAI `web_search`'s `user_location`. Always given, the timezone
        at least: without one the search takes the table to be in the US."""
        place: Place | None = session.place
        location = {"type": "approximate"}
        if place is not None:
            fields = {"city": place.city, "region": place.region, "country": place.country_code}
            location |= {k: v for k, v in fields.items() if v}
        location["timezone"] = time_zone(session.timezone).key
        return location

    def perplexity_user_location(self, session: Session) -> dict[str, str] | None:
        """Perplexity `web_search`'s `user_location`: country, region and city,
        or None without a country."""
        place: Place | None = session.place
        if place is None or not place.country_code:
            return None
        fields = {"country": place.country_code, "region": place.region, "city": place.city}
        return {k: v for k, v in fields.items() if v}

    # --- The page's messages -------------------------------------------------------------

    async def on_message(self, session: Session, message: dict[str, Any]) -> None:
        """A `location` message: a fix, or the permission denied. Returns at
        once; geocoding runs as the session's own task."""
        if session.state == "ended":
            return
        track = self.track(session)
        if message.get("denied") is True:
            if not track.denied:
                track.denied = True
                session.log("location denied")
            return
        if (fix := parse_fix(message.get("fix"))) is None:
            log.warning("session %s: ignored a location message without a usable fix", session.id)
            return
        track.fix, track.level = fix, level(fix.accuracy_m, self.config)
        session.log("location fix", fix=asdict(fix), level=track.level.name.lower())
        if track.result is not None and track.result.covers(fix):
            track.result_level = max(track.result_level, track.level)
        self.set_place(session, track)
        if track.task is None and self.unplaced(track) is not None:
            track.task = session.spawn(self.geocode(session, track))

    def track(self, session: Session) -> Track:
        if (track := self.tracks.get(session.id)) is None:
            track = self.tracks[session.id] = Track()
            session.spawn(self.forget_at_end(session))
        return track

    def forget(self, session: Session) -> None:
        """Drop the session's coordinates."""
        self.tracks.pop(session.id, None)

    async def forget_at_end(self, session: Session) -> None:
        """End cancels the session's tasks, this one too, and so forgets."""
        try:
            await asyncio.get_running_loop().create_future()
        finally:
            self.forget(session)

    # --- Geocoding -----------------------------------------------------------------------

    def unplaced(self, track: Track) -> Fix | None:
        """The latest fix, if it needs geocoding: it has a level, the geocoder
        hasn't answered it, and it is outside the last result's box."""
        fix = track.fix
        if fix is None or track.level is Level.NONE or fix is track.answered:
            return None
        return None if track.result is not None and track.result.covers(fix) else fix

    def wait_s(self, track: Track) -> float:
        """At most once a minute; after failures, 1, 2, 4… minutes, up to 30."""
        interval = self.config.geocode_min_interval_s
        return min(interval * 2 ** max(0, track.failures - 1), max(interval, RETRY_MAX_S))

    async def geocode(self, session: Session, track: Track) -> None:
        """Geocode the session's latest fix as the rules allow, until it needs
        no more: a newer fix may come while this waits."""
        try:
            while (fix := self.unplaced(track)) is not None:
                hit = self.geocoder.cached(fix)
                if hit is None:
                    if (wait := track.last_request + self.wait_s(track) - time.monotonic()) > 0:
                        await asyncio.sleep(wait)
                        continue
                    track.last_request = time.monotonic()
                try:
                    answer, elapsed_s = (hit, None) if hit is not None else await self.geocoder.reverse(fix)
                except GeocodeError as e:
                    track.failures += 1
                    session.log("geocoder failed", lat=fix.lat, lon=fix.lon, kind=e.kind, status=e.status,
                                error=e.detail)
                    log.warning("session %s: the geocoder failed (%s); keeping the last place", session.id, e.kind)
                    continue
                track.failures = 0
                track.answered = fix
                lat, lon = Nominatim.key(fix)
                session.log("geocoder", lat=lat, lon=lon, zoom=ZOOM, source="nominatim" if hit is None else "cache",
                            elapsed_s=elapsed_s, response=answer.response)
                track.result, track.result_level = answer, level(fix.accuracy_m, self.config)
                if track.fix is not fix and answer.covers(track.fix):
                    track.result_level = max(track.result_level, track.level)
                self.set_place(session, track)
        finally:
            track.task = None

    def set_place(self, session: Session, track: Track) -> None:
        """The last result's place at the level both it and the latest fix
        allow: a neighbourhood found from a poor fix is only a town."""
        result = track.result
        place = None
        if result is not None and result.place is not None:
            place = result.place.cut(min(track.level, track.result_level))
        if place != session.place:
            session.place = place
            session.log("place", place=None if place is None else asdict(place))


def time_zone(name: str) -> ZoneInfo:
    """The phone's timezone, or UTC when it isn't one Carl knows."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def date_time(timezone: str, now: datetime | None = None) -> str:
    """"Sunday 27 September 2026, 21:04 (Europe/Helsinki)": the server clock
    in the phone's timezone."""
    zone = time_zone(timezone)
    t = (now or datetime.now(UTC)).astimezone(zone)
    return f"{DAYS[t.weekday()]} {t.day} {MONTHS[t.month - 1]} {t.year}, {t:%H:%M} ({zone.key})"


def install(sessions: Sessions, environ: Mapping[str, str]) -> None:
    """Plug location into the sessions (`sessions.locator`)."""
    geocoder = Nominatim(environ.get("CARL_NOMINATIM_URL") or NOMINATIM_URL)
    sessions.locator = Locator(sessions.config.location, geocoder)
