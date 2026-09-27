import asyncio
import dataclasses
import json
import logging
import math
from types import SimpleNamespace

import aiohttp
import pytest
from aiohttp import web

from carl.config import Price, Stage
from carl.finding import (
    NOTHING_BEFORE,
    SCHEMA,
    STAGE_A,
    STAGE_B,
    FindingRequest,
    SearchResult,
    key_name,
    language_name,
    make_fact_finder,
    same_model,
    same_url,
)
from carl.location import Locator, Nominatim, Place
from carl.models import ModelError
from carl.prompts import FILLS, PromptError, load_prompts

from .conftest import ROOT

A = Stage("openai", "gpt-test", {"reasoning_effort": "none", "tool_choice": "required"})
B = Stage("perplexity", "google/gemini-test", {
    "reasoning_effort": "low", "search_type": "web", "search_context_size": "medium", "max_steps": 2,
    "max_output_tokens": 4096,
})
PRICES = {
    "openai": {"gpt-test": Price(input=0.10, cached=0.01, output=0.50, search=0.010)},
    "perplexity": {"google/gemini-test": Price(input=0.75, cached=0.075, output=3.75, search=0.0025)},
}
KEYS = {"OPENAI_API_KEY": "sk-test-openai", "PERPLEXITY_API_KEY": "pplx-test"}

