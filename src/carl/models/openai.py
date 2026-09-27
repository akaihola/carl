"""Typed answers from an OpenAI model such as GPT-6 Luna (Responses API).

The question and its choices go in the system message and the fields, as
labelled text, in the user message. A strict JSON schema allows only the
choices, and each choice's probability is read from the answer's token
logprobs (`carl.models.logprobs`). The stage's parameters set the
reasoning effort, the number of top logprobs (logprobs need effort `none`)
and the most output tokens.

`store: false` is always sent, so OpenAI keeps no copy of the conversation.
It is a privacy choice, so it lives here and not in the config file.
"""

from __future__ import annotations

import json
from typing import Any

from . import Question, TypedAnswer
from .calls import HttpAdapter
from .logprobs import Step, answer_probs

# The adapter's own framing of a typed question, like Jev's request format:
# the question and choices come from the prompt file.
ANSWER_WITH = 'Answer with JSON: {"answer": one of the choices below, written exactly as given}.'


def messages(question: Question) -> tuple[str, str]:
    """How an LLM is shown a typed question: (system message, user message)."""
    choices = "\n".join(f"- `{c}`: {d}" for c, d in question.choices.items())
    system = f"{question.text}\n\n{ANSWER_WITH}\n\nChoices:\n{choices}"
    user = "\n\n".join(f"`{name}`:\n{value}" for name, value in question.fields.items())
    return system, user


def answer_schema(choices: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": choices}},
        "required": ["answer"],
        "additionalProperties": False,
    }


def output(body: dict[str, Any]) -> tuple[str, list[Step], str | None]:
    """The answer's text, its tokens' logprobs, and a refusal if there was one."""
    text, steps, refusal = "", [], None
    for item in body.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                text += part.get("text", "")
                for lp in part.get("logprobs") or []:
                    alternatives = [(a["token"], a["logprob"]) for a in lp.get("top_logprobs") or []]
                    steps.append((lp["token"], lp["logprob"], alternatives))
            elif part.get("type") == "refusal":
                refusal = str(part.get("refusal"))
    return text, steps, refusal


class OpenAITyped(HttpAdapter):
    provider = "openai"
    key_name = "OPENAI_API_KEY"
    default_base_url = "https://api.openai.com/v1"
    path = "/responses"
    known_params = frozenset({"reasoning_effort", "top_logprobs", "max_output_tokens"})
    typical_output_tokens = 15  # {"answer":"same as C2"} came to 16 tokens, "claim" to 13

    def request(self, question: Question) -> dict[str, Any]:
        system, user = messages(question)
        body: dict[str, Any] = {
            "model": self.stage.model,
            "store": False,
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "text": {"format": {
                "type": "json_schema", "name": "typed_answer", "strict": True,
                "schema": answer_schema(list(question.choices)),
            }},
        }
        params = self.stage.params
        if "reasoning_effort" in params:
            body["reasoning"] = {"effort": params["reasoning_effort"]}
        if "top_logprobs" in params:
            body["include"] = ["message.output_text.logprobs"]
            body["top_logprobs"] = params["top_logprobs"]
        if "max_output_tokens" in params:
            body["max_output_tokens"] = params["max_output_tokens"]
        return body

    async def ask(self, question: Question, *, stage: str) -> TypedAnswer:
        record = self.start(question, stage, self.request(question))
        body = await self.post(record)
        record.model = str(body.get("model") or record.model)
        usage = body.get("usage")
        if isinstance(usage, dict) and usage:
            details = usage.get("input_tokens_details") or {}
            self.charge(record, usage.get("input_tokens") or 0, details.get("cached_tokens") or 0,
                        usage.get("output_tokens") or 0)
        else:
            self.estimate(record)
        # A 200 can still carry a run that failed or stopped short.
        status = body.get("status")
        if status == "failed":
            raise self.fail(record, "unavailable", f"status failed: {json.dumps(body.get('error'))}")
        if status not in (None, "completed"):
            raise self.fail(record, "bad output", f"status {status}: {json.dumps(body.get('incomplete_details'))}")
        try:
            text, steps, refusal = output(body)
        except (AttributeError, KeyError, TypeError) as e:
            raise self.fail(record, "bad output", f"can't read the output ({e!r}): {json.dumps(body)}") from None
        if refusal is not None:
            raise self.fail(record, "bad output", f"refusal: {refusal}")
        try:
            answer = json.loads(text)["answer"]
        except (ValueError, KeyError, TypeError):
            raise self.fail(record, "bad output", f"not the expected JSON: {text}") from None
        if not isinstance(answer, str) or answer not in question.choices:
            raise self.fail(record, "bad output", f"answer {answer!r} is not one of the choices")
        probs = answer_probs(steps, list(question.choices)) if steps else None
        return TypedAnswer(answer, probs, record)
