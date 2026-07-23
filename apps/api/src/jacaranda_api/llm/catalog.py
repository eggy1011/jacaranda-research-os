from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from jacaranda_api.llm.errors import PromptCatalogError, UnknownTaskError
from jacaranda_api.llm.models import JsonObject
from jacaranda_api.llm.schema_loader import SchemaLoader


@dataclass(frozen=True, slots=True)
class PromptTask:
    task_name: str
    prompt_version: str
    stage: str
    prompt_text: str
    output_schema_reference: str
    output_schema: JsonObject
    input_schema: JsonObject | None
    batching: JsonObject | None


class PromptCatalogReader(Protocol):
    def resolve(self, task_name: str) -> PromptTask: ...


class PromptCatalog:
    """Read-only adapter over Claude-owned prompt registry and schemas."""

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._prompt_root = self._repository_root / "packages/prompts"
        self._schema_loader = SchemaLoader(self._repository_root)
        self._tasks = self._load_registry()

    def resolve(self, task_name: str) -> PromptTask:
        raw_task = self._tasks.get(task_name)
        if raw_task is None:
            raise UnknownTaskError()
        prompt_file = self._safe_prompt_path(self._require_string(raw_task, "prompt_file"))
        prompt_text = self._read_prompt(prompt_file)
        prompt_version = self._require_string(raw_task, "prompt_version")
        stage = self._require_string(raw_task, "stage")
        metadata = self._frontmatter(prompt_text)
        if metadata.get("version") != prompt_version or metadata.get("stage") != stage:
            raise PromptCatalogError()

        output_reference = self._require_string(raw_task, "output_schema")
        output_schema = self._schema_loader.bundle(
            output_reference,
            relative_to=self._prompt_root,
        )
        input_reference = raw_task.get("input_schema")
        input_schema = None
        if input_reference is not None:
            if not isinstance(input_reference, str):
                raise PromptCatalogError()
            input_schema = self._schema_loader.bundle(
                input_reference,
                relative_to=self._prompt_root,
            )
        batching = raw_task.get("batching")
        if batching is not None and not isinstance(batching, dict):
            raise PromptCatalogError()
        return PromptTask(
            task_name=task_name,
            prompt_version=prompt_version,
            stage=stage,
            prompt_text=prompt_text,
            output_schema_reference=output_reference,
            output_schema=output_schema,
            input_schema=input_schema,
            batching=batching,
        )

    def all_tasks(self) -> tuple[PromptTask, ...]:
        """Return executable tasks in registry order for deterministic schedulers."""
        return tuple(self.resolve(task_name) for task_name in self._tasks)

    def _load_registry(self) -> dict[str, JsonObject]:
        registry_path = self._prompt_root / "registry.json"
        try:
            value = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise PromptCatalogError() from None
        if not isinstance(value, dict) or not isinstance(value.get("tasks"), list):
            raise PromptCatalogError()
        tasks: dict[str, JsonObject] = {}
        for item in value["tasks"]:
            if not isinstance(item, dict):
                raise PromptCatalogError()
            task = cast(JsonObject, item)
            task_name = self._require_string(task, "task_name")
            if task_name in tasks:
                raise PromptCatalogError()
            tasks[task_name] = task
        return tasks

    def _safe_prompt_path(self, relative_path: str) -> Path:
        path = (self._prompt_root / relative_path).resolve()
        if not path.is_relative_to(self._prompt_root) or path.suffix != ".md":
            raise PromptCatalogError()
        return path

    def _read_prompt(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise PromptCatalogError() from None
        if not text.strip():
            raise PromptCatalogError()
        return text

    def _frontmatter(self, prompt_text: str) -> dict[str, str]:
        lines = prompt_text.splitlines()
        if not lines or lines[0] != "---":
            raise PromptCatalogError()
        metadata: dict[str, str] = {}
        for line in lines[1:]:
            if line == "---":
                return metadata
            key, separator, value = line.partition(":")
            if not separator or not key.strip() or not value.strip():
                raise PromptCatalogError()
            metadata[key.strip()] = value.strip()
        raise PromptCatalogError()

    def _require_string(self, value: JsonObject, key: str) -> str:
        item = value.get(key)
        if not isinstance(item, str) or not item:
            raise PromptCatalogError()
        return item