PLACE = Place("Kallio", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
PLACE_AND_TIME = "Kallio, Helsinki, Suomi / Finland. Sunday 27 September 2026, 21:04 (Europe/Helsinki)"
CONVERSATION = ("A1: We had a talk at work about gifted kids today.", "(paused)")
CANDIDATE = "B2: Einstein failed maths at school, you know."

ANSWER = {
    "restatement": "Albert Einstein failed mathematics at school.",
    "outcome": "claim is wrong",
    "title": "Einstein didn't fail maths",
    "fact": "Albert Einstein never failed mathematics; he had mastered calculus before he was 15.",
    "source_url": "https://en.wikipedia.org/wiki/Albert_Einstein",
    "source_title": "Albert Einstein - Wikipedia",
    "excerpt": "he had mastered differential and integral calculus before he was fifteen",
}
EMPTY_CARD = {"title": "", "fact": "", "source_url": "", "source_title": "", "excerpt": ""}


@pytest.fixture(scope="module")
def prompt():
    return load_prompts(ROOT / "prompts")["fact-finding"]


@pytest.fixture
def locator(config):
    return Locator(config.location, Nominatim())


@pytest.fixture
def table():
    """What location's methods read of a session: its place name and timezone."""
    return SimpleNamespace(place=PLACE, timezone="Europe/Helsinki")


@pytest.fixture
def request_(prompt, locator, table):
    return FindingRequest(
        prompt, "claim", CANDIDATE, CONVERSATION, PLACE_AND_TIME, language_name("en"),
        locator.openai_user_location(table), locator.perplexity_user_location(table),
    )


# --- Fake providers ----------------------------------------------------------------------


class Fake:
    """A fake OpenAI and Perplexity: records each request and answers as the test says."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], dict]] = []
        self.replies: list[tuple[int, object, float]] = []
        self.server = None

    def reply(self, body: object, status: int = 200, delay_s: float = 0.0) -> None:
        self.replies.append((status, body, delay_s))

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append((request.path, dict(request.headers), await request.json()))
        status, body, delay_s = self.replies.pop(0)
        await asyncio.sleep(delay_s)
        if isinstance(body, str):
            return web.Response(status=status, text=body)
        return web.json_response(body, status=status)

    def url(self, path: str) -> str:
        return str(self.server.make_url(path))

    @property
    def body(self) -> dict:
        return self.requests[-1][2]


@pytest.fixture
async def fake(aiohttp_server) -> Fake:
    fake = Fake()
    app = web.Application()
    app.router.add_post("/v1/responses", fake.handle)
    app.router.add_post("/v1/agent", fake.handle)
    fake.server = await aiohttp_server(app)
    return fake


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def test_config(config):
    return dataclasses.replace(config, prices=PRICES)


@pytest.fixture
def finder_a(fake, test_config, session):
    return make_fact_finder(A, test_config, KEYS, session, base_url=fake.url("/v1"), timeout_s=2)


@pytest.fixture
def finder_b(fake, test_config, session):
    return make_fact_finder(B, test_config, KEYS, session, base_url=fake.url("/v1"), timeout_s=2)


def text(answer) -> str:
    return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)


def a_reply(answer=ANSWER, *, usage=None, model="gpt-test-2026-09-01", status="completed", calls=None) -> dict:
    """A Responses API reply with one search and its sources."""
    if calls is None:
        calls = [{
            "type": "web_search_call", "id": "ws_1", "status": "completed",
            "action": {"type": "search", "query": "Einstein failed maths myth", "sources": [
                {"type": "url", "url": "https://www.en.wikipedia.org/wiki/Albert_Einstein/"},
                {"type": "url", "url": "https://www.snopes.com/fact-check/einstein-math/", "title": "Einstein math"},
            ]},
        }]
    message = {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
               "content": [{"type": "output_text", "text": text(answer), "annotations": []}]}
    usage = {"input_tokens": 9000, "input_tokens_details": {"cached_tokens": 1000}, "output_tokens": 250,
             "output_tokens_details": {"reasoning_tokens": 0}} if usage is None else usage
    return {"id": "resp_1", "object": "response", "model": model, "status": status, "output": [*calls, message],
            "usage": usage}


B_RESULTS = [
    {"id": 1, "url": "https://en.wikipedia.org/wiki/Albert_Einstein", "title": "Albert Einstein - Wikipedia",
     "snippet": "A persistent myth says he failed mathematics, but he had mastered differential and integral "
                "calculus before he was fifteen.", "date": "2026-09-01", "source": "web"},
    {"id": 2, "url": "https://www.britannica.com/biography/Albert-Einstein", "title": "Albert Einstein | Britannica",
     "snippet": "Einstein was born in Ulm.", "source": "web"},
]
B_USAGE = {
    "input_tokens": 4000, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 300,
    "tool_calls_details": {"search_web": {"invocation": 1}},
    "cost": {"currency": "USD", "input_cost": 0.003, "output_cost": 0.001125, "tool_calls_cost": 0.0025,
             "total_cost": 0.006625},
}


def b_reply(answer=ANSWER, *, usage=None, model="google/gemini-test", status="completed", results=None) -> dict:
    """An Agent API reply with one search, which ran two queries."""
    search = {"type": "search_results", "queries": ["Einstein failed math myth", "Einstein Mathematik Schule"],
              "results": B_RESULTS if results is None else results}
    message = {"type": "message", "role": "assistant", "status": "completed",
               "content": [{"type": "output_text", "text": text(answer), "annotations": []}]}
    return {"id": "resp_b", "object": "response", "model": model, "status": status, "output": [search, message],
            "usage": B_USAGE if usage is None else usage}


def keys_in(value) -> set[str]:
    """Every key anywhere in a JSON value."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_in(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_in(v)}
    return set()


def estimate(request: dict, output_tokens: int) -> tuple[int, int]:
    return math.ceil(len(json.dumps(request, ensure_ascii=False)) / 4), output_tokens


# --- The request -------------------------------------------------------------------------


def test_the_prompt_file_is_filled_in(prompt, request_):
    assert prompt.placeholders == FILLS["fact-finding"]
    rendered = request_.text()
    assert "{" not in rendered.replace('{"', "")
    assert "flagged as a possible\nclaim. Search the web" in rendered
    assert "Write the restatement, title and fact in English." in rendered
    assert f"Where and when: {PLACE_AND_TIME}" in rendered
    assert rendered.endswith(f"today.\n(paused)\n\nCANDIDATE: {CANDIDATE}\n")
    assert "Never cite forums, social media or video." in rendered


def test_the_request_values_and_event(prompt, request_):
    assert request_.values() == {
        "candidate_kind": "claim", "card_language": "English", "place_and_time": PLACE_AND_TIME,
        "conversation": "\n".join(CONVERSATION), "candidate": CANDIDATE,
    }
    event = json.loads(json.dumps(request_.event()))
    assert (event["prompt"], event["version"]) == ("fact-finding", prompt.version)
    assert event["values"] == request_.values()
    assert event["openai_location"]["city"] == "Helsinki" and event["perplexity_location"]["country"] == "FI"
    assert "Search the web" not in json.dumps(event)  # never the rendered text


def test_a_candidate_said_first_has_nothing_before(prompt):
    request = FindingRequest(prompt, "open question", "A1: Who played Rick?", [], PLACE_AND_TIME, "Finnish")
    assert request.values()["conversation"] == NOTHING_BEFORE
    assert request.conversation == ()


def test_a_candidate_is_a_claim_or_an_open_question(prompt):
    with pytest.raises(ValueError, match="not 'none'"):
        FindingRequest(prompt, "none", CANDIDATE, CONVERSATION, PLACE_AND_TIME, "English")


def test_a_prompt_missing_a_value_fails(request_):
    other = dataclasses.replace(request_.prompt, placeholders=request_.prompt.placeholders | {"earlier"})
    with pytest.raises(PromptError, match="no value for earlier"):
        dataclasses.replace(request_, prompt=other).text()


@pytest.mark.parametrize(("code", "name"), [("fi", "Finnish"), ("en", "English"), ("SV", "Swedish"), ("xx", "xx")])
def test_language_name(code, name):
    assert language_name(code) == name


async def test_openai_request(fake, finder_a, request_):
    fake.reply(a_reply())
    await finder_a.find(request_, stage=STAGE_A)
    path, headers, body = fake.requests[0]
    assert path == "/v1/responses"
    assert headers["Authorization"] == "Bearer sk-test-openai"
    assert body["model"] == "gpt-test"
    assert body["store"] is False
    assert body["tools"] == [{
        "type": "web_search",
        "user_location": {"type": "approximate", "city": "Helsinki", "region": "Uusimaa", "country": "FI",
                          "timezone": "Europe/Helsinki"},
    }]
    assert body["tool_choice"] == "required"
    assert body["reasoning"] == {"effort": "none"}
    assert body["include"] == ["web_search_call.action.sources"]
    assert body["input"] == request_.text()
    fmt = body["text"]["format"]
    assert (fmt["type"], fmt["name"], fmt["strict"]) == ("json_schema", "draft_card", True)
    assert fmt["schema"] == SCHEMA
    assert fmt["schema"]["properties"]["outcome"]["enum"] == [
        "claim is wrong", "claim is right", "question answered", "not found",
    ]
    assert set(fmt["schema"]["required"]) == set(fmt["schema"]["properties"])
    assert "max_output_tokens" not in body


async def test_perplexity_request(fake, finder_b, request_):
    fake.reply(b_reply())
    await finder_b.find(request_, stage=STAGE_B)
    path, headers, body = fake.requests[0]
    assert path == "/v1/agent"
    assert headers["Authorization"] == "Bearer pplx-test"
    assert body["model"] == "google/gemini-test"
    assert body["store"] is False
    assert body["input"] == request_.text()
    assert body["tools"] == [{
        "type": "web_search", "search_type": "web", "search_context_size": "medium",
        "user_location": {"country": "FI", "region": "Uusimaa", "city": "Helsinki"},
    }]
    assert body["response_format"] == {
        "type": "json_schema", "json_schema": {"name": "draft_card", "strict": True, "schema": SCHEMA},
    }
    assert body["reasoning"] == {"effort": "low"}
    assert (body["max_steps"], body["max_output_tokens"]) == (2, 4096)


async def test_no_coordinates_reach_either_search_tool(fake, finder_a, finder_b, request_):
    coordinates = {"lat": 60.1841, "lon": 24.9497, "latitude": 60.1841, "longitude": 24.9497, "accuracy_m": 30}
    request = dataclasses.replace(
        request_, openai_location=dict(request_.openai_location) | coordinates,
        perplexity_location=dict(request_.perplexity_location) | coordinates,
    )
    fake.reply(a_reply())
    fake.reply(b_reply())
    await finder_a.find(request, stage=STAGE_A)
    await finder_b.find(request, stage=STAGE_B)
    for _, _, body in fake.requests:
        sent = json.dumps(body)
        assert "60.18" not in sent and "24.94" not in sent
        assert not keys_in(body) & {"lat", "lon", "latitude", "longitude", "accuracy_m", "coordinates"}
    assert set(fake.requests[0][2]["tools"][0]["user_location"]) == {"type", "city", "region", "country", "timezone"}
    assert set(fake.requests[1][2]["tools"][0]["user_location"]) == {"country", "region", "city"}


async def test_without_a_place_the_tools_get_what_there_is(fake, finder_a, finder_b, request_, locator):
    nowhere = SimpleNamespace(place=None, timezone="Europe/Helsinki")
    request = dataclasses.replace(request_, openai_location=locator.openai_user_location(nowhere),
                                  perplexity_location=locator.perplexity_user_location(nowhere))
    fake.reply(a_reply())
    fake.reply(b_reply())
    await finder_a.find(request, stage=STAGE_A)
    await finder_b.find(request, stage=STAGE_B)
    # OpenAI's search takes the table to be in the US without one, so the timezone always goes.
    assert fake.requests[0][2]["tools"][0]["user_location"] == {"type": "approximate", "timezone": "Europe/Helsinki"}
    assert "user_location" not in fake.requests[1][2]["tools"][0]
    request = dataclasses.replace(request_, openai_location=None, perplexity_location=None)
    fake.reply(a_reply())
    await finder_a.find(request, stage=STAGE_A)
    assert fake.body["tools"] == [{"type": "web_search"}]


# --- Findings -------------------------------------------------------------------------------


async def test_openai_finding(fake, finder_a, request_, prompt):
    fake.reply(a_reply())
    finding = await finder_a.find(request_, stage=STAGE_A)
    assert finding.outcome == "claim is wrong"
    assert finding.restatement == "Albert Einstein failed mathematics at school."
    assert finding.card.title == "Einstein didn't fail maths"
    assert finding.card.source_url == "https://en.wikipedia.org/wiki/Albert_Einstein"
    assert finding.card.excerpt == ANSWER["excerpt"]
    # OpenAI's sources: URLs, a title when given, never a snippet.
    assert finding.results == (
        SearchResult("https://www.en.wikipedia.org/wiki/Albert_Einstein/"),
        SearchResult("https://www.snopes.com/fact-check/einstein-math/", "Einstein math"),
    )
    assert finding.searches == ("Einstein failed maths myth",)
    assert finding.search_calls == 1
    assert finding.source_in_results is True
    # A dated snapshot of the pinned model is the pinned model.
    assert finding.model == "gpt-test-2026-09-01" and not finding.model_differs
    r = finding.record
    assert (r.stage, r.provider, r.model) == ("fact-finding A", "openai", "gpt-test-2026-09-01")
    assert (r.prompt, r.version, r.fields) == ("fact-finding", prompt.version, request_.values())
    assert r.params == A.params
    assert (r.input_tokens, r.cached_tokens, r.output_tokens) == (9000, 1000, 250)
    assert r.cost_usd == pytest.approx((8000 * 0.10 + 1000 * 0.01 + 250 * 0.50) / 1e6 + 1 * 0.010)
    assert r.provider_cost_usd is None and r.charged_usd == r.cost_usd
    assert not r.estimated and r.error is None and r.status == 200
    event = json.loads(json.dumps(finding.event()))
    assert event["card"]["title"] == "Einstein didn't fail maths"
    assert event["results"][1] == {"url": "https://www.snopes.com/fact-check/einstein-math/",
                                   "title": "Einstein math", "snippet": ""}
    assert "record" not in event


async def test_openai_counts_each_search_and_skips_page_actions(fake, finder_a, request_):
    calls = [
        {"type": "web_search_call", "action": {"type": "search", "queries": ["a", "b"],
                                               "sources": [{"type": "url", "url": "https://a.example/"}]}},
        {"type": "web_search_call", "action": {"type": "open_page", "url": "https://a.example/"}},
        {"type": "web_search_call", "action": {"type": "search", "query": "c"}},
    ]
    fake.reply(a_reply(calls=calls, usage={"input_tokens": 1000, "output_tokens": 100}))
    finding = await finder_a.find(request_, stage=STAGE_A)
    assert finding.searches == ("a; b", "c")
    assert finding.search_calls == 2
    assert finding.results == (SearchResult("https://a.example/"),)
    assert finding.source_in_results is False
    assert finding.record.cost_usd == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1e6 + 2 * 0.010)


