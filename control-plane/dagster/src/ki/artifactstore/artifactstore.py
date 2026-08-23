from ki.core.datapipeline.datapipeline_dataclasses import GlobalRunContext
from ki.artifactstore.dataclasses import ArtifactRef, ArtifactMetadata
from ki.core.base.registry import Registry

import logging  
from pathlib import Path
from typing import Any, Type

import json
import uuid
import hashlib
from datetime import datetime, timezone

class PathResolver:
    def resolve(
        self,
        *,
        run_ctx: GlobalRunContext,
        component: str,
        artifact_id: str,
        extension: str
    ) -> tuple[Path, Path]:
        artifact_dir = run_ctx.run_path / component / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"artifact{extension}"
        metadata_path = artifact_dir / "metadata.json"
        return artifact_path, metadata_path


class ArtifactStore:
    def __init__(
        self,
        *,
        serializer_registry: Registry,
        path_resolver: PathResolver,
        logger: logging.Logger,
    ):
        self.serializer_registry = serializer_registry
        self.path_resolver = path_resolver
        self.logger = logger

    def save(
        self,
        *,
        obj: Any,
        artifact_type: str,
        component: str,
        run_ctx,
        serializer_key: str = "pydantic_json",
        version: int | None = None,
        parent_object_type: str,
        attribute_name: str   
    ) -> ArtifactRef:

        artifact_id = uuid.uuid4().hex  # Option A
        serializer_cls = self.serializer_registry.get(serializer_key)
        serializer: ArtifactSerializer = serializer_cls()

        artifact_path, metadata_path = self.path_resolver.resolve(
            run_ctx=run_ctx,
            component=component,
            artifact_id=artifact_id,
            extension=serializer.file_extension,
        )

        # ---- dump artifact
        serializer.dump(obj, artifact_path)

        # ---- compute hash + size
        raw = artifact_path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        size_bytes = len(raw)

        metadata = ArtifactMetadata(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            component=component,
            run_id=run_ctx.run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            serializer=serializer_key,
            hash=f"sha256:{sha256}",
            size_bytes=size_bytes,
        )

        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata.__dict__, f, indent=2)

        uri = artifact_path.resolve().as_uri()

        self.logger.info(
            "Stored artifact %s (%s) at %s",
            artifact_id,
            artifact_type,
            uri,
        )

        return ArtifactRef(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            hash=metadata.hash,
            version=version,
            uri=uri,
            parent_object_type=parent_object_type,  
            attribute_name=attribute_name           
        )

    def load(
        self,
        *,
        ref: ArtifactRef,
        obj_type: Type,
    ) -> Any:

        artifact_path = Path(ref.uri.replace("file://", ""))
        metadata_path = artifact_path.parent / "metadata.json"

        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")

        with metadata_path.open("r", encoding="utf-8") as f:
            metadata_dict = json.load(f)

        serializer_key = metadata_dict["serializer"]
        serializer_cls = self.serializer_registry.get(serializer_key)
        serializer: ArtifactSerializer = serializer_cls()

        obj = serializer.load(artifact_path, obj_type)

        # optional integrity check
        raw = artifact_path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        if f"sha256:{sha256}" != ref.hash:
            raise ValueError("Artifact hash mismatch")

        return obj


