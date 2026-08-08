from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic

from carnopy.domain.failures import CarnopyError

PhaseCallback = Callable[[str, bool], None]
ProtectedPhaseCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
CancellationCheck = Callable[[], bool]


class ExecutionCancelled(CarnopyError):
    """A cancellable operation was stopped before immutable finalization."""


@dataclass
class ExecutionControl:
    """Private progress and cancellation bridge for worker-driven execution."""

    cancellation_requested: CancellationCheck
    on_phase: PhaseCallback
    on_progress: ProgressCallback
    on_protected_phase: ProtectedPhaseCallback | None = None
    minimum_progress_interval: float = 0.1
    _cancellable: bool = field(default=True, init=False)
    _last_progress_at: float | None = field(default=None, init=False)

    def phase(self, name: str, *, cancellable: bool = True) -> None:
        self._cancellable = cancellable
        self.raise_if_cancelled()
        self.on_phase(name, cancellable)

    def protected_phase(self, name: str) -> None:
        """Cross the irreversible outer-finalization termination boundary."""
        self.raise_if_cancelled()
        self._cancellable = False
        if self.on_protected_phase is None:
            self.on_phase(name, False)
        else:
            self.on_protected_phase(name)

    def checkpoint(self, completed: int, total: int) -> None:
        self.raise_if_cancelled()
        now = monotonic()
        if (
            completed == total
            or self._last_progress_at is None
            or now - self._last_progress_at >= self.minimum_progress_interval
        ):
            self.on_progress(completed, total)
            self._last_progress_at = now

    def raise_if_cancelled(self) -> None:
        if self._cancellable and self.cancellation_requested():
            raise ExecutionCancelled("generation cancelled before immutable finalization")

    def disable_cancellation(self) -> None:
        self._cancellable = False