async def test_perplexity_finding(fake, finder_b, request_, caplog):
    fake.reply(b_reply())
    with caplog.at_level(logging.INFO, logger="carl.finding"):
        finding = await finder_b.find(request_, stage=STAGE_B)
    assert finding.outcome == "claim is wrong"
    assert finding.card.fact.startswith("Albert Einstein never failed")
    assert finding.results[0] == SearchResult(
        "https://en.wikipedia.org/wiki/Albert_Einstein", "Albert Einstein - Wikipedia", B_RESULTS[0]["snippet"],
    )
    assert finding.results[1].snippet == "Einstein was born in Ulm."
    assert finding.card.excerpt in finding.results[0].snippet
    assert finding.searches == ("Einstein failed math myth", "Einstein Mathematik Schule")
    assert finding.search_calls == 1
    assert finding.source_in_results is True
    assert finding.model == "google/gemini-test" and not finding.model_differs
    r = finding.record
    carl = (4000 * 0.75 + 300 * 3.75) / 1e6 + 1 * 0.0025
    assert r.cost_usd == pytest.approx(carl)
    assert r.provider_cost_usd == 0.006625
    assert r.charged_usd == 0.006625
    assert not r.estimated
    assert not caplog.records  # the two figures agree


async def test_perplexitys_own_cost_counts_and_the_difference_is_logged(fake, finder_b, request_, caplog):
    usage = B_USAGE | {"cost": {"total_cost": 0.0102}}
    fake.reply(b_reply(usage=usage))
    with caplog.at_level(logging.INFO, logger="carl.finding"):
        r = (await finder_b.find(request_, stage=STAGE_B)).record
    assert r.cost_usd == pytest.approx(0.006625)
    assert r.provider_cost_usd == 0.0102 and r.charged_usd == 0.0102
    logged = "fact-finding B via perplexity: the provider charged $0.010200, the price table says $0.006625"
    assert logged in caplog.text


