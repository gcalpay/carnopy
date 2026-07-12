from __future__ import annotations

from dataclasses import dataclass, field

from carnopy.app.plot_staging import PlotStagingLease, cleanup_plot_staging


@dataclass
class ImageExportFinalizer:
    """Idempotently finish one parent-owned image-export staging lease."""

    lease: PlotStagingLease
    _finished: bool = field(default=False, init=False)
    _cleanup_error: str | None = field(default=None, init=False)

    def finish(self, successful: bool) -> str | None:
        if self._finished:
            return self._cleanup_error
        self._finished = True
        try:
            cleanup_plot_staging(self.lease, successful=successful)
        except Exception as exc:  # pragma: no cover - defensive process boundary
            self._cleanup_error = f"plot staging cleanup failed: {exc}"
        return self._cleanup_error
