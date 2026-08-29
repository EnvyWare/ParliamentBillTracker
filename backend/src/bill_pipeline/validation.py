"""A dependency-free validator for the subset of JSON Schema this project uses.

The published snapshot must be schema-validated before it replaces the last
known-good object, so validation has to run inside the Lambda. Pulling in
``jsonschema`` would drag compiled wheels into an ARM64 deployment package for
a handful of keywords, so the subset is implemented here instead.

The real ``jsonschema`` library is a development dependency and
``tests/test_snapshot.py`` cross-checks that this validator agrees with it on
every fixture. If the two ever disagree, the tests fail.

Supported keywords: ``$ref`` (local ``#/$defs`` pointers), ``type``, ``enum``,
``const``, ``required``, ``properties``, ``additionalProperties`` (boolean),
``items``, ``oneOf``, ``pattern``, ``minLength``, ``minimum``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TYPE_CHECKS: dict[str, Any] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class SchemaValidationError(ValueError):
    """The instance did not satisfy the schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        shown = "; ".join(errors[:10])
        more = f" (and {len(errors) - 10} more)" if len(errors) > 10 else ""
        super().__init__(f"Snapshot failed schema validation: {shown}{more}")


def load_schema(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


def validate(instance: Any, schema: dict[str, Any]) -> None:
    """Raise :class:`SchemaValidationError` if ``instance`` does not conform."""
    errors: list[str] = []
    _validate(instance, schema, schema, "$", errors)
    if errors:
        raise SchemaValidationError(errors)


def iter_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Collect validation errors without raising."""
    errors: list[str] = []
    _validate(instance, schema, schema, "$", errors)
    return errors


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    if not ref.startswith("#/"):
        raise ValueError(f"Only local $ref pointers are supported, got {ref!r}")
    target: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        target = target[token]
    if not isinstance(target, dict):
        raise ValueError(f"$ref {ref!r} did not resolve to a schema object")
    # A sibling keyword alongside $ref (such as description) is ignored, which
    # matches the 2020-12 behaviour this project relies on.
    return _resolve(target, root)


def _validate(
    instance: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    schema = _resolve(schema, root)

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
        return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")
        return

    if "type" in schema and not _matches_type(instance, schema["type"]):
        errors.append(f"{path}: expected type {schema['type']!r}, got {_kind(instance)}")
        return

    if "oneOf" in schema:
        matches = sum(
            1 for option in schema["oneOf"] if not _sub_errors(instance, option, root, path)
        )
        if matches != 1:
            errors.append(f"{path}: matched {matches} of the oneOf branches, expected exactly 1")
            return

    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, instance) is None:
            errors.append(f"{path}: {instance!r} does not match pattern {pattern!r}")
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            errors.append(f"{path}: string shorter than minLength {min_length}")

    if isinstance(instance, int | float) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, int | float) and instance < minimum:
            errors.append(f"{path}: {instance} is below minimum {minimum}")

    if isinstance(instance, dict):
        _validate_object(instance, schema, root, path, errors)

    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            _validate(item, schema["items"], root, f"{path}[{index}]", errors)


def _validate_object(
    instance: dict[str, Any],
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    for key in schema.get("required", []):
        if key not in instance:
            errors.append(f"{path}: missing required property {key!r}")

    properties = schema.get("properties", {})
    for key, value in instance.items():
        if key in properties:
            _validate(value, properties[key], root, f"{path}.{key}", errors)
        elif schema.get("additionalProperties") is False:
            errors.append(f"{path}: unexpected property {key!r}")


def _sub_errors(
    instance: Any, schema: dict[str, Any], root: dict[str, Any], path: str
) -> list[str]:
    collected: list[str] = []
    _validate(instance, schema, root, path, collected)
    return collected


def _matches_type(instance: Any, expected: Any) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    return any(_TYPE_CHECKS[name](instance) for name in names if name in _TYPE_CHECKS)


def _kind(instance: Any) -> str:
    if instance is None:
        return "null"
    if isinstance(instance, bool):
        return "boolean"
    return type(instance).__name__
