import asyncio
import dataclasses
import json
import math
import socket

import aiohttp
import pytest
from aiohttp import web

from carl.config import Price, Stage
from carl.models import ModelError, Question, http_session, make_typed_model
from carl.models.questions import TypedPrompt
from carl.prompts import Prompt, PromptError, version

DECISION = """# Question

Is `utterance` worth fact-checking? `conversation` holds the lines said
before it, and `place_and_time` says where and when.

# Choices

- `claim`: `utterance` states something checkable.
- `open question`: `utterance` wonders about something a source can answer.
- `same as Cn`: `utterance` says the same as the earlier candidate Cn in
  `earlier_candidates`.
- `none`: anything else.
"""

FIELDS = {
    "place_and_time": "Kallio, Helsinki, Finland. Sunday 27 September 2026, 19:30",
    "earlier_candidates": "C1: Einstein failed maths.\nC2: The Great Wall is visible from space.",
    "conversation": "A: Mennään Kiinaan.",
    "utterance": "B: Muurin näkee avaruudesta.",
}

LUNA = Stage("openai", "gpt-test", {"reasoning_effort": "none", "top_logprobs": 20, "max_output_tokens": 200})
JEV = Stage("openrouter", "jev-test", {})
PRICES = {
    "openai": {"gpt-test": Price(input=0.10, cached=0.01, output=0.50)},
    "openrouter": {"jev-test": Price(input=0.042, cached=0.0, output=0.0)},
}
KEYS = {"OPENAI_API_KEY": "sk-test-openai", "OPENROUTER_API_KEY": "sk-test-openrouter"}


def typed_prompt(text: str = DECISION, name: str = "decision") -> TypedPrompt:
    return TypedPrompt.load(Prompt(name, text, version(text.encode()), frozenset()))


@pytest.fixture
def question() -> Question:
    return typed_prompt().fill(FIELDS, ["C1", "C2"])


# --- Typed prompt files ----------------------------------------------------------------


def test_a_typed_prompt_is_read():
    typed = typed_prompt()
    assert typed.name == "decision" and typed.version == version(DECISION.encode())
    assert typed.question.startswith("Is `utterance` worth fact-checking? `conversation` holds")
    assert list(typed.choices) == ["claim", "open question", "same as Cn", "none"]
    assert typed.choices["same as Cn"] == "`utterance` says the same as the earlier candidate Cn in `earlier_candidates`."
    assert typed.fields == {"utterance", "conversation", "place_and_time", "earlier_candidates"}


def test_same_as_cn_becomes_one_choice_per_id(question):
    assert list(question.choices) == ["claim", "open question", "same as C1", "same as C2", "none"]
    assert "the earlier candidate C2 in" in question.choices["same as C2"]
    assert question.prompt == "decision" and question.fields == FIELDS


def test_with_no_ids_there_is_no_same_as_choice():
    assert list(typed_prompt().fill(FIELDS).choices) == ["claim", "open question", "none"]


def test_each_cn_choice_can_get_its_own_ids():
    settle = typed_prompt(
        "# Question\n\nDoes `utterance` settle one?\n\n# Choices\n\n- `none`: no.\n"
        "- `settles Cn`: settles Cn.\n- `agrees with Cn`: agrees.\n- `disputes Cn`: disputes.\n",
        "settle",
    )
    question = settle.fill({"utterance": "x"}, {"settles Cn": ["C1", "C2"], "agrees with Cn": ["C3"], "disputes Cn": ["C3"]})
    assert list(question.choices) == ["none", "settles C1", "settles C2", "agrees with C3", "disputes C3"]


