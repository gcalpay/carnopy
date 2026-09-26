from __future__ import annotations

from carnopy.domain.failures import ConfigError


class SourceImportError(ConfigError):
    """A source cannot be interpreted safely, without publishing an artifact."""

    def __init__(self, code: str, message: str, *, locator: str = "") -> None:
        self.code = code
        self.locator = locator
        super().__init__(f"{code}: {message}" + (f" ({locator})" if locator else ""))