async def test_perplexity_searches_without_invocations_are_its_search_results(fake, finder_b, request_):
    usage = {k: v for k, v in B_USAGE.items() if k not in ("tool_calls_details", "cost")}
    reply = b_reply(usage=usage)
    reply["output"].insert(1, {"type": "search_results", "queries": [], "results": []})
    fake.reply(reply)
    finding = await finder_b.find(request_, stage=STAGE_B)
    assert finding.search_calls == 2
    assert finding.searches == ("Einstein failed math myth", "Einstein Mathematik Schule", "(no query given)")
    assert finding.record.provider_cost_usd is None
    assert finding.record.cost_usd == pytest.approx(0.006625 + 0.0025)


async def test_a_different_model_is_flagged(fake, finder_b, request_, caplog):
    fake.reply(b_reply(model="google/gemini-3.7-flash"))
    with caplog.at_level(logging.WARNING, logger="carl.finding"):
        finding = await finder_b.find(request_, stage=STAGE_B)
    assert finding.model == finding.record.model == "google/gemini-3.7-flash"
    assert finding.model_differs and finding.event()["model_differs"] is True
    assert "ran google/gemini-3.7-flash, not the pinned google/gemini-test" in caplog.text


@pytest.mark.parametrize(
    ("pinned", "reported", "same"),
    [("gpt-6-luna", "gpt-6-luna-2026-09-01", True), ("google/gemini-3.8-flash", "google/gemini-3.8-flash", True),
     ("google/gemini-3.8-flash", "gemini-3.8-flash", True), ("typesafe/jev-1.13", "typesafe/jev-1.13-20260917", True),
     ("google/gemini-3.8-flash", "google/gemini-3.8-flash-lite", False),
     ("google/gemini-3.8-flash", "openai/gpt-6-luna", False), ("gpt-6-luna", "gpt-6", False)],
)
def test_same_model(pinned, reported, same):
    assert same_model(pinned, reported) is same


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [("https://en.wikipedia.org/wiki/Casablanca_(film)", "http://en.wikipedia.org/wiki/Casablanca_%28film%29/", True),
     ("https://Example.org/a#part", "https://example.org/a", True),
     ("https://example.org/a?x=1", "https://example.org/a?x=2", False),
     ("https://fi.wikipedia.org/wiki/Helsinki", "https://en.wikipedia.org/wiki/Helsinki", False)],
)
def test_same_url(a, b, same):
    assert same_url(a, b) is same


