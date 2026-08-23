# ki/core/datapipeline/artifactpolicy.py

import logging
from pydantic import BaseModel

import numpy as np
import pandas as pd

from ki.core.datapipeline.datapipeline_dataclasses import Base64Image


class ArtifactPersistencePolicy:
    """
    Verwaltung der Persistenz von Component Outputs.

    - Primitive Attribute (int, float, str, bool) und kleine dicts → inline
    - Technisch persistierbare Attribute → ArtifactRefs erzeugen
    - Attribut-basierte Typprüfung über _infer_serializer_keys
    """

    def __init__(self, global_ctx, logger: logging.Logger, max_inline_dict_size=10, allow_inferred_serializer=True):
        self.global_ctx = global_ctx
        self.logger = logger
        self.max_inline_dict_size = max_inline_dict_size
        self.allow_inferred_serializer = allow_inferred_serializer
        self.serializer_registry = global_ctx.serializer_registry
        self.artifact_store = global_ctx.artifact_store

    def _infer_serializer_keys(self, obj) -> tuple[dict, dict]:
        """
        Iteriert über Attribute von obj und ermittelt für jedes Attribute:
        - Dict1: attrib_name -> serializer_key (bekannter Typ)
        - Dict2: attrib_name -> attrib_type (kein Serializer bekannt)
        """
        attrib_dict = {}  # attrib_name -> serializer_key
        unknown_dict = {} # attrib_name -> type

        # Falls es ein Pydantic Model ist, nutzen wir dessen Feld-Definitionen
        if isinstance(obj, BaseModel):
            # Wir iterieren über die Namen der definierten Felder
            iterable = obj.model_fields.keys()
        else:
            # Fallback für normale Klassen
            iterable = vars(obj).keys()

        for attr_name in iterable:
            attr_value = getattr(obj, attr_name)

            # --- Primitive Typen oder kleine dicts inline behandeln ---
            if isinstance(attr_value, (int, float, str, bool)):
                continue
            if isinstance(attr_value, dict) and len(attr_value) <= self.max_inline_dict_size:
                continue
            
            # --- Typ-basierte Erkennung mit Validierung ---
            candidate = None

            if isinstance(attr_value, (pd.DataFrame, pd.Series)):
                candidate = "pandas_parquet"
            elif isinstance(attr_value, np.ndarray):
                candidate = "numpy_parquet"
            elif isinstance(attr_value, Base64Image):
                candidate = "base64_image"
            elif isinstance(attr_value, BaseModel):
                candidate = "pydantic_json"
            elif isinstance(attr_value, dict):
                candidate = "json"
            elif isinstance(attr_value, list):
                # --- Deep Check für Listen ---
                if not attr_value:
                    # Leere Liste ist unkritisch
                    candidate = "pydantic_list_json"
                else:
                    first_item = attr_value[0]
                    # Wir erlauben Pydantic-Modelle ODER einfache JSON-Basistypen
                    if isinstance(first_item, (BaseModel, str, int, float, bool, type(None))):
                        candidate = "pydantic_list_json"
            
            # --- Registry prüfen ---
            if candidate and self.serializer_registry.contains(candidate):
                self.logger.debug(
                    f"Serializer '{candidate}' für Attribut '{attr_name}' ({type(attr_value).__name__}) ausgewählt."
                )
                attrib_dict[attr_name] = candidate
            else:
                unknown_dict[attr_name] = type(attr_value).__name__

        return attrib_dict, unknown_dict

    def persist(self, value, component_name: str, global_ctx) -> list:
        """
        Persistiert die Attribute eines Datenobjekts.
        Liefert eine Liste von ArtifactRefs zurück (auch für Ganzobjekt).
        """
        artifact_refs = []

        # --- Ganzobjekt-Serialisierung prüfen ---
        serializer_key = getattr(getattr(value, "ConfigDict", None), "default_serializer", None)
        if serializer_key and self.allow_inferred_serializer:
            if self.serializer_registry.contains(serializer_key):
                self.logger.info(
                    f"Ganzobjekt {type(value).__name__} wird als Artefakt gespeichert mit Serializer '{serializer_key}'"
                )
                artifact_ref = self.artifact_store.save(
                    obj=value,
                    artifact_type=type(value).__name__,
                    component=component_name,
                    run_ctx=global_ctx,
                    serializer_key=serializer_key,
                    attribute_name=None,
                    parent_object_type=type(value).__name__
                )
                artifact_refs.append(artifact_ref)
                return artifact_refs  # Alle Attribute referenzieren dasselbe Artefakt

        # --- Attribut-basierte Persistenz ---
        attrib_dict, unknown_dict = self._infer_serializer_keys(value)

        # Warnung, falls unbekannte Typen existieren
        if unknown_dict:
            unknown_str = ", ".join(f"{n} ({t})" for n, t in unknown_dict.items())
            self.logger.warning(
                f"Komponente '{component_name}': Keine Serializer für Attribute gefunden: {unknown_str}"
            )

        # Persistenz der bekannten Attribute
        for attr_name, serializer_key in attrib_dict.items():
            attr_value = getattr(value, attr_name)
            artifact_ref = self.artifact_store.save(
                obj=attr_value,
                artifact_type=f"{type(value).__name__}.{attr_name}",
                component=component_name,
                run_ctx=global_ctx,
                serializer_key=serializer_key,
                attribute_name=attr_name,
                parent_object_type=type(value).__name__
            )
            artifact_ref.parent_object_type = type(value).__name__  # Metadaten
            artifact_refs.append(artifact_ref)

        return artifact_refs