def test_a_named_field_left_out_fails():
    with pytest.raises(PromptError, match="no value for earlier_candidates"):
        typed_prompt().fill({k: v for k, v in FIELDS.items() if k != "earlier_candidates"})
    # Fields the prompt doesn't name may still be given.
    assert "date_time" in typed_prompt().fill(FIELDS | {"date_time": "now"}).fields


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("# Question\n\nIs {utterance} a claim?\n\n# Choices\n\n- `claim`: yes.\n", "not {placeholders}"),
        ("# Question\n\nIs `utterance` a claim?\n", "no # Choices section"),
        ("# Choices\n\n- `claim`: yes.\n", "no # Question section"),
        ("# Question\n\nIs it?\n\n# Choices\n\nPick one:\n- `claim`: yes.\n", "can't read the choice"),
    ],
)
def test_a_malformed_typed_prompt_fails(text, problem):
    with pytest.raises(PromptError, match=problem):
        TypedPrompt.load(Prompt("decision", text, "12345678", frozenset({"utterance"}) if "{" in text else frozenset()))


# --- Fake providers ----------------------------------------------------------------------


class Fake:
    """A fake provider: records each request and answers as the test says."""

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


@pytest.fixture
async def fake(aiohttp_server) -> Fake:
    fake = Fake()
    app = web.Application()
    app.router.add_post("/v1/responses", fake.handle)
    app.router.add_post("/api/v1/systemone", fake.handle)
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
def luna(fake, test_config, session):
    return make_typed_model(LUNA, test_config, KEYS, session, base_url=fake.url("/v1"), timeout_s=2)


@pytest.fixture
def jev(fake, test_config, session):
    return make_typed_model(JEV, test_config, KEYS, session, base_url=fake.url("/api/v1"), timeout_s=2)


def ln(p: float) -> float:
    return math.log(p)


def luna_reply(answer: str, tokens=None, usage=None, **extra) -> dict:
    """A Responses API reply. `tokens`: [(token, p, [(alternative, p)…])…]."""
    if tokens is None:
        tokens = [('{"', 1, []), ("answer", 1, []), ('":"', 1, []), (answer, 1, []), ('"}', 1, [])]
    logprobs = [
        {"token": t, "logprob": ln(p), "top_logprobs": [{"token": a, "logprob": ln(q)} for a, q in alts]}
        for t, p, alts in tokens
    ]
    text = json.dumps({"answer": answer}, separators=(",", ":"))
    usage = {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 200}, "output_tokens": 20} if usage is None else usage
    return {
        "id": "resp_1", "model": "gpt-test-2026-09-01", "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text, "logprobs": logprobs}]}],
        "usage": usage,
    } | extra


def jev_reply(choice: str, probabilities=None, usage=None) -> dict:
    answer = {"type": "choice", "choice": choice, "confidence": 0.9}
    if probabilities is not None:
        answer["probabilities"] = probabilities
    return {
        "model": "jev-test-20260917", "answers": {"answer": answer}, "provider": "TypeSafe",
        "usage": {"input_tokens": 648, "output_tokens": 45, "cost": 2.8e-05} if usage is None else usage,
    }


def estimate(request: dict, output_tokens: int) -> tuple[int, int]:
    return math.ceil(len(json.dumps(request, ensure_ascii=False)) / 4), output_tokens


# --- The OpenAI adapter ----------------------------------------------------------------------


async def test_luna_request(fake, luna, question):
    fake.reply(luna_reply("claim"))
    await luna.ask(question, stage="decision")
    path, headers, body = fake.requests[0]
    assert path == "/v1/responses"
    assert headers["Authorization"] == "Bearer sk-test-openai"
    assert body["model"] == "gpt-test"
    assert body["store"] is False
    assert body["reasoning"] == {"effort": "none"}
    assert body["include"] == ["message.output_text.logprobs"]
    assert body["top_logprobs"] == 20 and body["max_output_tokens"] == 200
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert fmt["schema"]["properties"]["answer"]["enum"] == list(question.choices)
    assert fmt["schema"]["additionalProperties"] is False
    system, user = body["input"]
    assert system["role"] == "system" and system["content"].startswith(question.text)
    assert "- `same as C2`: `utterance` says the same as the earlier candidate C2" in system["content"]
    assert user["role"] == "user"
    assert user["content"].startswith("`place_and_time`:\nKallio, Helsinki")
    assert "`utterance`:\nB: Muurin näkee avaruudesta." in user["content"]


