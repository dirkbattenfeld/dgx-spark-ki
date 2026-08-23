# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
from dataclasses import dataclass


# %%
@dataclass
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    hash: str
    version: int | None
    uri: str
    parent_object_type: str
    attribute_name: str    

@dataclass(frozen=True)
class ArtifactMetadata:
    artifact_id: str
    artifact_type: str
    component: str
    run_id: int
    created_at: str
    serializer: str
    hash: str
    size_bytes: int
