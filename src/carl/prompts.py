"""The prompt files under `prompts/` (First working Carl spec, section 7).

One file per prompt, with `{placeholders}` the server fills in. Prompts
belong to the pipeline, not to an adapter, and no prompt text exists anywhere
else. A prompt's version is a short content hash of its file.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

# A placeholder is a lower-case name in braces. Other braces, such as a JSON
# example, are left alone.
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

# The values the pipeline fills into each prompt, by prompt name. A stage's
# prompt joins this table with the build step that makes the stage.
FILLS: dict[str, frozenset[str]] = {"decision": frozenset()}  # typed prompts name their fields in backticks


class PromptError(Exception):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    version: str
    placeholders: frozenset[str]

    def render(self, values: Mapping[str, str]) -> str:
        missing = self.placeholders - values.keys()
        if missing:
            raise PromptError(f"prompts/{self.name}.md: no value for {', '.join(sorted(missing))}")
        return PLACEHOLDER.sub(lambda m: values[m.group(1)], self.text)


def version(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


def load_prompts(folder: Path, fills: Mapping[str, Collection[str]] = FILLS) -> dict[str, Prompt]:
    """Every prompt in `folder`, checked against what the pipeline fills in.

    Fails if a template has a placeholder that nothing fills, or if a prompt
    the pipeline uses has no file. README.md is not a prompt.
    """
    prompts: dict[str, Prompt] = {}
    problems: list[str] = []
    for path in sorted(folder.glob("*.md")):
        if path.name == "README.md":
            continue
        data = path.read_bytes()
        text = data.decode("utf-8")
        name = path.stem
        placeholders = frozenset(PLACEHOLDER.findall(text))
        unfilled = placeholders - set(fills.get(name, ()))
        if unfilled:
            problems.append(f"{path}: nothing fills {', '.join('{' + p + '}' for p in sorted(unfilled))}")
        prompts[name] = Prompt(name, text, version(data), placeholders)
    for name in sorted(fills.keys() - prompts.keys()):
        problems.append(f"{folder / (name + '.md')}: missing")
    if problems:
        raise PromptError("\n".join(problems))
    return prompts
