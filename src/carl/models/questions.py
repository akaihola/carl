"""Typed prompt files: one question and a description for each choice.

A typed prompt (`decision.md`, `settle.md`, `fact-checking.md`,
`same-fact.md`) has a `# Question` section and a `# Choices` section, each
choice a list item written ``- `choice`: description``. It has no
`{placeholders}`: its fields are named in the text in backticks, and each
adapter presents them its own way (as labelled text to an LLM, as `state` to
Jev). A choice with `Cn` in it, such as `same as Cn`, stands for one choice
per candidate id given when the question is filled in.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..prompts import Prompt, PromptError
from . import Question

CHOICE = re.compile(r"- `([^`]+)`:\s*(.*)", re.S)
TEMPLATE_ID = re.compile(r"\bCn\b")
# A field named in backticks: a lower-case identifier.
NAMED = re.compile(r"`([a-z][a-z0-9_]*)`")


def sections(text: str) -> dict[str, str]:
    """Split a prompt file into its `# Heading` sections, by lower-case heading."""
    parts: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("# "):
            current = parts.setdefault(line[2:].strip().lower(), [])
        elif current is not None:
            current.append(line)
    return {name: "\n".join(lines).strip() for name, lines in parts.items()}


@dataclass(frozen=True)
class TypedPrompt:
    """A typed prompt file, read. `choices` keeps `Cn` choices as written."""

    name: str
    version: str
    question: str
    choices: dict[str, str]
    fields: frozenset[str]

    @classmethod
    def load(cls, prompt: Prompt) -> TypedPrompt:
        where = f"prompts/{prompt.name}.md"
        if prompt.placeholders:
            raise PromptError(f"{where}: a typed prompt names its fields in backticks, not {{placeholders}}")
        parts = sections(prompt.text)
        for heading in ("question", "choices"):
            if not parts.get(heading):
                raise PromptError(f"{where}: no # {heading.capitalize()} section")
        choices: dict[str, str] = {}
        for item in re.split(r"\n(?=- `)", parts["choices"]):
            m = CHOICE.fullmatch(item.strip())
            if not m:
                raise PromptError(f"{where}: can't read the choice {item!r}")
            choices[m.group(1)] = " ".join(m.group(2).split())
        question = " ".join(parts["question"].split())
        named = set(NAMED.findall(question))
        for description in choices.values():
            named.update(NAMED.findall(description))
        return cls(prompt.name, prompt.version, question, choices, frozenset(named - choices.keys()))

    def fill(self, fields: Mapping[str, str], ids: Sequence[str] | Mapping[str, Sequence[str]] = ()) -> Question:
        """The question, asked about `fields`.

        Each `Cn` choice becomes one choice per id: `ids` is either the ids
        for every such choice, or the ids for each choice as written
        (`{"settles Cn": ["C1", "C2"], "agrees with Cn": ["C3"]}`). A `Cn`
        choice with no ids is left out. Fails if a field the prompt names is
        missing.
        """
        missing = self.fields - fields.keys()
        if missing:
            raise PromptError(f"prompts/{self.name}.md: no value for {', '.join(sorted(missing))}")
        choices: dict[str, str] = {}
        for choice, description in self.choices.items():
            if not TEMPLATE_ID.search(choice):
                choices[choice] = description
                continue
            for cid in ids.get(choice, ()) if isinstance(ids, Mapping) else ids:
                choices[TEMPLATE_ID.sub(cid, choice)] = TEMPLATE_ID.sub(cid, description)
        return Question(self.name, self.version, self.question, choices, dict(fields))
