from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urldefrag, urlparse

from jsonschema import Draft202012Validator

from jacaranda_api.llm.errors import InputSchemaMismatchError, PromptCatalogError
from jacaranda_api.llm.models import JsonObject, JsonValue, ValidationFeedback

MAX_VALIDATION_FEEDBACK = 8


class SchemaLoader:
    """Load and fully dereference trusted repository JSON Schemas."""

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._documents: dict[Path, JsonObject] = {}
        self._ids: dict[str, Path] = {}
        for schema_root in (
            self._repository_root / "packages/prompts/schemas",
            self._repository_root / "packages/research-schema",
        ):
            for path in sorted(schema_root.glob("*.schema.json")):
                self._load_document(path)

    def bundle(self, reference: str, *, relative_to: Path) -> JsonObject:
        document_path, fragment = self._resolve_reference(
            reference,
            current_path=(relative_to / "_").resolve(),
        )
        root = self._load_document(document_path)
        target = self._resolve_pointer(root, fragment)
        bundled = self._dereference(
            target,
            current_path=document_path,
            current_root=root,
            stack=frozenset(),
        )
        if not isinstance(bundled, dict):
            raise PromptCatalogError()
        try:
            Draft202012Validator.check_schema(bundled)
        except Exception:
            raise PromptCatalogError() from None
        return bundled

    def _load_document(self, path: Path) -> JsonObject:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._repository_root) or not resolved.is_file():
            raise PromptCatalogError()
        cached = self._documents.get(resolved)
        if cached is not None:
            return cached
        try:
            value = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise PromptCatalogError() from None
        if not isinstance(value, dict):
            raise PromptCatalogError()
        document = cast(JsonObject, value)
        self._documents[resolved] = document
        identifier = document.get("$id")
        if isinstance(identifier, str):
            existing = self._ids.get(identifier)
            if existing is not None and existing != resolved:
                raise PromptCatalogError()
            self._ids[identifier] = resolved
        return document

    def _resolve_reference(self, reference: str, *, current_path: Path) -> tuple[Path, str]:
        base, fragment = urldefrag(reference)
        if not base:
            return current_path, fragment
        parsed = urlparse(base)
        if parsed.scheme:
            target = self._ids.get(base)
            if target is None:
                raise PromptCatalogError()
            return target, fragment
        target = (current_path.parent / unquote(base)).resolve()
        if not target.is_relative_to(self._repository_root):
            raise PromptCatalogError()
        return target, fragment

    def _resolve_pointer(self, document: JsonValue, fragment: str) -> JsonValue:
        if fragment in ("", "/"):
            return document
        if not fragment.startswith("/"):
            raise PromptCatalogError()
        current = document
        for raw_part in fragment.removeprefix("/").split("/"):
            part = unquote(raw_part).replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise PromptCatalogError()
        return current

    def _dereference(
        self,
        value: JsonValue,
        *,
        current_path: Path,
        current_root: JsonObject,
        stack: frozenset[tuple[Path, str]],
    ) -> JsonValue:
        if isinstance(value, list):
            return [
                self._dereference(
                    item,
                    current_path=current_path,
                    current_root=current_root,
                    stack=stack,
                )
                for item in value
            ]
        if not isinstance(value, dict):
            return value

        reference = value.get("$ref")
        if isinstance(reference, str):
            target_path, fragment = self._resolve_reference(
                reference,
                current_path=current_path,
            )
            key = (target_path, fragment)
            if key in stack:
                raise PromptCatalogError()
            target_root = (
                current_root if target_path == current_path else self._load_document(target_path)
            )
            target = self._resolve_pointer(target_root, fragment)
            resolved = self._dereference(
                target,
                current_path=target_path,
                current_root=target_root,
                stack=stack | {key},
            )
            siblings = {
                key_name: self._dereference(
                    item,
                    current_path=current_path,
                    current_root=current_root,
                    stack=stack,
                )
                for key_name, item in value.items()
                if key_name != "$ref"
            }
            if not siblings:
                return resolved
            return {"allOf": [resolved], **siblings}

        return {
            key: self._dereference(
                item,
                current_path=current_path,
                current_root=current_root,
                stack=stack,
            )
            for key, item in value.items()
        }


def validate_schema_contract(
    supplied: Mapping[str, JsonValue],
    expected: JsonObject,
) -> JsonObject:
    normalised = normalise_json_object(supplied)
    if canonical_json(normalised) != canonical_json(expected):
        raise InputSchemaMismatchError()
    return expected


def validate_instance(
    instance: JsonValue,
    schema: JsonObject,
    *,
    stage: str,
    code: str = "schema_validation_failed",
) -> tuple[ValidationFeedback, ...]:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    feedback: list[ValidationFeedback] = []
    for error in errors[:MAX_VALIDATION_FEEDBACK]:
        pointer = "/" + "/".join(_escape_pointer(str(part)) for part in error.absolute_path)
        feedback.append(
            ValidationFeedback(
                code=code,
                stage=stage,
                path=pointer,
                retryable=True,
                detail=f"output failed {error.validator or 'schema'} validation",
            )
        )
    return tuple(feedback)


def normalise_json_object(value: Mapping[str, JsonValue]) -> JsonObject:
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise InputSchemaMismatchError() from None
    return cast(JsonObject, decoded)


def canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def safe_feedback_payload(
    feedback: Sequence[ValidationFeedback],
) -> list[JsonObject]:
    return [
        {
            "code": item.code,
            "stage": item.stage,
            "path": item.path,
            "retryable": item.retryable,
            "detail": "validator rejected the previous structured output",
        }
        for item in feedback[:MAX_VALIDATION_FEEDBACK]
    ]


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