async def test_store_false_is_sent_whatever_the_config_says(fake, test_config, session, question):
    with pytest.raises(ValueError, match="unknown parameter store"):
        make_typed_model(dataclasses.replace(LUNA, params={"store": True}), test_config, KEYS, session)
    bare = make_typed_model(dataclasses.replace(LUNA, params={}), test_config, KEYS, session, base_url=fake.url("/v1"))
    fake.reply(luna_reply("none", tokens=[]))
    answer = await bare.ask(question, stage="decision")
    body = fake.requests[0][2]
    assert body["store"] is False
    assert "include" not in body and "top_logprobs" not in body and "reasoning" not in body
    assert answer.probs is None


async def test_luna_answer_and_record(fake, luna, question):
    fake.reply(luna_reply("claim"))
    answer = await luna.ask(question, stage="decision")
    assert answer.answer == "claim"
    assert answer.probs == {"claim": 1.0}
    r = answer.record
    assert (r.stage, r.provider, r.model) == ("decision", "openai", "gpt-test-2026-09-01")
    assert (r.prompt, r.version, r.fields) == ("decision", question.version, FIELDS)
    assert r.params == LUNA.params
    assert (r.input_tokens, r.cached_tokens, r.output_tokens) == (1000, 200, 20)
    assert r.cost_usd == pytest.approx((800 * 0.10 + 200 * 0.01 + 20 * 0.50) / 1e6)
    assert r.provider_cost_usd is None and r.charged_usd == r.cost_usd
    assert not r.estimated and r.error is None
    assert r.request == fake.requests[0][2]
    assert r.response["id"] == "resp_1"
    assert r.status == 200 and 0 < r.elapsed_s < 2
    assert json.loads(json.dumps(r.event()))["started_at"] == r.started_at.isoformat()


async def test_luna_probabilities_pool_same_as_off_the_chosen_path(fake, luna, question):
    tokens = [
        ('{"', 1, []), ("answer", 1, []), ('":"', 1, []),
        ("claim", 0.7, [("claim", 0.7), ("same", 0.2), ("none", 0.05)]),
        ('"}', 1, []),
    ]
    fake.reply(luna_reply("claim", tokens))
    probs = (await luna.ask(question, stage="decision")).probs
    assert probs == pytest.approx({"claim": 0.7, "same as *": 0.2, "none": 0.05, "other": 0.05})


async def test_luna_probabilities_name_each_same_as_on_the_chosen_path(fake, luna, question):
    tokens = [
        ('{"', 1, []), ("answer", 1, []), ('":"', 1, []),
        ("same", 0.6, [("same", 0.6), ("claim", 0.3)]),
        (" as", 1, []), (" C", 1, []),
        ("2", 0.6, [("2", 0.6), ("1", 0.3), ("7", 0.1)]),
        ('"}', 1, []),
    ]
    fake.reply(luna_reply("same as C2", tokens))
    answer = await luna.ask(question, stage="decision")
    assert answer.answer == "same as C2"
    assert answer.probs == pytest.approx(
        {"claim": 0.3, "same as C2": 0.36, "same as C1": 0.18, "other": 0.1 + 0.06}
    )
    assert sum(answer.probs.values()) == pytest.approx(1)


async def test_luna_ids_sharing_a_prefix_are_told_apart(fake, luna):
    question = typed_prompt().fill(FIELDS, ["C2", "C21"])
    tokens = [
        ('{"', 1, []), ("answer", 1, []), ('":"', 1, []),
        ("same", 1, []), (" as", 1, []), (" C", 1, []), ("2", 1, []),
        ('"}', 0.8, [('"}', 0.8), ("1", 0.2)]),
    ]
    fake.reply(luna_reply("same as C2", tokens))
    probs = (await luna.ask(question, stage="decision")).probs
    assert probs == pytest.approx({"same as C2": 0.8, "same as C21": 0.2})


