from __future__ import annotations

from functools import cached_property

import CoolProp
import CoolProp.CoolProp as CP

from carnopy.backends import coolprop_models
from carnopy.config.models import CoolPropModel
from carnopy.domain.failures import BackendInitializationError, BackendResult


class CoolPropBackend:
    def __init__(self, model: CoolPropModel = "heos") -> None:
        if model not in coolprop_models.MODEL_PREFIXES:
            raise ValueError(f"unsupported CoolProp model {model!r}")
        self._model = model

    @property
    def name(self) -> str:
        return "coolprop"

    @property
    def model(self) -> CoolPropModel:
        return self._model

    @property
    def version(self) -> str:
        return str(CoolProp.__version__)

    @property
    def model_prefix(self) -> str:
        return coolprop_models.MODEL_PREFIXES[self.model]

    @property
    def supported_properties(self) -> tuple[str, ...]:
        return coolprop_models.supported_properties(self.model)

    @property
    def unsupported_model_properties(self) -> tuple[str, ...]:
        return coolprop_models.unsupported_properties(self.model)

    @cached_property
    def _aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for canonical in self._all_fluids():
            raw_aliases = CP.get_fluid_param_string(canonical, "aliases")
            names = [canonical, *raw_aliases.split(",")]
            for name in names:
                cleaned = name.strip()
                if cleaned:
                    aliases[cleaned.casefold()] = canonical
        return aliases

    def list_fluids(self) -> list[str]:
        fluids: list[str] = []
        for fluid in self._all_fluids():
            try:
                CP.AbstractState(self.model_prefix, fluid)
            except Exception:
                continue
            fluids.append(fluid)
        return fluids

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
            canonical = self._aliases[fluid.strip().casefold()]
        except KeyError as exc:
            raise ValueError(f"unsupported CoolProp pure fluid {fluid!r}") from exc
        try:
            CP.AbstractState(self.model_prefix, canonical)
        except Exception as exc:
            raise ValueError(
                f"CoolProp model {self.model} does not support pure fluid {canonical!r}: {exc}"
            ) from exc
        return canonical

    def unsupported_properties(self, properties: list[str]) -> list[str]:
        return list(coolprop_models.unsupported_properties(self.model, properties))

    def reference_state_target(self, fluid: str) -> str:
        return self._qualified_fluid(fluid)

    def initialize_reference_states(self, fluids: list[str]) -> None:
        for fluid in fluids:
            target = self.reference_state_target(fluid)
            try:
                CP.set_reference_state(target, "DEF")
            except Exception as exc:
                raise BackendInitializationError(
                    f"failed to set CoolProp DEF reference state for {target}: {exc}"
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
            value = str(CP.PhaseSI(input1, value1, input2, value2, self._qualified_fluid(fluid)))
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
            value = float(
                CP.PropsSI(
                    output,
                    input1,
                    value1,
                    input2,
                    value2,
                    self._qualified_fluid(fluid),
                )
            )
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
            value = float(CP.PropsSI(output, self._qualified_fluid(fluid)))
        except Exception as exc:
            return BackendResult.failure(
                layer="backend",
                code="backend_property_call_failed",
                message=f"CoolProp fluid constant evaluation failed for {output}",
                error=exc,
            )
        return BackendResult.success(value)

    def _qualified_fluid(self, fluid: str) -> str:
        return f"{self.model_prefix}::{fluid}"

    @staticmethod
    def _all_fluids() -> list[str]:
        return sorted(str(fluid) for fluid in CP.FluidsList())
