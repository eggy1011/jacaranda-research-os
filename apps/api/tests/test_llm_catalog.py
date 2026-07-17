from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from jacaranda_api.llm.catalog import PromptCatalog
from jacaranda_api.llm.errors import PromptCatalogError, UnknownTaskError
from jacaranda_api.llm.models import JsonObject, ValidationFeedback
from jacaranda_api.llm.schema_loader import (
    SchemaLoader,
    canonical_json,
    normalise_json_object,
    safe_feedback_payload,
    validate_instance,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_real_catalog_resolves_every_registered_task_and_bundles_refs() -> None:
    catalog = PromptCatalog(REPOSITORY_ROOT)
    task_names = [
        "extraction",
        "source_verification",
        "company_analysis",
        "industry_analysis",
        "financial_analysis",
        "competition",
        "valuation_narrative",
        "catalysts_risks",
        "translation",
        "slide_compression_plan",
        "slide_compression_slide",
    ]

    tasks = [catalog.resolve(name) for name in task_names]

    assert len(tasks) == 11
    assert tasks[0].prompt_version == "0.1.0"
    assert tasks[0].stage == "S1"
    assert "# S1" in tasks[0].prompt_text
    assert tasks[8].batching == {
        "max_texts_per_call": 20,
        "merge": "concatenate texts arrays; paths are unique keys",
    }
    assert tasks[-1].input_schema is not None
    assert all("$ref" not in canonical_json(task.output_schema) for task in tasks)

    extraction_output = json.loads(
        (
            REPOSITORY_ROOT / "packages/prompts/examples/02-extraction-output.json"
        ).read_text(encoding="utf-8")
    )
    assert not list(Draft202012Validator(tasks[0].output_schema).iter_errors(extraction_output))


def test_catalog_rejects_unknown_task() -> None:
    with pytest.raises(UnknownTaskError):
        PromptCatalog(REPOSITORY_ROOT).resolve("not_registered")


def test_schema_validation_feedback_is_bounded_and_does_not_echo_values() -> None:
    schema: JsonObject = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
        "additionalProperties": False,
    }
    feedback = validate_instance(
        {"name": 123, "count": "secret-value", "extra": True},
        schema,
        stage="S1",
    )

    assert {item.path for item in feedback} == {"/", "/count", "/name"}
    assert all("secret-value" not in item.detail for item in feedback)
    safe = safe_feedback_payload(
        (
            ValidationFeedback(
                code="dangling_reference",
                stage="S3",
                path="/claims/0/source_ids",
                retryable=True,
                detail="do not forward this raw secret",
            ),
        )
    )
    assert safe[0]["detail"] == "validator rejected the previous structured output"


def test_json_normalisation_rejects_non_json_values() -> None:
    assert normalise_json_object({"value": ["ok", 1]}) == {"value": ["ok", 1]}
    with pytest.raises(Exception, match="structured input"):
        normalise_json_object({"value": float("nan")})
    with pytest.raises(Exception, match="structured input"):
        normalise_json_object({"value": object()})  # type: ignore[dict-item]


