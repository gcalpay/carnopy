from __future__ import annotations

from functools import cached_property

import CoolProp
import CoolProp.CoolProp as CP

from carnopy.domain.failures import BackendInitializationError, BackendResult


class CoolPropBackend:
    @property
    def name(self) -> str:
        return "coolprop"

    @property
    def version(self) -> str:
        return str(CoolProp.__version__)

    @cached_property
    def _aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for canonical in self.list_fluids():
            raw_aliases = CP.get_fluid_param_string(canonical, "aliases")
            names = [canonical, *raw_aliases.split(",")]
            for name in names:
                cleaned = name.strip()
                if cleaned:
                    aliases[cleaned.casefold()] = canonical
        return aliases

    def list_fluids(self) -> list[str]:
        return sorted(str(fluid) for fluid in CP.FluidsList())

    def aliases_for(self, canonical_fluid: str) -> list[str]:
        raw = CP.get_fluid_param_string(canonical_fluid, "aliases")
        aliases = {canonical_fluid}
        aliases.update(name.strip() for name in raw.split(",") if name.strip())
        return sorted(aliases)

    def canonicalize_fluid(self, fluid: str) -> str:
        if any(token in fluid for token in ("::", "&", "[", "]")):
            raise ValueError(
                f"mixtures and backend-prefixed fluid strings are unsupported: {fluid!r}"
            )
        try:
            return self._aliases[fluid.strip().casefold()]
        except KeyError as exc:
            raise ValueError(f"unsupported CoolProp pure fluid {fluid!r}") from exc

    def initialize_reference_states(self, fluids: list[str]) -> None:
        for fluid in fluids:
            try:
                CP.set_reference_state(fluid, "DEF")
            except Exception as exc:
                raise BackendInitializationError(
                    f"failed to set CoolProp DEF reference state for {fluid}: {exc}"
                ) from exc

    def phase(
        self,
        fluid: str,
        input1: str,
        value1: float,
        input2: str,
        value2: float,
    ) -> BackendResult[str]:
        try:
            value = str(CP.PhaseSI(input1, value1, input2, value2, fluid))
        except Exception as exc:
            return BackendResult.failure(
                layer="backend",
                code="backend_phase_call_failed",
                message="CoolProp phase evaluation failed",
                error=exc,
            )
        return BackendResult.success(value)

    def property(
        self,
        output: str,
        fluid: str,
        input1: str,
        value1: float,
        input2: str,
        value2: float,
    ) -> BackendResult[float]:
        try:
            value = float(CP.PropsSI(output, input1, value1, input2, value2, fluid))
        except Exception as exc:
            return BackendResult.failure(
                layer="backend",
                code="backend_property_call_failed",
                message=f"CoolProp property evaluation failed for {output}",
                error=exc,
            )
        return BackendResult.success(value)

    def fluid_constant(self, output: str, fluid: str) -> BackendResult[float]:
        try:
            value = float(CP.PropsSI(output, fluid))
        except Exception as exc:
            return BackendResult.failure(
                layer="backend",
                code="backend_property_call_failed",
                message=f"CoolProp fluid constant evaluation failed for {output}",
                error=exc,
            )
        return BackendResult.success(value)
