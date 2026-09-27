import asyncio
import dataclasses
import json
import logging
import time
from datetime import UTC, datetime

import pytest
from aiohttp import web

from carl import location
from carl.location import (
    NOMINATIM_URL,
    USER_AGENT,
    Level,
    Locator,
    Nominatim,
    Place,
    date_time,
    install,
    level,
    place_from,
)
from carl.recording import Recorder
from carl.server import SESSIONS
from carl.session import Session, Sessions

from .conftest import ScriptedStt
from .test_session import DISCLOSURE, connect, receive
from .test_session import events as recorded_events

LICENCE = "Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright"


def answer(name: str, addresstype: str, address: dict, bbox: list[str]) -> dict:
    return {"place_id": 1, "licence": LICENCE, "osm_type": "relation", "osm_id": 1, "category": "boundary",
            "type": "administrative", "addresstype": addresstype, "name": name, "address": address,
            "boundingbox": bbox}


# Nominatim's answer at zoom 14 for 60.184, 24.950, as it came on 2026-09-27
# (trimmed): the quarter Linjat, in the suburb Kallio.
KALLIO = answer("Linjat", "quarter", {
    "quarter": "Linjat", "suburb": "Kallio", "city_district": "Keskinen suurpiiri", "city": "Helsinki",
    "municipality": "Helsingin seutukunta", "state": "Uusimaa", "ISO3166-2-lvl4": "FI-18",
    "region": "Manner-Suomi", "postcode": "00530", "country": "Suomi / Finland", "country_code": "fi",
}, ["60.1797265", "60.1864515", "24.9334541", "24.9565747"])
TOOLO = answer("Etu-Töölö", "suburb", {
    "suburb": "Etu-Töölö", "city_district": "Eteläinen suurpiiri", "city": "Helsinki", "state": "Uusimaa",
    "country": "Suomi / Finland", "country_code": "fi",
}, ["60.1700", "60.1790", "24.9150", "24.9330"])
KALEVA = answer("Kaleva", "suburb", {
    "suburb": "Kaleva", "city": "Tampere", "state": "Pirkanmaa", "country": "Suomi / Finland", "country_code": "fi",
}, ["61.4900", "61.5100", "23.7900", "23.8200"])
NOWHERE = {"error": "Unable to geocode"}

AT_KALLIO = (60.1841, 24.9497)
ALSO_KALLIO = (60.1820, 24.9400)  # inside Linjat's box, but not the same query
AT_TOOLO = (60.1750, 24.9250)
AT_KALEVA = (61.5000, 23.8000)
AT_SEA = (60.1000, 24.9000)