@pytest.mark.parametrize("outcome", ["claim is right", "not found"])
async def test_silent_outcomes_have_no_card(fake, finder_a, finder_b, request_, outcome):
    filled = ANSWER | {"outcome": outcome}
    fake.reply(a_reply(filled))
    fake.reply(b_reply(ANSWER | EMPTY_CARD | {"outcome": outcome}))
    for finder, stage in ((finder_a, STAGE_A), (finder_b, STAGE_B)):
        finding = await finder.find(request_, stage=stage)
        assert finding.outcome == outcome
        assert finding.restatement == "Albert Einstein failed mathematics at school."
        assert finding.card is None and finding.source_in_results is None


async def test_a_question_answered(fake, finder_b, prompt):
    request = FindingRequest(prompt, "open question", "A2: Kuka siinä näytteli Rickiä?",
                             ["A1: Katsoin eilen taas Casablancan."], PLACE_AND_TIME, "Finnish")
    answer = {
        "restatement": "Kuka näytteli Rickiä elokuvassa Casablanca?", "outcome": "question answered",
        "title": "Rick Casablancassa", "fact": "Casablancan Rick Blainea näytteli Humphrey Bogart.",
        "source_url": "https://en.wikipedia.org/wiki/Casablanca_(film)", "source_title": "Casablanca (film)",
        "excerpt": "  Bogart plays Rick Blaine  ",
    }
    fake.reply(b_reply(answer))
    finding = await finder_b.find(request, stage=STAGE_B)
    assert finding.outcome == "question answered"
    assert finding.card.fact == "Casablancan Rick Blainea näytteli Humphrey Bogart."
    assert finding.card.excerpt == "Bogart plays Rick Blaine"  # only the ends are trimmed
    assert "user_location" not in fake.body["tools"][0]


