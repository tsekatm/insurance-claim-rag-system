"""Versioned prompt templates loaded from prompts/{name}/v{version}.yaml (LLD §4.3, §6.4)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from claims_rag.errors import PromptFormatError, PromptNotFoundError, PromptVariableError

_FILE = re.compile(r"^v(\d+(?:\.\d+)*)\.yaml$")


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system: str
    user_template: str
    required_vars: tuple[str, ...]
    temperature: float
    max_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RenderedPrompt:
    name: str
    version: str
    system: str
    user: str
    temperature: float
    max_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _load(path: Path, name: str, version: str) -> PromptTemplate:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise PromptFormatError(f"{path}: invalid YAML") from exc
    if not isinstance(raw, dict):
        raise PromptFormatError(f"{path}: expected a mapping")
    try:
        params = raw["params"]
        template = PromptTemplate(
            name=str(raw["name"]),
            version=str(raw["version"]),
            system=str(raw["system"]),
            user_template=str(raw["user_template"]),
            required_vars=tuple(str(v) for v in raw["required_vars"]),
            temperature=float(params["temperature"]),
            max_tokens=int(params["max_tokens"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PromptFormatError(f"{path}: missing or invalid field ({exc})") from exc
    if (template.name, template.version) != (name, version):
        raise PromptFormatError(f"{path}: name/version do not match the file location")
    unused = [v for v in template.required_vars if f"{{{v}}}" not in template.user_template]
    if unused:
        raise PromptFormatError(f"{path}: required_vars not in user_template: {unused}")
    return template


class PromptTemplateManager:
    """Loads and validates every prompt file eagerly, so a bad file fails at startup, not mid-run."""

    def __init__(self, prompts_dir: Path) -> None:
        self._templates: dict[str, dict[str, PromptTemplate]] = {}
        for path in sorted(prompts_dir.glob("*/v*.yaml")):
            match = _FILE.match(path.name)
            if not match:
                raise PromptFormatError(f"{path}: file name must be v<major>.<minor>.yaml")
            name, version = path.parent.name, match.group(1)
            self._templates.setdefault(name, {})[version] = _load(path, name, version)

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        versions = self._templates.get(name)
        if not versions:
            raise PromptNotFoundError(f"no prompt named {name!r}")
        if version is None:
            version = max(versions, key=_version_key)
        if version not in versions:
            raise PromptNotFoundError(f"prompt {name!r} has no version {version!r}")
        return versions[version]

    def render(self, name: str, variables: Mapping[str, str], version: str | None = None) -> RenderedPrompt:
        template = self.get(name, version)
        missing = sorted(set(template.required_vars) - set(variables))
        extra = sorted(set(variables) - set(template.required_vars))
        if missing or extra:
            raise PromptVariableError(f"{name} v{template.version}: missing {missing}, unexpected {extra}")
        # One pass over the template: only {var} for declared vars is replaced, so literal JSON braces survive
        # and a value that itself contains "{other}" is never substituted again.
        pattern = re.compile("|".join(re.escape(f"{{{v}}}") for v in template.required_vars))
        user = pattern.sub(lambda m: variables[m.group(0)[1:-1]], template.user_template)
        return RenderedPrompt(
            name=template.name,
            version=template.version,
            system=template.system,
            user=user,
            temperature=template.temperature,
            max_tokens=template.max_tokens,
        )