async def test_luna_value_starting_inside_a_token(fake, luna, question):
    tokens = [('{"answer', 1, []), ('":"cl', 0.8, [('":"cl', 0.8), ('":"no', 0.15)]), ('aim"}', 1, [])]
    fake.reply(luna_reply("claim", tokens))
    probs = (await luna.ask(question, stage="decision")).probs
    assert probs == pytest.approx({"claim": 0.8, "none": 0.15, "other": 0.05})


async def test_luna_mass_that_could_be_several_choices_is_ambiguous(fake, luna):
    verdict = typed_prompt(
        "# Question\n\nIs `card` supported?\n\n# Choices\n\n- `supported`: yes.\n"
        "- `not supported`: no.\n- `not sure`: can't tell.\n",
        "fact-checking",
    ).fill({"card": "x"})
    tokens = [
        ('{"', 1, []), ("answer", 1, []), ('":"', 1, []),
        ("supported", 0.9, [("supported", 0.9), ("not", 0.1)]),
        ('"}', 1, []),
    ]
    fake.reply(luna_reply("supported", tokens))
    probs = (await luna.ask(verdict, stage="fact-checking")).probs
    assert probs == pytest.approx({"supported": 0.9, "ambiguous": 0.1})


async def test_luna_without_usage_is_estimated(fake, luna, question):
    fake.reply(luna_reply("claim", usage={}))
    r = (await luna.ask(question, stage="decision")).record
    assert r.estimated
    assert (r.input_tokens, r.output_tokens) == estimate(r.request, 15)
    assert r.cost_usd == pytest.approx((r.input_tokens * 0.10 + 15 * 0.50) / 1e6)


# --- Typed errors ---------------------------------------------------------------------------


async def test_a_timeout_is_charged_an_estimate(fake, test_config, session, question):
    slow = make_typed_model(LUNA, test_config, KEYS, session, base_url=fake.url("/v1"), timeout_s=0.2)
    fake.reply(luna_reply("claim"), delay_s=1)
    with pytest.raises(ModelError) as caught:
        await slow.ask(question, stage="decision")
    e = caught.value
    assert e.kind == e.record.error == "timeout"
    assert "0.2 s" in e.record.error_text
    assert e.record.estimated and e.record.cost_usd > 0
    assert (e.record.input_tokens, e.record.output_tokens) == estimate(e.record.request, 15)
    assert e.record.response is None and 0.2 <= e.record.elapsed_s < 1


@pytest.mark.parametrize(
    ("status", "kind", "code"),
    [(429, "rate-limited", "rate_limit_exceeded"), (500, "unavailable", "server_error"),
     (503, "unavailable", "server_error"), (401, "unavailable", "invalid_api_key"),
     (400, "unavailable", "invalid_request_error")],
)
async def test_http_errors(fake, luna, question, status, kind, code):
    error = {"error": {"message": f"Something about B: Muurin näkee avaruudesta ({status})", "code": code}}
    if status == 400:
        error["error"] = {"message": "Bad schema", "type": "invalid_request_error", "code": None}
    fake.reply(error, status=status)
    with pytest.raises(ModelError) as caught:
        await luna.ask(question, stage="decision")
    e = caught.value
    assert e.kind == kind
    assert (e.record.status, e.record.error_code) == (status, code)
    assert e.record.error_text == f"HTTP {status}: {json.dumps(error)}"
    assert e.record.response == error
    assert e.record.estimated
    # The exception's own message never carries the provider's text.
    assert str(e) == f"decision via openai: {kind} (HTTP {status})"


async def test_an_unreachable_provider_is_unavailable(test_config, session, question):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    closed = make_typed_model(LUNA, test_config, KEYS, session, base_url=f"http://127.0.0.1:{port}/v1")
    with pytest.raises(ModelError) as caught:
        await closed.ask(question, stage="decision")
    assert caught.value.kind == "unavailable"
    assert "Cannot connect" in caught.value.record.error_text
    assert caught.value.record.estimated and caught.value.record.status is None


