from __future__ import annotations

import hashlib
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from carnopy.app.protocol import EventType
from carnopy.app.scene_bundle import VerifiedSceneBundle, verify_scene_bundle
from carnopy.app.scene_contracts import (
    SceneContractError,
    SceneProfile,
    SceneRequest,
    validate_scene_request,
)
from carnopy.app.scene_integrity import SceneBundleError
from carnopy.app.scene_leases import (
    SceneLease,
    SceneLeasePayload,
    validate_scene_lease,
    verify_scene_lease,
)

PositiveInt = Annotated[StrictInt, Field(gt=0)]
SceneIdentity = Annotated[StrictStr, Field(pattern=r"^scene-[0-9a-f]{64}$")]
ContentIdentity = Annotated[StrictStr, Field(pattern=r"^scene-content-[0-9a-f]{64}$")]
Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
Emit = Callable[[EventType, dict[str, Any]], None]
Checkpoint = Callable[[], None]


class BuildScenePayload(BaseModel):
    """Strict worker input bound to one parent-created empty lease."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_path: Path
    lease: SceneLeasePayload
    profile: SceneProfile
    request: SceneRequest

    @field_validator("workspace_path")
    @classmethod
    def absolute_workspace_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("scene build workspace path must be absolute")
        return value

    @model_validator(mode="after")
    def consistent_profile_and_request(self) -> BuildScenePayload:
        if self.profile.binding != self.request.binding:
            raise ValueError("scene build request binding disagrees with its accepted profile")
        if not self.profile.build_eligible:
            raise ValueError("scene build requires an eligible accepted profile")
        return self


class SceneBuildResult(BaseModel):
    """Path-free worker evidence that a candidate was written and verified."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_build_result_schema_version: Literal[1] = 1
    lease: SceneLeasePayload
    scene_request_id: SceneIdentity
    content_id: ContentIdentity
    binary_sha256: Sha256
    manifest_size: PositiveInt
    binary_size: PositiveInt
    bundle_size: PositiveInt

    @model_validator(mode="after")
    def consistent_sizes(self) -> SceneBuildResult:
        if self.bundle_size != self.manifest_size + self.binary_size:
            raise ValueError("scene build result bundle size is inconsistent")
        return self


def execute_scene_build(
    payload: BuildScenePayload,
    *,
    emit: Emit,
    checkpoint: Checkpoint,
) -> dict[str, object]:
    """Build one candidate scene and publish it only into its empty lease."""

    lease = validate_scene_lease(payload.workspace_path, payload.lease)
    validate_scene_request(payload.request, payload.profile.fields)

    emit("phase", {"name": "scene_geometry", "cancellable": True})
    emit("progress", {"completed": 0, "total": 4})
    checkpoint()
    from carnopy.app.scene_assembly import build_scene_geometry

    assembly = build_scene_geometry(
        payload.profile,
        payload.request,
        checkpoint=checkpoint,
    )

    emit("progress", {"completed": 1, "total": 4})
    emit("phase", {"name": "scene_encoding", "cancellable": True})
    checkpoint()
    from carnopy.app.scene_writer import prepare_scene_bundle

    prepared = prepare_scene_bundle(assembly, checkpoint=checkpoint)

    emit("progress", {"completed": 2, "total": 4})
    emit("phase", {"name": "scene_source_revalidation", "cancellable": True})
    checkpoint()
    _revalidate_exact_binding(payload.request)

    emit("progress", {"completed": 3, "total": 4})
    checkpoint()
    emit(
        "phase",
        {
            "name": "scene_publication",
            "cancellable": False,
            "termination_protected": True,
        },
    )
    # No cooperative checkpoint is permitted after publication begins. The
    # manifest is written last and the generic request coordinator treats this
    # short section as termination-protected.
    from carnopy.app.scene_writer import write_prepared_scene_bundle

    written = write_prepared_scene_bundle(lease, prepared)
    verified = verify_scene_bundle(lease)
    _require_written_candidate(verified, prepared.manifest, written.bundle_size)
    _revalidate_exact_binding(payload.request)

    result = SceneBuildResult(
        lease=payload.lease,
        scene_request_id=verified.manifest.request_id,
        content_id=verified.manifest.content_id,
        binary_sha256=verified.manifest.binary.sha256,
        manifest_size=verified.manifest_size,
        binary_size=verified.binary_size,
        bundle_size=verified.manifest_size + verified.binary_size,
    )
    emit("progress", {"completed": 4, "total": 4})
    return result.model_dump(mode="json")