def test_schema_loader_rejects_untrusted_or_invalid_references(tmp_path: Path) -> None:
    _write_minimal_repository(
        tmp_path,
        registry_task={
            "task_name": "test",
            "prompt_file": "test.md",
            "prompt_version": "0.1.0",
            "stage": "S1",
            "output_schema": "../../outside.json",
        },
    )
    with pytest.raises(PromptCatalogError):
        PromptCatalog(tmp_path).resolve("test")

    loader = SchemaLoader(REPOSITORY_ROOT)
    with pytest.raises(PromptCatalogError):
        loader.bundle("https://unknown.invalid/schema.json", relative_to=REPOSITORY_ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        "invalid_registry_json",
        "tasks_not_array",
        "task_not_object",
        "duplicate_task",
        "missing_task_name",
        "missing_prompt",
        "unsafe_prompt_path",
        "empty_prompt",
        "invalid_frontmatter",
        "invalid_frontmatter_line",
        "unterminated_frontmatter",
        "frontmatter_mismatch",
        "bad_input_schema_type",
        "bad_batching_type",
        "duplicate_schema_id",
    ],
)
def test_catalog_rejects_malformed_repository_contracts(tmp_path: Path, mutation: str) -> None:
    task: dict[str, object] = {
        "task_name": "test",
        "prompt_file": "test.md",
        "prompt_version": "0.1.0",
        "stage": "S1",
        "output_schema": "schemas/output.schema.json",
    }
    _write_minimal_repository(tmp_path, registry_task=task)
    registry_path = tmp_path / "packages/prompts/registry.json"
    prompt_path = tmp_path / "packages/prompts/test.md"

    if mutation == "invalid_registry_json":
        registry_path.write_text("{", encoding="utf-8")
    elif mutation == "tasks_not_array":
        registry_path.write_text('{"tasks": {}}', encoding="utf-8")
    elif mutation == "task_not_object":
        registry_path.write_text('{"tasks": ["bad"]}', encoding="utf-8")
    elif mutation == "duplicate_task":
        registry_path.write_text(json.dumps({"tasks": [task, task]}), encoding="utf-8")
    elif mutation == "missing_task_name":
        changed = {key: value for key, value in task.items() if key != "task_name"}
        registry_path.write_text(json.dumps({"tasks": [changed]}), encoding="utf-8")
    elif mutation == "missing_prompt":
        prompt_path.unlink()
    elif mutation == "unsafe_prompt_path":
        task["prompt_file"] = "../outside.md"
        registry_path.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    elif mutation == "empty_prompt":
        prompt_path.write_text("", encoding="utf-8")
    elif mutation == "invalid_frontmatter":
        prompt_path.write_text("no frontmatter", encoding="utf-8")
    elif mutation == "invalid_frontmatter_line":
        prompt_path.write_text("---\nbad-line\n---\n", encoding="utf-8")
    elif mutation == "unterminated_frontmatter":
        prompt_path.write_text("---\nversion: 0.1.0\nstage: S1\n", encoding="utf-8")
    elif mutation == "frontmatter_mismatch":
        prompt_path.write_text("---\nversion: 9.9.9\nstage: S1\n---\n", encoding="utf-8")
    elif mutation == "bad_input_schema_type":
        task["input_schema"] = 1
        registry_path.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    elif mutation == "bad_batching_type":
        task["batching"] = "bad"
        registry_path.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    elif mutation == "duplicate_schema_id":
        second = tmp_path / "packages/research-schema/duplicate.schema.json"
        second.write_text(
            json.dumps(
                {
                    "$id": "https://example.invalid/output.schema.json",
                    "type": "object",
                }
            ),
            encoding="utf-8",
        )

    with pytest.raises(PromptCatalogError):
        PromptCatalog(tmp_path).resolve("test")