async def test_a_body_that_isnt_json_is_bad_output(fake, luna, question):
    fake.reply("<html>Bad gateway, sort of</html>")
    with pytest.raises(ModelError) as caught:
        await luna.ask(question, stage="decision")
    e = caught.value
    assert e.kind == "bad output"
    assert e.record.response == {"raw_text": "<html>Bad gateway, sort of</html>"}
    assert e.record.estimated


@pytest.mark.parametrize(
    ("text", "detail"),
    [('{"answer":"maybe"}', "answer 'maybe' is not one of the choices"),
     ("I think it's a claim", "not the expected JSON"),
     ('{"verdict":"claim"}', "not the expected JSON")],
)
async def test_an_answer_outside_the_choices_is_bad_output_at_its_real_cost(fake, luna, question, text, detail):
    reply = luna_reply("claim", tokens=[])
    reply["output"][0]["content"][0]["text"] = text
    fake.reply(reply)
    with pytest.raises(ModelError) as caught:
        await luna.ask(question, stage="decision")
    e = caught.value
    assert e.kind == "bad output" and detail in e.record.error_text
    assert not e.record.estimated and e.record.input_tokens == 1000


async def test_a_refusal_is_bad_output(fake, luna, question):
    reply = luna_reply("claim")
    reply["output"][0]["content"] = [{"type": "refusal", "refusal": "I can't help with that."}]
    fake.reply(reply)
    with pytest.raises(ModelError) as caught:
        await luna.ask(question, stage="decision")
    assert caught.value.kind == "bad output"
    assert caught.value.record.error_text == "refusal: I can't help with that."


async def test_an_incomplete_or_failed_run(fake, luna, question):
    fake.reply(luna_reply("claim", status="incomplete", incomplete_details={"reason": "max_output_tokens"}))
    fake.reply(luna_reply("claim", status="failed", error={"code": "server_error", "message": "oops"}))
    with pytest.raises(ModelError) as incomplete:
        await luna.ask(question, stage="decision")
    assert incomplete.value.kind == "bad output"
    assert "max_output_tokens" in incomplete.value.record.error_text
    with pytest.raises(ModelError) as failed:
        await luna.ask(question, stage="decision")
    assert failed.value.kind == "unavailable"
    assert "oops" in failed.value.record.error_text


# --- The OpenRouter adapter for Jev -------------------------------------------------------------


@pytest.fixture
def verdict() -> Question:
    return typed_prompt(
        "# Question\n\nDoes `excerpt` support `card_fact`?\n\n# Choices\n\n- `supported`: it does.\n"
        "- `not supported`: it doesn't.\n- `doesn't answer the candidate`: off the point.\n",
        "fact-checking",
    ).fill({"card_fact": "Kiinan muuria ei näe avaruudesta.", "excerpt": "The wall is not visible from orbit."})


async def test_jev_request(fake, jev, verdict):
    fake.reply(jev_reply("supported", {"supported": 0.9, "not supported": 0.1, "doesn't answer the candidate": 0}))
    await jev.ask(verdict, stage="fact-checking")
    path, headers, body = fake.requests[0]
    assert path == "/api/v1/systemone"
    assert headers["Authorization"] == "Bearer sk-test-openrouter"
    assert body == {
        "model": "jev-test",
        "state": {"card_fact": "Kiinan muuria ei näe avaruudesta.", "excerpt": "The wall is not visible from orbit."},
        "questions": {"answer": {"type": "choice", "instructions": verdict.text, "criteria": dict(verdict.choices)}},
    }


async def test_jev_answer_probabilities_and_both_costs(fake, jev, verdict):
    probabilities = {"supported": 0.9, "not supported": 0.1, "doesn't answer the candidate": 0}
    fake.reply(jev_reply("supported", probabilities))
    answer = await jev.ask(verdict, stage="fact-checking")
    assert answer.answer == "supported"
    assert answer.probs == probabilities
    r = answer.record
    assert (r.stage, r.provider, r.model) == ("fact-checking", "openrouter", "jev-test-20260917")
    assert (r.input_tokens, r.cached_tokens, r.output_tokens) == (648, 0, 45)
    assert r.cost_usd == pytest.approx(648 * 0.042 / 1e6)
    assert r.provider_cost_usd == 2.8e-05 and r.charged_usd == 2.8e-05
    assert not r.estimated and r.params == {}


