from __future__ import annotations

from typing import Protocol

from carnopy.domain.failures import BackendResult


class PropertyBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def version(self) -> str: ...

    def list_fluids(self) -> list[str]: ...

    def aliases_for(self, canonical_fluid: str) -> list[str]: ...

    def canonicalize_fluid(self, fluid: str) -> str: ...

    def unsupported_properties(self, properties: list[str]) -> list[str]: ...

    def reference_state_target(self, fluid: str) -> str: ...

    def initialize_reference_states(self, fluids: list[str]) -> None: ...

    def phase(
        self,
        fluid: str,
        input1: str,
        value1: float,
        input2: str,
        value2: float,
    ) -> BackendResult[str]: ...

    def property(
        self,
        output: str,
        fluid: str,
        input1: str,
        value1: float,
        input2: str,
        value2: float,
    ) -> BackendResult[float]: ...

    def fluid_constant(self, output: str, fluid: str) -> BackendResult[float]: ...
