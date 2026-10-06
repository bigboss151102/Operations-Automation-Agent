"""Load versioned prompt files (``src/prompts/<name>.md``) with YAML frontmatter.

Prompt text never lives in ``.py`` files. Files without variables are returned as-is; files that
declare ``variables`` are rendered with ``string.Template`` (``$name``), so literal dollar signs in
them must be written ``$$``.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template

import yaml

PROMPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: int
    description: str
    text: str
    variables: frozenset[str]

    def render(self, **values: str) -> str:
        if not self.variables:
            return self.text
        missing = self.variables - values.keys()
        if missing:
            raise KeyError(f"Prompt {self.name!r} needs values for {sorted(missing)}")
        return Template(self.text).substitute(values)


def _parse(path: Path) -> Prompt:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path.name}: missing YAML frontmatter")
    _, front, body = raw.split("---\n", 2)  # maxsplit=2: later '---' lines in the body are safe
    meta = yaml.safe_load(front)
    return Prompt(
        name=str(meta["name"]),
        version=int(meta["version"]),
        description=str(meta.get("description", "")),
        text=body.strip(),
        variables=frozenset(meta.get("variables") or []),
    )


@cache
def load_prompt(name: str) -> Prompt:
    prompt = _parse(PROMPTS_DIR / f"{name}.md")
    if prompt.name != name:
        raise ValueError(f"{name}.md declares name {prompt.name!r}")
    return prompt


def available_prompts() -> list[str]:
    return sorted(path.stem for path in PROMPTS_DIR.glob("*.md"))