async def test_fenced_json_is_read(fake, finder_a, request_):
    fake.reply(a_reply("```json\n" + json.dumps(ANSWER) + "\n```"))
    assert (await finder_a.find(request_, stage=STAGE_A)).outcome == "claim is wrong"


# --- Bad output -------------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["claim is wrong", "question answered"])
@pytest.mark.parametrize(
    ("change", "detail"),
    [({"excerpt": ""}, "no excerpt"), ({"source_url": "  "}, "no source_url"),
     ({"title": None}, "no title"), ({"fact": "", "source_title": ""}, "no fact, source_title"),
     ({"source_url": "Wikipedia"}, "is not a web address"),
     ({"source_url": "ftp://example.org/x"}, "is not a web address")],
)
async def test_an_incomplete_card_is_bad_output_at_its_real_cost(fake, finder_b, request_, outcome, change, detail):
    answer = ANSWER | {"outcome": outcome} | change
    if change.get("title", "") is None:
        del answer["title"]
    fake.reply(b_reply(answer))
    with pytest.raises(ModelError) as caught:
        await finder_b.find(request_, stage=STAGE_B)
    e = caught.value
    assert e.kind == e.record.error == "bad output"
    assert detail in e.record.error_text
    assert not e.record.estimated
    assert e.record.provider_cost_usd == 0.006625 and e.record.cost_usd == pytest.approx(0.006625)


@pytest.mark.parametrize(
    ("answer", "detail"),
    [("The claim is wrong: he never failed.", "not JSON"),
     (json.dumps([ANSWER]), "not a JSON object"),
     (json.dumps(ANSWER | {"outcome": "partly wrong"}), "outcome 'partly wrong' is not one of"),
     (json.dumps({k: v for k, v in ANSWER.items() if k != "outcome"}), "outcome None is not one of"),
     (json.dumps(ANSWER | {"restatement": " "}), "no restatement"),
     (json.dumps(ANSWER | EMPTY_CARD | {"outcome": "claim is right", "restatement": ""}), "no restatement")],
)
async def test_an_answer_that_isnt_a_finding_is_bad_output(fake, finder_a, request_, answer, detail):
    fake.reply(a_reply(answer))
    with pytest.raises(ModelError) as caught:
        await finder_a.find(request_, stage=STAGE_A)
    e = caught.value
    assert e.kind == "bad output" and detail in e.record.error_text
    assert e.record.cost_usd == pytest.approx((8000 * 0.10 + 1000 * 0.01 + 250 * 0.50) / 1e6 + 0.010)
    assert str(e) == "fact-finding A via openai: bad output (HTTP 200)"