async def test_jev_without_probabilities(fake, jev, verdict):
    fake.reply(jev_reply("not supported"))
    answer = await jev.ask(verdict, stage="fact-checking")
    assert (answer.answer, answer.probs) == ("not supported", None)


async def test_jev_without_usage_is_estimated(fake, jev, verdict):
    fake.reply(jev_reply("supported", usage={}))
    r = (await jev.ask(verdict, stage="fact-checking")).record
    assert r.estimated and r.provider_cost_usd is None
    assert (r.input_tokens, r.output_tokens) == estimate(r.request, 45)
    assert r.cost_usd == pytest.approx(r.input_tokens * 0.042 / 1e6)


async def test_jev_choice_outside_the_choices_is_bad_output(fake, jev, verdict):
    fake.reply(jev_reply("maybe", {"maybe": 1.0}))
    fake.reply({"model": "jev-test", "usage": {"input_tokens": 10, "output_tokens": 0, "cost": 1e-7}})
    for _ in range(2):
        with pytest.raises(ModelError) as caught:
            await jev.ask(verdict, stage="fact-checking")
        assert caught.value.kind == "bad output"
        assert not caught.value.record.estimated
    assert "no answer" in caught.value.record.error_text


@pytest.mark.parametrize(("status", "kind"), [(402, "unavailable"), (429, "rate-limited"), (502, "unavailable")])
async def test_jev_http_errors(fake, jev, verdict, status, kind):
    error = {"error": {"code": status, "message": "Insufficient credits" if status == 402 else "busy"}}
    fake.reply(error, status=status)
    with pytest.raises(ModelError) as caught:
        await jev.ask(verdict, stage="fact-checking")
    e = caught.value
    assert e.kind == kind and e.record.error_code == str(status)
    assert e.record.estimated and e.record.provider_cost_usd is None


async def test_jev_timeout(fake, test_config, session, verdict):
    slow = make_typed_model(JEV, test_config, KEYS, session, base_url=fake.url("/api/v1"), timeout_s=0.2)
    fake.reply(jev_reply("supported"), delay_s=1)
    with pytest.raises(ModelError) as caught:
        await slow.ask(verdict, stage="fact-checking")
    assert caught.value.kind == "timeout"
    assert caught.value.record.estimated
    assert caught.value.record.output_tokens == 45


# --- Choosing an adapter ----------------------------------------------------------------------


async def test_the_configured_stages_get_their_adapters(config, session):
    keys = {"OPENAI_API_KEY": "k", "OPENROUTER_API_KEY": "k"}
    for stage in (config.stages.decision, config.stages.fact_checking):
        model = make_typed_model(stage, config, keys, session)
        assert model.provider == stage.provider


async def test_what_the_factory_refuses(test_config, session):
    with pytest.raises(ValueError, match="no typed-answer adapter for provider 'perplexity'"):
        make_typed_model(Stage("perplexity", "gpt-test", {}), test_config, KEYS, session)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is not set"):
        make_typed_model(JEV, test_config, {"OPENAI_API_KEY": "k", "OPENROUTER_API_KEY": ""}, session)
    with pytest.raises(ValueError, match="unknown parameter temperature"):
        make_typed_model(dataclasses.replace(JEV, params={"temperature": 0}), test_config, KEYS, session)
    no_output_price = dataclasses.replace(test_config, prices={"openai": {"gpt-test": Price(input=0.1)}})
    with pytest.raises(ValueError, match="needs input and output prices"):
        make_typed_model(LUNA, no_output_price, KEYS, session)


async def test_the_shared_session_honours_the_proxy_settings():
    async with http_session() as session:
        assert session.trust_env
