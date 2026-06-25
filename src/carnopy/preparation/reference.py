from __future__ import annotations

from typing import Any

from carnopy.domain.failures import ConfigError
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.preparation.fields import ResolvedField, ResolvedPreparation
from carnopy.preparation.source import LoadedPreparationSource, SourceTable


def build_reference_state_summary(
    source_data: LoadedPreparationSource,
    resolved: ResolvedPreparation,
) -> dict[str, Any]:
    selected = _selected_reference_dependent_fields(resolved)
    contexts = [_context_for_table(table) for table in source_data.tables]
    summary: dict[str, Any] = {
        "selected_reference_dependent_fields": selected,
        "requires_context_compatibility": bool(selected),
        "contexts": contexts,
        "compatible": True,
    }
    if not selected:
        return summary

    missing = [
        context["artifact"]
        for context in contexts
        if context["reference_state_policy"] is None
        or context["backend"] is None
        or context["backend_model"] is None
    ]
    if missing:
        raise ConfigError(
            "reference-dependent preparation fields require source reference-state "
            "metadata; missing context for: " + ", ".join(missing)
        )
    compatibility_keys = {
        (
            context["reference_state_policy"],
            context["backend"],
            context["backend_model"],
        )
        for context in contexts
    }
    if len(compatibility_keys) != 1:
        raise ConfigError(
            "reference-dependent preparation fields require one compatible "
            "reference-state context across selected source rows "
            "(reference_state_policy, backend, backend_model); found: "
            + ", ".join(" / ".join(str(part) for part in key) for key in sorted(compatibility_keys))
        )
    policy, backend, backend_model = next(iter(compatibility_keys))
    summary["compatible_context"] = {
        "reference_state_policy": policy,
        "backend": backend,
        "backend_model": backend_model,
    }
    return summary


def _selected_reference_dependent_fields(resolved: ResolvedPreparation) -> list[str]:
    fields: list[str] = []
    for field in (*resolved.numeric_features, *resolved.targets, *resolved.auxiliary):
        if _is_reference_dependent(field):
            fields.append(field.semantic_name)
    return sorted(set(fields))


def _is_reference_dependent(field: ResolvedField) -> bool:
    definition = PROPERTY_REGISTRY.get(field.semantic_name)
    return bool(definition is not None and definition.reference_dependent)


def _context_for_table(table: SourceTable) -> dict[str, Any]:
    return {
        "artifact": table.artifact_relative_path,
        "run_id": table.run_id,
        "backend": _text(table.metadata.get("backend")),
        "backend_model": _text(table.metadata.get("backend_model")) or table.backend_model,
        "reference_state_policy": _text(table.metadata.get("reference_state_policy")),
        "reference_state_backend_model": _text(table.metadata.get("reference_state_backend_model")),
        "reference_state_targets": _string_list(table.metadata.get("reference_state_targets")),
    }


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]