KALLIO_PLACE = Place("Kallio", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
TOOLO_PLACE = Place("Etu-Töölö", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
KALEVA_PLACE = Place("Kaleva", "Tampere", "Pirkanmaa", "Suomi / Finland", "FI")


class FakeNominatim:
    """Nominatim's /reverse on localhost: answers by bounding box, or as the test says."""

    def __init__(self) -> None:
        self.requests: list[tuple[float, dict[str, str], dict[str, str]]] = []
        self.replies: list[tuple[int, object, float]] = []  # the next answers, before the places
        self.server = None

    def reply(self, body: object, status: int = 200, delay_s: float = 0.0) -> None:
        self.replies.append((status, body, delay_s))

    async def reverse(self, request: web.Request) -> web.Response:
        self.requests.append((time.monotonic(), dict(request.query), dict(request.headers)))
        if self.replies:
            status, body, delay_s = self.replies.pop(0)
            await asyncio.sleep(delay_s)
        else:
            lat, lon = float(request.query["lat"]), float(request.query["lon"])
            status, body = 200, next((a for a in (KALLIO, TOOLO, KALEVA) if inside(a, lat, lon)), NOWHERE)
        if isinstance(body, str):
            return web.Response(status=status, text=body)
        return web.json_response(body, status=status)

    @property
    def url(self) -> str:
        return str(self.server.make_url("/"))

    def asked(self) -> list[tuple[str, str]]:
        return [(query["lat"], query["lon"]) for _, query, _ in self.requests]


def inside(body: dict, lat: float, lon: float) -> bool:
    south, north, west, east = (float(x) for x in body["boundingbox"])
    return south <= lat <= north and west <= lon <= east


@pytest.fixture
async def nominatim(aiohttp_server) -> FakeNominatim:
    fake = FakeNominatim()
    app = web.Application()
    app.router.add_get("/reverse", fake.reverse)
    fake.server = await aiohttp_server(app)
    return fake


INTERVAL_S = 0.4  # geocode_min_interval_s, a minute in the config file


@pytest.fixture
def locator(config, nominatim) -> Locator:
    settings = dataclasses.replace(config.location, geocode_min_interval_s=INTERVAL_S)
    return Locator(settings, Nominatim(nominatim.url, gap_s=0.05, timeout_s=0.3))


@pytest.fixture
async def new_session(config, store):
    """Makes sessions, recording ones by default, without speech-to-text running."""
    sessions = Sessions(config, {}, store, ScriptedStt(), "test")
    made: list[Session] = []

    def make(record: bool = True, timezone: str = "Europe/Helsinki") -> Session:
        session = Session(sessions, f"20260927T180000Z-{len(made):06x}", record=record, timezone=timezone)
        if record:
            session.recorder = Recorder(store, session.id)
        made.append(session)
        return session

    yield make
    tasks = [task for session in made for task in session.tasks]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def fix(lat: float, lon: float, accuracy_m: float = 20.0) -> dict:
    return {"type": "location", "fix": {"lat": lat, "lon": lon, "accuracy_m": accuracy_m,
                                        "time": "2026-09-27T18:04:00.000Z"}}


async def until(condition, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        await asyncio.sleep(0.01)


async def events(session: Session, *kinds: str) -> list[dict]:
    await session.recorder.flush()
    store = session.sessions.store
    lines = []
    for key in await store.list(f"recordings/{session.id}/events/"):
        lines += [json.loads(line) for line in (await store.get(key)).decode().splitlines()]
    return [e for e in lines if not kinds or e["event"] in kinds]


# --- The accuracy cuts --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("accuracy_m", "expected"),
    [(5, Level.FULL), (1000, Level.FULL), (1000.5, Level.TOWN), (20000, Level.TOWN), (20000.5, Level.NONE),
     (1e6, Level.NONE)],
)
def test_the_accuracy_cuts(config, accuracy_m, expected):
    assert level(accuracy_m, config.location) is expected


def test_the_cuts_to_a_place():
    assert KALLIO_PLACE.cut(Level.FULL) == KALLIO_PLACE
    assert KALLIO_PLACE.cut(Level.TOWN) == Place(None, "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
    assert KALLIO_PLACE.cut(Level.NONE) is None


# --- From Nominatim's address to a place --------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        (KALLIO["address"], KALLIO_PLACE),
        ({"neighbourhood": "Torkkelinmäki", "suburb": "Kallio", "city": "Helsinki", "country_code": "fi"},
         Place("Torkkelinmäki", "Helsinki", None, None, "FI")),
        ({"quarter": "Tapiolan keskus", "city_district": "Suur-Tapiola", "city": "Espoo"},
         Place("Tapiolan keskus", "Espoo")),
        ({"city_district": "Keskinen suurpiiri", "city": "Helsinki"}, Place("Keskinen suurpiiri", "Helsinki")),
        ({"town": "Porvoo", "county": "Itä-Uusimaa", "country": "Suomi / Finland"},
         Place(None, "Porvoo", "Itä-Uusimaa", "Suomi / Finland")),
        ({"village": "Nuorgam", "municipality": "Utsjoki", "region": "Lappi"}, Place(None, "Nuorgam", "Lappi")),
        ({"municipality": "Utsjoki", "state": "Lappi", "county": "Tunturi-Lappi"}, Place(None, "Utsjoki", "Lappi")),
        ({"suburb": "Kreuzberg", "city": "Berlin", "state": "Berlin", "country": "Deutschland", "country_code": "de"},
         Place("Kreuzberg", "Berlin", "Berlin", "Deutschland", "DE")),
        ({"country": "Suomi / Finland", "country_code": "fi"}, Place(None, None, None, "Suomi / Finland", "FI")),
        ({"road": "Itäinen Papinkatu", "postcode": "00530"}, None),
        ({}, None),
    ],
)
def test_nominatims_address_fields_make_the_place(address, expected):
    assert place_from(address) == expected


@pytest.mark.parametrize(
    ("place", "name"),
    [
        (KALLIO_PLACE, "Kallio, Helsinki, Suomi / Finland"),
        (KALLIO_PLACE.cut(Level.TOWN), "Helsinki, Suomi / Finland"),
        (Place("Kreuzberg", "Berlin", "Berlin", "Deutschland", "DE"), "Kreuzberg, Berlin, Deutschland"),
        (Place("Nuorgam", "Nuorgam", "Lappi", "Suomi / Finland"), "Nuorgam, Suomi / Finland"),
        (Place(None, None, "Lappi", "Suomi / Finland"), "Lappi, Suomi / Finland"),
    ],
)
def test_a_place_name_is_the_neighbourhood_city_and_country(place, name):
    assert place.name() == name


# --- What each stage gets -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("zone", "expected"),
    [
        ("Europe/Helsinki", "Sunday 27 September 2026, 21:04 (Europe/Helsinki)"),
        ("America/New_York", "Sunday 27 September 2026, 14:04 (America/New_York)"),
        ("Pacific/Auckland", "Monday 28 September 2026, 07:04 (Pacific/Auckland)"),
        ("UTC", "Sunday 27 September 2026, 18:04 (UTC)"),
        ("Mars/Olympus_Mons", "Sunday 27 September 2026, 18:04 (UTC)"),
        ("../../etc/passwd", "Sunday 27 September 2026, 18:04 (UTC)"),
        ("", "Sunday 27 September 2026, 18:04 (UTC)"),
    ],
)
def test_the_date_and_time_are_the_server_clock_in_the_phones_timezone(zone, expected):
    assert date_time(zone, datetime(2026, 9, 27, 18, 4, 30, tzinfo=UTC)) == expected


