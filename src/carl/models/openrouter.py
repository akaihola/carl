"""Typed answers from TypeSafe Jev, through OpenRouter's `/api/v1/systemone`.

That endpoint takes TypeSafe's own request format and is served by TypeSafe
at TypeSafe's price. The fields go as Jev's `state`; the question is one
`choice` question whose `instructions` are the prompt's question and whose
`criteria` are the choices with their descriptions. Jev gives a probability
for every choice itself, and OpenRouter reports the call's cost, which is
recorded beside Carl's own figure. Requests are limited to 32k tokens.

The model is pinned by the config file (`typesafe/jev-1.13`), never the
`~typesafe/jev-latest` alias, which could change the model under Carl.
"""

from __future__ import annotations

import json
from typing import Any

from . import Question, TypedAnswer
from .calls import HttpAdapter


def number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


class JevTyped(HttpAdapter):
    provider = "openrouter"
    key_name = "OPENROUTER_API_KEY"
    default_base_url = "https://openrouter.ai/api/v1"
    path = "/systemone"
    known_params: frozenset[str] = frozenset()
    typical_output_tokens = 45  # what Jev reports for one choice question; its output is free

    def request(self, question: Question) -> dict[str, Any]:
        return {
            "model": self.stage.model,
            "state": dict(question.fields),
            "questions": {
                "answer": {"type": "choice", "instructions": question.text, "criteria": dict(question.choices)},
            },
        }

    async def ask(self, question: Question, *, stage: str) -> TypedAnswer:
        record = self.start(question, stage, self.request(question))
        body = await self.post(record)
        record.model = str(body.get("model") or record.model)
        usage = body.get("usage")
        if isinstance(usage, dict) and usage:
            self.charge(record, usage.get("input_tokens") or 0, 0, usage.get("output_tokens") or 0,
                        number(usage.get("cost")))
        else:
            self.estimate(record)
        answer = (body.get("answers") or {}).get("answer") if isinstance(body.get("answers"), dict) else None
        if not isinstance(answer, dict):
            raise self.fail(record, "bad output", f"no answer: {json.dumps(body)}")
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in question.choices:
            raise self.fail(record, "bad output", f"choice {choice!r} is not one of the choices")
        probs = answer.get("probabilities")
        if isinstance(probs, dict) and all(number(p) is not None for p in probs.values()):
            return TypedAnswer(choice, {str(c): float(p) for c, p in probs.items()}, record)
        return TypedAnswer(choice, None, record)
