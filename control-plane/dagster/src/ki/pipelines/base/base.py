from abc import ABC, abstractmethod
from typing import Optional, Type, ClassVar, Set
from pydantic import BaseModel


# Interface für Result Klassen für Komponenten in Datenpipeline
class BaseComponentResult(BaseModel):
    # Die Whitelist der erlaubten privaten Attribute
    ALLOWED_PRIVATE_ATTRS: ClassVar[Set[str]] = {
        "_pipeline_outputs", # Liste der Attribute, die in allen Projektoren in die PipelineResults aufgenommen werden
        "_drop_outputs"      # Liste der Attribute, die nicht in die PipelineResults gelangen
    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        for attr_name in cls.__dict__:
            # Wir ignorieren Dunder-Attribute wie __module__ oder __doc__
            if attr_name.startswith("__") and attr_name.endswith("__"):
                continue
                
            # Wir prüfen nur echte private/geschützte Attribute (starten mit _)
            if attr_name.startswith("_"):
                if attr_name not in cls.ALLOWED_PRIVATE_ATTRS:
                    raise AttributeError(
                        f"Unzulässiges privates Attribut '{attr_name}' in Klasse '{cls.__name__}'. "
                        f"Erlaubt sind nur: {cls.ALLOWED_PRIVATE_ATTRS}"
                    )
    

# Interface für Komponenten in Datenpipelines
class BaseComponent(ABC):
    """
    Verbindliche Basisklasse für alle Pipeline-Komponenten.
    Erzwingt:
    - saubere Konstruktor-Signatur
    - verpflichtende Klassenattribute
    - konsistente run()-Signatur
    """

    # ---- verpflichtende Klassenattribute ----
    CONFIG_CLASS: Optional[Type] = None
    INPUT_CLASS: Optional[Type] = None   # darf bei Loader None sein
    OUTPUT_CLASS: Optional[Type] = None
    RUN_CONTEXT_CLASS: Optional[Type] = None

    def __init__(
        self,
        *,
        config,
        global_build_ctx):
        
        # --- Basiskomponenten ---
        self.config = config
        self.global_build_ctx = global_build_ctx
        self.build_logger = global_build_ctx.build_logger

        # --- Validierung ---
        self._validate_class_contract()
        self._validate_config()

    # ------------------------------------------------------------------
    # Validierung
    # ------------------------------------------------------------------

    @classmethod
    def _is_loader(cls) -> bool:
        """
        Loader dürfen INPUT_CLASS = None haben
        """
        return cls.INPUT_CLASS is None

    @classmethod
    def _validate_class_contract(cls):
        """
        Erzwingt das deklarative Component-Interface
        """
        if cls.CONFIG_CLASS is None and not cls._is_loader():
            raise TypeError(
                f"{cls.__name__}: CONFIG_CLASS muss gesetzt sein"
            )

        if cls.OUTPUT_CLASS is None:
            raise TypeError(
                f"{cls.__name__}: OUTPUT_CLASS muss gesetzt sein"
            )

        if cls.RUN_CONTEXT_CLASS is None:
            raise TypeError(
                f"{cls.__name__}: RUN_CONTEXT_CLASS muss gesetzt sein"
            )

    def _validate_config(self):
        """
        Validiert das Config-Objekt zur Laufzeit
        """
        if self.CONFIG_CLASS is not None:
            if not isinstance(self.config, self.CONFIG_CLASS):
                raise TypeError(
                    f"{self.__class__.__name__}: "
                    f"config muss vom Typ {self.CONFIG_CLASS.__name__} sein, "
                    f"bekommen: {type(self.config).__name__}"
                )

    # ------------------------------------------------------------------
    # Pflicht-API
    # ------------------------------------------------------------------

    @abstractmethod
    def run(
        self,
        data,
        *,
        component_ctx,
        global_ctx,
    ):
        """
        Einheitliche Ausführungssignatur für alle Komponenten.
        Muss implementiert werden.
        """
        raise NotImplementedError

# %%