def test_schema_loader_handles_pointers_siblings_and_cycles(tmp_path: Path) -> None:
    _write_minimal_repository(
        tmp_path,
        registry_task={
            "task_name": "test",
            "prompt_file": "test.md",
            "prompt_version": "0.1.0",
            "stage": "S1",
            "output_schema": "schemas/output.schema.json",
        },
    )
    schema_path = tmp_path / "packages/prompts/schemas/output.schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "answer": {
                        "$ref": "#/$defs/text",
                        "description": "sibling keyword",
                    },
                    "a/b": {"type": "string"},
                    "disabled": False,
                },
                "$defs": {"text": {"type": "string"}},
                "examples": [{"answer": "ok"}],
            }
        ),
        encoding="utf-8",
    )
    loader = SchemaLoader(tmp_path)

    bundled = loader.bundle(
        "schemas/output.schema.json",
        relative_to=tmp_path / "packages/prompts",
    )
    answer = bundled["properties"]
    assert isinstance(answer, dict)
    assert "$ref" not in canonical_json(bundled)
    assert loader.bundle(
        "schemas/output.schema.json#/properties/a~1b",
        relative_to=tmp_path / "packages/prompts",
    ) == {"type": "string"}
    assert loader.bundle(
        "schemas/output.schema.json#/examples/0",
        relative_to=tmp_path / "packages/prompts",
    ) == {"answer": "ok"}
    with pytest.raises(PromptCatalogError):
        loader.bundle(
            "schemas/output.schema.json#/properties/disabled",
            relative_to=tmp_path / "packages/prompts",
        )
    with pytest.raises(PromptCatalogError):
        loader.bundle(
            "schemas/output.schema.json#not-a-pointer",
            relative_to=tmp_path / "packages/prompts",
        )
    with pytest.raises(PromptCatalogError):
        loader.bundle(
            "schemas/output.schema.json#/missing",
            relative_to=tmp_path / "packages/prompts",
        )
    with pytest.raises(PromptCatalogError):
        loader.bundle(
            "../../../../outside.schema.json",
            relative_to=tmp_path / "packages/prompts",
        )

    schema_path.write_text(json.dumps({"$ref": "#"}), encoding="utf-8")
    cycle_loader = SchemaLoader(tmp_path)
    with pytest.raises(PromptCatalogError):
        cycle_loader.bundle(
            "schemas/output.schema.json",
            relative_to=tmp_path / "packages/prompts",
        )


@pytest.mark.parametrize(
    "schema_content",
    [
        "{",
        "[]",
        '{"type": 7}',
    ],
)
def test_schema_loader_rejects_invalid_schema_documents(
    tmp_path: Path,
    schema_content: str,
) -> None:
    _write_minimal_repository(
        tmp_path,
        registry_task={
            "task_name": "test",
            "prompt_file": "test.md",
            "prompt_version": "0.1.0",
            "stage": "S1",
            "output_schema": "schemas/output.schema.json",
        },
    )
    (tmp_path / "packages/prompts/schemas/output.schema.json").write_text(
        schema_content,
        encoding="utf-8",
    )
    with pytest.raises(PromptCatalogError):
        PromptCatalog(tmp_path).resolve("test")


def test_schema_loader_rejects_missing_document_and_bad_pointer_index(tmp_path: Path) -> None:
    _write_minimal_repository(
        tmp_path,
        registry_task={
            "task_name": "test",
            "prompt_file": "test.md",
            "prompt_version": "0.1.0",
            "stage": "S1",
            "output_schema": "schemas/output.schema.json",
        },
    )
    loader = SchemaLoader(tmp_path)
    with pytest.raises(PromptCatalogError):
        loader.bundle(
            "schemas/missing.schema.json",
            relative_to=tmp_path / "packages/prompts",
        )
    with pytest.raises(PromptCatalogError):
        loader.bundle(
            "schemas/output.schema.json#/required/99",
            relative_to=tmp_path / "packages/prompts",
        )


def _write_minimal_repository(
    root: Path,
    *,
    registry_task: dict[str, object],
) -> None:
    prompt_root = root / "packages/prompts"
    schema_root = prompt_root / "schemas"
    research_root = root / "packages/research-schema"
    schema_root.mkdir(parents=True)
    research_root.mkdir(parents=True)
    (prompt_root / "registry.json").write_text(
        json.dumps({"tasks": [registry_task]}),
        encoding="utf-8",
    )
    (prompt_root / "test.md").write_text(
        "---\nprompt_id: test\nversion: 0.1.0\nstage: S1\n---\n# Test",
        encoding="utf-8",
    )
    (schema_root / "output.schema.json").write_text(
        json.dumps(
            {
                "$id": "https://example.invalid/output.schema.json",
                "type": "object",
                "additionalProperties": False,
                "required": ["answer"],
                "properties": {"answer": {"type": "string"}},
            }
        ),
        encoding="utf-8",
    )