def test_the_date_and_time_come_from_the_server_clock():
    assert date_time("Europe/Helsinki") == date_time("Europe/Helsinki", datetime.now(UTC))


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr(location, "date_time", lambda zone, now=None: f"<now in {zone}>")


@pytest.mark.parametrize(
    ("place", "with_place", "expected"),
    [
        (KALLIO_PLACE, True, "Kallio, Helsinki, Suomi / Finland. <now in Europe/Helsinki>"),
        (KALLIO_PLACE.cut(Level.TOWN), True, "Helsinki, Suomi / Finland. <now in Europe/Helsinki>"),
        (None, True, "<now in Europe/Helsinki>"),
        (KALLIO_PLACE, False, "<now in Europe/Helsinki>"),
    ],
)
def test_the_place_and_time_for_the_prompts(locator, new_session, frozen_clock, place, with_place, expected):
    session = new_session(record=False)
    session.place = place
    assert locator.place_and_time(session, with_place=with_place) == expected


def test_the_search_tools_get_place_names(locator, new_session):
    session = new_session(record=False)
    session.place = KALLIO_PLACE
    assert locator.openai_user_location(session) == {
        "type": "approximate", "city": "Helsinki", "region": "Uusimaa", "country": "FI", "timezone": "Europe/Helsinki",
    }
    assert locator.perplexity_user_location(session) == {"country": "FI", "region": "Uusimaa", "city": "Helsinki"}
    session.place = KALLIO_PLACE.cut(Level.TOWN)
    assert locator.openai_user_location(session)["city"] == "Helsinki"


def test_without_a_place_openai_still_gets_the_timezone(locator, new_session):
    """Without a location, OpenAI's search takes the table to be in the United States."""
    session = new_session(record=False, timezone="Europe/Helsinki")
    assert locator.openai_user_location(session) == {"type": "approximate", "timezone": "Europe/Helsinki"}
    assert locator.perplexity_user_location(session) is None
    session.timezone = "Nowhere/Special"
    assert locator.openai_user_location(session) == {"type": "approximate", "timezone": "UTC"}
    session.place = Place("Kallio", "Helsinki")  # no country: Perplexity needs one
    assert locator.perplexity_user_location(session) is None


