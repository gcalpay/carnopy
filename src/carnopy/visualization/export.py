from __future__ import annotations

import errno
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from carnopy._version import __version__
from carnopy.provenance import sha256_file
from carnopy.visualization.models import (
    PlotKind,
    PlotScale,
    PlotSource,
    VisualizationError,
)

PLOT_SCHEMA_VERSION = 1
DEFAULT_RASTER_DPI = 300
ALLOWED_OUTPUT_SUFFIXES = {".png", ".pdf", ".svg"}


def export_figure(
    *,
    figure: Any,
    plot_source: PlotSource,
    output: str | Path | None,
    selected_fluids: list[str],
    property_name: str,
    property_column: str,
    property_unit: str,
    kind: PlotKind,
    scale: PlotScale,
    valid_rows_plotted: int,
    invalid_rows_excluded: int,
    matplotlib_version: str,
    settings: dict[str, Any],
) -> tuple[Path, Path]:
    image_path = _resolve_output_path(
        output=output,
        plot_source=plot_source,
        selected_fluids=selected_fluids,
        property_name=property_name,
        kind=kind,
    )
    _ensure_output_outside_source_run(image_path, plot_source)
    sidecar_path = image_path.with_suffix(".plot.json")
    try:
        image_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VisualizationError(
            f"could not create figure output directory {image_path.parent}: {exc}"
        ) from exc
    existing = next(
        (path for path in (image_path, sidecar_path) if os.path.lexists(path)),
        None,
    )
    if existing is not None:
        raise VisualizationError(f"refusing to overwrite existing plot artifact: {existing}")

    token = uuid4().hex
    staged_image = image_path.parent / (
        f".{image_path.stem}.{token}.tmp{image_path.suffix.lower()}"
    )
    staged_sidecar = image_path.parent / f".{image_path.name}.{token}.tmp.plot.json"
    linked_image = False
    linked_sidecar = False
    try:
        save_kwargs: dict[str, Any] = {}
        if image_path.suffix.lower() == ".png":
            save_kwargs["dpi"] = DEFAULT_RASTER_DPI
        save_kwargs["format"] = image_path.suffix.lower().removeprefix(".")
        figure.savefig(staged_image, **save_kwargs)
        image_sha256 = _hash_file(staged_image)
        sidecar = _build_sidecar(
            plot_source=plot_source,
            image_path=image_path,
            image_sha256=image_sha256,
            sidecar_path=sidecar_path,
            selected_fluids=selected_fluids,
            property_name=property_name,
            property_column=property_column,
            property_unit=property_unit,
            kind=kind,
            scale=scale,
            valid_rows_plotted=valid_rows_plotted,
            invalid_rows_excluded=invalid_rows_excluded,
            matplotlib_version=matplotlib_version,
            settings=settings,
        )
        with staged_sidecar.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(sidecar, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        os.link(staged_image, image_path)
        linked_image = True
        os.link(staged_sidecar, sidecar_path)
        linked_sidecar = True
    except VisualizationError:
        if linked_sidecar:
            _unlink_if_same_file(sidecar_path, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(image_path, staged_image)
        raise
    except OSError as exc:
        if linked_sidecar:
            _unlink_if_same_file(sidecar_path, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(image_path, staged_image)
        if exc.errno in {
            errno.ENOTSUP,
            errno.EOPNOTSUPP,
            errno.EPERM,
            errno.EXDEV,
        }:
            raise VisualizationError(
                "plot export requires same-filesystem hard-link support; "
                f"could not promote staged artifacts: {exc}"
            ) from exc
        raise VisualizationError(f"could not export plot artifacts: {exc}") from exc
    except Exception as exc:
        if linked_sidecar:
            _unlink_if_same_file(sidecar_path, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(image_path, staged_image)
        raise VisualizationError(f"could not export plot artifacts: {exc}") from exc
    finally:
        _unlink_staged(staged_sidecar)
        _unlink_staged(staged_image)
    return image_path, sidecar_path


def _resolve_output_path(
    *,
    output: str | Path | None,
    plot_source: PlotSource,
    selected_fluids: list[str],
    property_name: str,
    kind: PlotKind,
) -> Path:
    if output is None:
        fluid_part = _slug(selected_fluids[0]) if len(selected_fluids) == 1 else "multifluid"
        filename = f"{fluid_part}_{property_name}_{kind}_{plot_source.run_id[:8]}.png"
        path = Path.cwd() / "figures" / filename
    else:
        path = Path(output).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
    if path.suffix.lower() not in ALLOWED_OUTPUT_SUFFIXES:
        raise VisualizationError("figure output must use a .png, .pdf, or .svg extension")
    return path.resolve()


def _ensure_output_outside_source_run(
    image_path: Path,
    plot_source: PlotSource,
) -> None:
    if plot_source.metadata is None:
        return
    source_directory = plot_source.dataset_path.parent.resolve()
    if image_path.is_relative_to(source_directory):
        raise VisualizationError(
            "figures cannot be written inside an immutable source run directory"
        )


def _build_sidecar(
    *,
    plot_source: PlotSource,
    image_path: Path,
    image_sha256: str,
    sidecar_path: Path,
    selected_fluids: list[str],
    property_name: str,
    property_column: str,
    property_unit: str,
    kind: PlotKind,
    scale: PlotScale,
    valid_rows_plotted: int,
    invalid_rows_excluded: int,
    matplotlib_version: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    return {
        "plot_schema_version": PLOT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "carnopy_version": __version__,
        "matplotlib_version": matplotlib_version,
        "source": {
            "requested_path": str(plot_source.requested_path),
            "dataset_path": str(plot_source.dataset_path),
            "format": plot_source.source_format,
            "sha256": plot_source.source_sha256,
            "integrity": plot_source.source_integrity,
            "metadata_path": (
                str(plot_source.metadata_path) if plot_source.metadata_path is not None else None
            ),
            "run_id": plot_source.run_id,
            "spec_id": plot_source.spec_id,
            "generation_context_id": plot_source.generation_context_id,
            "mode": plot_source.mode,
            "backend": _single_or_joined(plot_source.frame["backend"]),
            "backend_version": _single_or_joined(plot_source.frame["backend_version"]),
            "reference_state_policy": _metadata_text(plot_source, "reference_state_policy"),
        },
        "selection": {
            "fluids": selected_fluids,
            "property": property_name,
            "property_column": property_column,
            "property_unit": property_unit,
            "kind": kind,
            "scale": scale,
            "coordinate": plot_source.coordinate,
            "coordinate_display_unit": plot_source.coordinate_display_unit,
            "valid_rows_plotted": valid_rows_plotted,
            "invalid_rows_excluded": invalid_rows_excluded,
        },
        "settings": {
            **settings,
            "raster_dpi": (DEFAULT_RASTER_DPI if image_path.suffix.lower() == ".png" else None),
        },
        "image": {
            "path": str(image_path),
            "sidecar_path": str(sidecar_path),
            "sha256": image_sha256,
            "format": image_path.suffix.lower().removeprefix("."),
        },
    }


def _hash_file(path: Path) -> str:
    try:
        return sha256_file(path)
    except OSError as exc:
        raise VisualizationError(f"could not hash exported figure {path}: {exc}") from exc


def _unlink_if_same_file(final_path: Path, staged_path: Path) -> None:
    try:
        final_stat = os.stat(final_path, follow_symlinks=False)
        staged_stat = os.stat(staged_path, follow_symlinks=False)
    except OSError:
        return
    if (final_stat.st_dev, final_stat.st_ino) != (staged_stat.st_dev, staged_stat.st_ino):
        return
    try:
        final_path.unlink()
    except OSError:
        return


def _unlink_staged(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return cleaned or "fluid"


def _single_or_joined(series: Any) -> str:
    values = sorted(series.dropna().astype(str).unique().tolist())
    return ", ".join(values) if values else "unreported"


def _metadata_text(plot_source: PlotSource, key: str) -> str | None:
    if plot_source.metadata is None:
        return None
    value = plot_source.metadata.get(key)
    return value if isinstance(value, str) else None
