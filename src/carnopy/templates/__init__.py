from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from importlib.resources import files
from pathlib import Path
from typing import Final, Literal

ConfigTemplateMode = Literal[
    "property_table",
    "saturation_table",
    "vapor_mass_fraction_table",
]

TEMPLATE_FILENAMES: Final[dict[ConfigTemplateMode, str]] = {
    "property_table": "property_table.yaml",
    "saturation_table": "saturation_table.yaml",
    "vapor_mass_fraction_table": "vapor_mass_fraction_table.yaml",
}


class TemplateError(Exception):
    """A starter configuration cannot be created safely."""


def template_text(mode: ConfigTemplateMode) -> str:
    """Return the packaged starter configuration for one dataset mode."""
    resource = files(__package__).joinpath(TEMPLATE_FILENAMES[mode])
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateError(f"could not read packaged template for {mode}: {exc}") from exc


def initialize_config(
    mode: ConfigTemplateMode,
    output: str | Path,
    *,
    create_parents: bool = False,
    interactive: bool = False,
    confirm_create: Callable[[Path], bool] | None = None,
) -> Path:
    """Create one configuration from a packaged template without overwriting."""
    output_path = Path(output).expanduser()
    if output_path.suffix.lower() not in {".yaml", ".yml"}:
        raise TemplateError("configuration output must end in .yaml or .yml")

    parent = output_path.parent
    if not parent.exists():
        should_create = create_parents
        if not should_create and interactive and confirm_create is not None:
            should_create = confirm_create(parent)
        if not should_create:
            raise TemplateError(
                f"parent directory does not exist: {parent}. "
                "Pass --create-parents for noninteractive use."
            )
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TemplateError(f"could not create parent directory {parent}: {exc}") from exc
    elif not parent.is_dir():
        raise TemplateError(f"configuration parent is not a directory: {parent}")

    if output_path.exists():
        raise TemplateError(f"refusing to overwrite existing file: {output_path}")

    created = False
    try:
        with output_path.open("x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write(template_text(mode))
    except FileExistsError as exc:
        raise TemplateError(f"refusing to overwrite existing file: {output_path}") from exc
    except OSError as exc:
        if created:
            with suppress(OSError):
                output_path.unlink(missing_ok=True)
        raise TemplateError(f"could not create configuration {output_path}: {exc}") from exc
    return output_path.resolve()