async def test_no_stage_gets_coordinates(locator, new_session):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    contexts = [
        locator.place_and_time(session, with_place=True), locator.place_and_time(session, with_place=False),
        json.dumps(locator.openai_user_location(session)), json.dumps(locator.perplexity_user_location(session)),
        repr(session.place),
    ]
    assert not any(digits in text for text in contexts for digits in ("60.18", "24.9", "60,18", "24,9"))


# --- Geocoding ----------------------------------------------------------------------------


async def test_the_first_fix_is_geocoded_with_carls_own_user_agent(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    assert session.place == KALLIO_PLACE
    [(_, query, headers)] = nominatim.requests
    assert query == {"format": "jsonv2", "lat": "60.184", "lon": "24.950", "zoom": "14", "addressdetails": "1"}
    assert headers["User-Agent"] == USER_AGENT == "Carl (+https://github.com/akaihola/carl)"
    assert "@" not in USER_AGENT
    assert "Accept-Language" not in headers  # names as Nominatim gives them


async def test_a_fix_inside_the_last_neighbourhood_is_not_geocoded_again(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    await locator.on_message(session, fix(*ALSO_KALLIO))
    await asyncio.sleep(INTERVAL_S * 2)
    assert len(nominatim.requests) == 1 and session.place == KALLIO_PLACE


async def test_a_fix_outside_is_geocoded_at_most_once_a_minute(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    await locator.on_message(session, fix(*AT_TOOLO))
    await locator.on_message(session, fix(*AT_KALEVA))
    await asyncio.sleep(0.1)
    assert len(nominatim.requests) == 1 and session.place == KALLIO_PLACE  # the last place until then
    await until(lambda: session.place == KALEVA_PLACE)
    assert nominatim.asked() == [("60.184", "24.950"), ("61.500", "23.800")]  # only the latest fix
    first, second = (t for t, _, _ in nominatim.requests)
    assert second - first >= INTERVAL_S - 0.02


async def test_answers_are_cached(locator, new_session, nominatim):
    first, second = new_session(), new_session()
    await locator.on_message(first, fix(*AT_KALLIO))
    await until(lambda: first.place is not None)
    await locator.on_message(second, fix(60.18412, 24.94968, 35))  # the same query, to about 100 m
    await until(lambda: second.place is not None)
    assert second.place == KALLIO_PLACE and len(nominatim.requests) == 1
    [cached] = await events(second, "geocoder")
    assert cached["source"] == "cache" and cached["response"] == KALLIO and cached["elapsed_s"] is None


async def test_at_most_one_request_a_second_over_all_sessions(config, new_session, nominatim):
    locator = Locator(config.location, Nominatim(nominatim.url))
    helsinki, tampere = new_session(), new_session()
    await locator.on_message(helsinki, fix(*AT_KALLIO))
    await locator.on_message(tampere, fix(*AT_KALEVA))
    await until(lambda: helsinki.place is not None and tampere.place is not None)
    assert (helsinki.place, tampere.place) == (KALLIO_PLACE, KALEVA_PLACE)
    first, second = (t for t, _, _ in nominatim.requests)
    assert second - first >= 1.0


async def test_a_geocoder_failure_keeps_the_last_place(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    nominatim.reply("Service Unavailable", status=503)
    await locator.on_message(session, fix(*AT_TOOLO))
    await until(lambda: len(nominatim.requests) == 2)
    await asyncio.sleep(0.05)
    assert session.place == KALLIO_PLACE
    [failed] = await events(session, "geocoder failed")
    assert failed["kind"] == "unavailable" and failed["status"] == 503
    assert failed["error"] == "HTTP 503: Service Unavailable"
    await until(lambda: session.place == TOOLO_PLACE)  # tried again a minute later
    assert len(nominatim.requests) == 3


async def test_a_failure_before_any_place_leaves_none(config, new_session, nominatim):
    settings = dataclasses.replace(config.location, geocode_min_interval_s=1.0)
    locator = Locator(settings, Nominatim(nominatim.url, gap_s=0.05, timeout_s=0.3))
    session = new_session()
    nominatim.reply(KALLIO, delay_s=0.6)  # longer than the timeout
    await locator.on_message(session, fix(*AT_KALLIO))
    await asyncio.sleep(0.6)
    assert session.place is None and len(nominatim.requests) == 1
    [failed] = await events(session, "geocoder failed")
    assert failed["kind"] == "timeout"
    await until(lambda: session.place == KALLIO_PLACE)


def test_a_failing_geocoder_is_tried_less_and_less_often(config):
    locator = Locator(config.location, Nominatim())
    waits = [locator.wait_s(location.Track(failures=n)) for n in (0, 1, 2, 3, 4, 10)]
    assert waits == [60, 60, 120, 240, 480, 1800]


async def test_a_poor_fix_gives_the_town_only_and_a_worse_one_nothing(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO, accuracy_m=5000))
    await until(lambda: session.place is not None)
    assert session.place == Place(None, "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
    await locator.on_message(session, fix(*ALSO_KALLIO, accuracy_m=25))  # better, inside the box
    assert session.place == KALLIO_PLACE
    await locator.on_message(session, fix(*AT_KALLIO, accuracy_m=30000))
    assert session.place is None
    await locator.on_message(session, fix(*AT_KALLIO, accuracy_m=25))
    assert session.place == KALLIO_PLACE
    await asyncio.sleep(0.1)
    assert len(nominatim.requests) == 1


async def test_a_fix_with_no_location_is_not_geocoded(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO, accuracy_m=25000))
    await asyncio.sleep(0.1)
    assert session.place is None and nominatim.requests == []


async def test_a_neighbourhood_found_from_a_poor_fix_is_only_a_town_elsewhere(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO, accuracy_m=5000))
    await until(lambda: session.place is not None)
    await locator.on_message(session, fix(*AT_TOOLO, accuracy_m=20))  # good, outside the box, too soon
    assert session.place == Place(None, "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
    await until(lambda: session.place == TOOLO_PLACE)


async def test_where_nominatim_knows_no_place_there_is_none(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    await locator.on_message(session, fix(*AT_SEA))
    await until(lambda: session.place is None)
    await asyncio.sleep(INTERVAL_S * 2)
    assert len(nominatim.requests) == 2  # an answer, not a failure: not asked again


async def test_a_denial_is_noted_once(locator, new_session, nominatim):
    session = new_session()
    for _ in range(3):
        await locator.on_message(session, {"type": "location", "denied": True})
    assert len(await events(session, "location denied")) == 1
    assert session.place is None and nominatim.requests == []


@pytest.mark.parametrize(
    "message",
    [
        {"type": "location"},
        {"type": "location", "fix": None},
        {"type": "location", "fix": {"lat": "60.18", "lon": 24.95, "accuracy_m": 20}},
        {"type": "location", "fix": {"lat": 91, "lon": 24.95, "accuracy_m": 20}},
        {"type": "location", "fix": {"lat": 60.18, "lon": 24.95, "accuracy_m": -1}},
        {"type": "location", "fix": {"lat": 60.18, "lon": True, "accuracy_m": 20}},
        {"type": "location", "fix": {"lat": float("nan"), "lon": 24.95, "accuracy_m": 20}},
        {"type": "location", "denied": "yes"},
    ],
)
async def test_a_message_without_a_usable_fix_is_ignored(locator, new_session, nominatim, message):
    session = new_session()
    await locator.on_message(session, message)
    await asyncio.sleep(0.05)
    assert session.place is None and nominatim.requests == []
    assert await events(session, "location fix", "location denied") == []


async def test_an_ended_session_gets_no_fixes(locator, new_session, nominatim):
    session = new_session()
    session.state = "ended"
    await locator.on_message(session, fix(*AT_KALLIO))
    await asyncio.sleep(0.05)
    assert locator.tracks == {} and nominatim.requests == []


# --- What a recording keeps ---------------------------------------------------------------


async def test_the_recording_keeps_every_fix_and_geocoder_response(locator, new_session, nominatim):
    session = new_session()
    await locator.on_message(session, fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    await locator.on_message(session, fix(*ALSO_KALLIO, accuracy_m=3000))
    await locator.on_message(session, {"type": "location", "denied": True})
    log = await events(session, "location fix", "geocoder", "place", "location denied")
    assert [e["event"] for e in log] == ["location fix", "geocoder", "place", "location fix", "place",
                                         "location denied"]
    assert log[0]["fix"] == {"lat": 60.1841, "lon": 24.9497, "accuracy_m": 20.0, "time": "2026-09-27T18:04:00.000Z"}
    assert log[0]["level"] == "full"
    geocoder = log[1]
    assert (geocoder["lat"], geocoder["lon"], geocoder["zoom"], geocoder["source"]) == (60.184, 24.95, 14, "nominatim")
    assert geocoder["response"] == KALLIO and geocoder["elapsed_s"] >= 0
    assert log[2]["place"] == dataclasses.asdict(KALLIO_PLACE)
    assert log[3]["fix"]["accuracy_m"] == 3000 and log[3]["level"] == "town"
    assert log[4]["place"] == {"neighbourhood": None, "city": "Helsinki", "region": "Uusimaa",
                               "country": "Suomi / Finland", "country_code": "FI"}


async def test_coordinates_stay_out_of_the_server_log(locator, new_session, nominatim, caplog):
    caplog.set_level(logging.DEBUG)
    session = new_session(record=False)
    nominatim.reply("Bad Gateway for /reverse?lat=60.184&lon=24.950", status=502)
    await locator.on_message(session, fix(*AT_KALLIO))
    await locator.on_message(session, {"type": "location", "fix": {"lat": 600.1841, "lon": 24.9497}})
    await until(lambda: session.place is not None)
    carls = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("carl"))
    assert "the geocoder failed (unavailable)" in carls
    assert not any(digits in carls for digits in ("60.18", "24.9", "600.1"))
    assert await session.sessions.store.list("recordings/") == []  # a normal session records nothing


# --- Through the WebSocket ----------------------------------------------------------------


def test_install_uses_the_public_nominatim_unless_told_otherwise(config, store):
    sessions = Sessions(config, {}, store, ScriptedStt(), "test")
    install(sessions, {})
    assert isinstance(sessions.locator, Locator) and sessions.locator.geocoder.base_url == NOMINATIM_URL
    install(sessions, {"CARL_NOMINATIM_URL": "https://nominatim.example.org/"})
    assert sessions.locator.geocoder.base_url == "https://nominatim.example.org"


async def test_a_session_with_location_on(unlocked, store, nominatim):
    sessions = unlocked.server.app[SESSIONS]
    install(sessions, {"CARL_NOMINATIM_URL": nominatim.url})
    ws = await connect(unlocked)
    await ws.send_json({"type": "start", "record": True, "disclosure": DISCLOSURE, "mic": {},
                        "timezone": "Europe/Helsinki", "location": True})
    session_id = (await receive(ws, "session"))["session"]
    session = sessions.get(session_id)
    await ws.send_json(fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    assert session.place == KALLIO_PLACE
    assert sessions.locator.place_and_time(session, with_place=True).startswith("Kallio, Helsinki, Suomi / Finland. ")
    assert sessions.locator.place_and_time(session, with_place=False).endswith(" (Europe/Helsinki)")
    assert session_id in sessions.locator.tracks
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    assert sessions.locator.tracks == {}  # the coordinates are gone at End
    log = await recorded_events(store, session_id)
    assert log[0]["event"] == "session start" and log[0]["location"] is True
    kinds = [e["event"] for e in log]
    assert kinds.index("location fix") < kinds.index("geocoder") < kinds.index("place") < kinds.index("session end")
    assert next(e for e in log if e["event"] == "location fix")["fix"]["lat"] == 60.1841


async def test_a_normal_session_keeps_coordinates_only_in_memory(unlocked, store, nominatim):
    sessions = unlocked.server.app[SESSIONS]
    install(sessions, {"CARL_NOMINATIM_URL": nominatim.url})
    ws = await connect(unlocked)
    await ws.send_json({"type": "start", "record": False, "disclosure": None, "mic": {},
                        "timezone": "Europe/Helsinki", "location": True})
    session = sessions.get((await receive(ws, "session"))["session"])
    await ws.send_json({"type": "location", "denied": True})
    await ws.send_json(fix(*AT_KALLIO))
    await until(lambda: session.place is not None)
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    assert sessions.locator.tracks == {} and await store.list("recordings/") == []