async def test_a_refusal_is_bad_output(fake, finder_a, request_):
    reply = a_reply()
    reply["output"][-1]["content"] = [{"type": "refusal", "refusal": "I can't help with that."}]
    fake.reply(reply)
    with pytest.raises(ModelError) as caught:
        await finder_a.find(request_, stage=STAGE_A)
    assert caught.value.kind == "bad output"
    assert caught.value.record.error_text == "refusal: I can't help with that."


@pytest.mark.parametrize("which", ["a", "b"])
async def test_an_unfinished_run_is_bad_output_and_a_failed_one_unavailable(fake, finder_a, finder_b, request_, which):
    finder, reply, stage = (finder_a, a_reply, STAGE_A) if which == "a" else (finder_b, b_reply, STAGE_B)
    incomplete = reply(ANSWER, status="incomplete") | {"incomplete_details": {"reason": "max_output_tokens"}}
    failed = reply(ANSWER, status="failed") | {"error": {"code": "server_error", "message": "The run failed."}}
    fake.reply(incomplete)
    fake.reply(failed)
    with pytest.raises(ModelError) as caught:
        await finder.find(request_, stage=stage)
    assert caught.value.kind == "bad output"
    assert caught.value.record.error_text == 'status incomplete: {"reason": "max_output_tokens"}'
    assert not caught.value.record.estimated  # its usage came back
    with pytest.raises(ModelError) as caught:
        await finder.find(request_, stage=stage)
    assert caught.value.kind == "unavailable"
    assert "The run failed." in caught.value.record.error_text


async def test_output_that_cant_be_read_is_bad_output_with_an_estimated_search(fake, finder_a, request_):
    reply = a_reply()
    reply["output"] = [{"type": "message", "content": "not a list of parts"}]
    fake.reply(reply)
    with pytest.raises(ModelError) as caught:
        await finder_a.find(request_, stage=STAGE_A)
    r = caught.value.record
    assert caught.value.kind == "bad output" and "can't read the output" in r.error_text
    assert r.estimated  # the tokens are known, the searches aren't
    assert r.cost_usd == pytest.approx((8000 * 0.10 + 1000 * 0.01 + 250 * 0.50) / 1e6 + 0.010)


# --- Estimates and typed errors ------------------------------------------------------------------


async def test_without_usage_the_tokens_are_estimated_and_the_searches_counted(fake, finder_a, finder_b, request_):
    calls = [{"type": "web_search_call", "action": {"type": "search", "query": q}} for q in ("a", "b", "c")]
    fake.reply(a_reply(calls=calls, usage={}))
    fake.reply(b_reply(usage=None) | {"usage": None})
    a = (await finder_a.find(request_, stage=STAGE_A)).record
    b = (await finder_b.find(request_, stage=STAGE_B)).record
    assert a.estimated and b.estimated
    assert (a.input_tokens, a.output_tokens) == estimate(a.request, 300)
    assert a.cost_usd == pytest.approx((a.input_tokens * 0.10 + 300 * 0.50) / 1e6 + 3 * 0.010)
    assert (b.input_tokens, b.output_tokens) == estimate(b.request, 300)
    assert b.cost_usd == pytest.approx((b.input_tokens * 0.75 + 300 * 3.75) / 1e6 + 1 * 0.0025)
    assert b.provider_cost_usd is None and b.charged_usd == b.cost_usd


async def test_a_timeout_is_charged_an_estimate_with_the_typical_searches(fake, test_config, session, request_):
    slow = make_fact_finder(B, test_config, KEYS, session, base_url=fake.url("/v1"), timeout_s=0.2)
    fake.reply(b_reply(), delay_s=1)
    with pytest.raises(ModelError) as caught:
        await slow.find(request_, stage=STAGE_B)
    e = caught.value
    assert e.kind == e.record.error == "timeout"
    assert "0.2 s" in e.record.error_text
    r = e.record
    assert r.estimated and r.response is None and 0.2 <= r.elapsed_s < 1
    assert (r.input_tokens, r.output_tokens) == estimate(r.request, 300)
    assert r.cost_usd == pytest.approx((r.input_tokens * 0.75 + 300 * 3.75) / 1e6 + 1 * 0.0025)
    assert (r.prompt, r.fields) == ("fact-finding", request_.values())


