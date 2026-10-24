"""LLD §4.3 / §6.4: versioned YAML prompt templates."""

from pathlib import Path

import pytest

from claims_rag.components.prompt_manager import PromptTemplateManager
from claims_rag.errors import PromptFormatError, PromptNotFoundError, PromptVariableError

EXTRACT_V1 = """\
name: extract
version: "1.0"
system: |
  Extract only what the document states.
user_template: |
  Return JSON matching {schema}. Example: {"policy_number": "MOT-123456"}
  Rules: {instructions}
required_vars: [schema, instructions]
params:
  temperature: 0
  max_tokens: 800
"""


def _write(root: Path, name: str, version: str, body: str) -> None:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"v{version}.yaml").write_text(body)


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    _write(tmp_path, "extract", "1.0", EXTRACT_V1)
    _write(
        tmp_path,
        "extract",
        "1.10",
        EXTRACT_V1.replace('"1.0"', '"1.10"').replace("max_tokens: 800", "max_tokens: 900"),
    )
    _write(tmp_path, "extract", "1.9", EXTRACT_V1.replace('"1.0"', '"1.9"'))
    return tmp_path


def test_get_returns_latest_version_compared_numerically(prompts: Path) -> None:
    template = PromptTemplateManager(prompts).get("extract")
    assert template.version == "1.10"
    assert template.max_tokens == 900


def test_get_specific_version(prompts: Path) -> None:
    template = PromptTemplateManager(prompts).get("extract", "1.0")
    assert template.version == "1.0"
    assert template.required_vars == ("schema", "instructions")
    assert template.temperature == 0.0
    assert template.system == "Extract only what the document states.\n"


def test_render_substitutes_only_required_vars_and_keeps_literal_braces(prompts: Path) -> None:
    rendered = PromptTemplateManager(prompts).render(
        "extract", {"schema": "<S>", "instructions": "<I>"}, version="1.0"
    )
    assert rendered.user == 'Return JSON matching <S>. Example: {"policy_number": "MOT-123456"}\nRules: <I>\n'
    assert (rendered.name, rendered.version) == ("extract", "1.0")
    assert (rendered.temperature, rendered.max_tokens) == (0.0, 800)
    assert rendered.system == "Extract only what the document states.\n"


def test_rendered_value_containing_a_placeholder_is_not_substituted_again(prompts: Path) -> None:
    rendered = PromptTemplateManager(prompts).render(
        "extract", {"schema": "{instructions}", "instructions": "X"}, version="1.0"
    )
    assert "matching {instructions}." in rendered.user


def test_render_missing_variable(prompts: Path) -> None:
    with pytest.raises(PromptVariableError, match="instructions"):
        PromptTemplateManager(prompts).render("extract", {"schema": "s"})


def test_render_unexpected_variable(prompts: Path) -> None:
    with pytest.raises(PromptVariableError, match="extra"):
        PromptTemplateManager(prompts).render("extract", {"schema": "s", "instructions": "i", "extra": "x"})


@pytest.mark.parametrize(("name", "version"), [("missing", None), ("extract", "2.0")])
def test_unknown_name_or_version(prompts: Path, name: str, version: str | None) -> None:
    with pytest.raises(PromptNotFoundError):
        PromptTemplateManager(prompts).get(name, version)


@pytest.mark.parametrize(
    "body",
    [
        "not: [valid",  # YAML syntax error
        "- a list",  # not a mapping
        EXTRACT_V1.replace("system: |\n  Extract only what the document states.\n", ""),  # missing key
        EXTRACT_V1.replace("name: extract", "name: assess"),  # name does not match folder
        EXTRACT_V1.replace('version: "1.0"', 'version: "1.1"'),  # version does not match file
        EXTRACT_V1.replace(
            "required_vars: [schema, instructions]", "required_vars: [schema, nope]"
        ),  # unused var
        EXTRACT_V1.replace("max_tokens: 800", "max_tokens: lots"),  # bad param type
    ],
)
def test_malformed_file_fails_at_construction(tmp_path: Path, body: str) -> None:
    _write(tmp_path, "extract", "1.0", body)
    with pytest.raises(PromptFormatError):
        PromptTemplateManager(tmp_path)


def test_to_dict(prompts: Path) -> None:
    rendered = PromptTemplateManager(prompts).render("extract", {"schema": "s", "instructions": "i"})
    assert rendered.to_dict()["version"] == "1.10"
    assert PromptTemplateManager(prompts).get("extract").to_dict()["required_vars"] == (
        "schema",
        "instructions",
    )