def adopt_scene_build(
    lease: SceneLease,
    profile: SceneProfile,
    request: SceneRequest,
    result: SceneBuildResult | dict[str, object],
) -> VerifiedSceneBundle:
    """Independently verify and accept one worker candidate without mutation."""

    try:
        parsed = (
            result
            if isinstance(result, SceneBuildResult)
            else SceneBuildResult.model_validate(result, strict=True)
        )
    except ValueError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene build result is invalid",
        ) from exc
    expected_lease = SceneLeasePayload.model_validate(lease.worker_payload(), strict=True)
    if parsed.lease != expected_lease:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene build result does not identify the parent-held lease",
        )
    if profile.binding != request.binding or not profile.build_eligible:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene adoption inputs do not contain one eligible accepted binding",
        )
    try:
        validate_scene_request(request, profile.fields)
    except SceneContractError as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene adoption request is invalid for its accepted profile",
        ) from exc

    verify_scene_lease(lease)
    verified = verify_scene_bundle(lease)
    _require_result_matches_bundle(parsed, verified)
    _require_manifest_matches_acceptance(verified, profile, request)
    return verified


def _revalidate_exact_binding(request: SceneRequest) -> None:
    from carnopy.app.source_inspection import revalidate_scene_binding

    accepted = revalidate_scene_binding(request.binding)
    if accepted != request.binding:
        raise SceneContractError(
            "scene_source_changed",
            "scene source identity changed during scene construction",
        )


def _require_written_candidate(
    verified: VerifiedSceneBundle,
    expected_manifest: object,
    expected_bundle_size: int,
) -> None:
    if (
        verified.manifest != expected_manifest
        or verified.manifest_size + verified.binary_size != expected_bundle_size
    ):
        raise SceneBundleError(
            "scene_integrity_error",
            "written scene candidate disagrees with its prepared bytes",
        )


def _require_result_matches_bundle(
    result: SceneBuildResult,
    verified: VerifiedSceneBundle,
) -> None:
    manifest = verified.manifest
    if (
        result.scene_request_id != manifest.request_id
        or result.content_id != manifest.content_id
        or result.binary_sha256 != manifest.binary.sha256
        or result.manifest_size != verified.manifest_size
        or result.binary_size != verified.binary_size
        or result.bundle_size != verified.manifest_size + verified.binary_size
    ):
        raise SceneBundleError(
            "scene_integrity_error",
            "scene build result disagrees with the independently verified bundle",
        )


def _require_manifest_matches_acceptance(
    verified: VerifiedSceneBundle,
    profile: SceneProfile,
    request: SceneRequest,
) -> None:
    manifest = verified.manifest
    payload = manifest.scientific_payload
    if (
        manifest.request_id != request.request_id
        or payload.request != request
        or payload.scene_profile_schema_version != profile.scene_profile_schema_version
        or payload.source_row_count != profile.source_row_count
        or payload.fields != profile.fields
        or payload.topology.status != profile.topology.status
        or payload.topology.context_fields != profile.topology.context_fields
        or payload.topology.reason_code != profile.topology.reason_code
        or payload.topology.reason != profile.topology.reason
        or len(payload.topology.axes) != len(profile.topology.axes)
    ):
        raise SceneBundleError(
            "scene_integrity_error",
            "verified scene bundle disagrees with its accepted profile or request",
        )
    for index, (manifest_axis, profile_axis) in enumerate(
        zip(payload.topology.axes, profile.topology.axes, strict=True)
    ):
        expected_hash = _topology_levels_sha256(profile_axis.levels)
        if (
            manifest_axis.index != index
            or manifest_axis.field_id != profile_axis.field_id
            or manifest_axis.source_column != profile_axis.source_column
            or manifest_axis.unit != profile_axis.unit
            or manifest_axis.level_count != len(profile_axis.levels)
            or manifest_axis.levels_sha256 != expected_hash
        ):
            raise SceneBundleError(
                "scene_integrity_error",
                "verified scene topology levels disagree with the accepted profile",
            )


def _topology_levels_sha256(levels: tuple[float, ...]) -> str:
    digest = hashlib.sha256()
    packer = struct.Struct("<d")
    for level in levels:
        digest.update(packer.pack(level))
    return digest.hexdigest()