@pytest.mark.parametrize(
    ("status", "kind", "code"),
    [(429, "rate-limited", "rate_limit_exceeded"), (500, "unavailable", "server_error"),
     (503, "unavailable", "server_error"), (401, "unavailable", "invalid_api_key"),
     (400, "unavailable", "invalid_request_error")],
)
@pytest.mark.parametrize("which", ["a", "b"])
async def test_http_errors(fake, finder_a, finder_b, request_, status, kind, code, which):
    finder, stage = (finder_a, STAGE_A) if which == "a" else (finder_b, STAGE_B)
    error = {"error": {"message": f"Something about {CANDIDATE} ({status})", "type": "api_error", "code": code}}
    fake.reply(error, status=status)
    with pytest.raises(ModelError) as caught:
        await finder.find(request_, stage=stage)
    e = caught.value
    assert e.kind == kind
    assert (e.record.status, e.record.error_code) == (status, code)
    assert e.record.error_text == f"HTTP {status}: {json.dumps(error)}"
    r = e.record
    assert r.estimated and (r.input_tokens, r.output_tokens) == estimate(r.request, 300)
    # A request refused with a 4xx ran no search; after a 5xx, the typical searches may have.
    price = PRICES["openai"]["gpt-test"] if which == "a" else PRICES["perplexity"]["google/gemini-test"]
    searched = 0 if status < 500 else 1 * price.search
    assert r.cost_usd == pytest.approx((r.input_tokens * price.input + 300 * price.output) / 1e6 + searched)
    assert str(e) == f"{stage} via {'openai' if which == 'a' else 'perplexity'}: {kind} (HTTP {status})"


async def test_a_body_that_isnt_json_is_bad_output(fake, finder_b, request_):
    fake.reply("<html>Bad gateway, sort of</html>")
    with pytest.raises(ModelError) as caught:
        await finder_b.find(request_, stage=STAGE_B)
    assert caught.value.kind == "bad output"
    assert caught.value.record.response == {"raw_text": "<html>Bad gateway, sort of</html>"}
    assert caught.value.record.estimated


# --- The factory ---------------------------------------------------------------------------------


def test_the_config_files_fact_finders_can_be_made(config, session):
    a = make_fact_finder(config.stages.fact_finder_a, config, KEYS, session)
    b = make_fact_finder(config.stages.fact_finder_b, config, KEYS, session)
    assert a.url == "https://api.openai.com/v1/responses"
    assert b.url == "https://api.perplexity.ai/v1/agent"
    assert a.timeout_s == b.timeout_s == 30
    assert (key_name(config.stages.fact_finder_a), key_name(config.stages.fact_finder_b)) == (
        "OPENAI_API_KEY", "PERPLEXITY_API_KEY",
    )


def test_the_factory_refuses_what_it_cant_run(test_config, session):
    with pytest.raises(ValueError, match="no fact-finding adapter for provider 'openrouter'"):
        make_fact_finder(Stage("openrouter", "jev-test", {}), test_config, KEYS, session)
    with pytest.raises(ValueError, match="unknown parameter store"):
        make_fact_finder(dataclasses.replace(B, params=B.params | {"store": True}), test_config, KEYS, session)
    with pytest.raises(ValueError, match="PERPLEXITY_API_KEY is not set"):
        make_fact_finder(B, test_config, {"OPENAI_API_KEY": "x"}, session)
    no_search = dataclasses.replace(test_config, prices=PRICES | {
        "openai": {"gpt-test": Price(input=0.10, cached=0.01, output=0.50)},
    })
    with pytest.raises(ValueError, match="needs a search price"):
        make_fact_finder(A, no_search, KEYS, session)


async def test_store_false_and_forced_search_are_sent_whatever_the_config_says(fake, test_config, session, request_):
    bare = make_fact_finder(dataclasses.replace(A, params={}), test_config, KEYS, session, base_url=fake.url("/v1"))
    fake.reply(a_reply())
    await bare.find(request_, stage=STAGE_A)
    assert fake.body["store"] is False and fake.body["tool_choice"] == "required"
    assert "reasoning" not in fake.body
