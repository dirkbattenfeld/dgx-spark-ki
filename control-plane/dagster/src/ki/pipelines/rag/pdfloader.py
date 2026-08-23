from pathlib import Path
from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass

from ki.pipelines.base.registry import component_registry
from ki.pipelines.base.base import BaseComponent, BaseComponentResult
from ki.core.datapipeline.datapipeline_dataclasses import BaseRunContext

class PdfLoaderConfig(BaseModel):
    path: Path

class ExtractInput(BaseComponentResult):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_pdf: Path
    
@dataclass
class PdfLoaderRunContext(BaseRunContext[PdfLoaderConfig]):
    component_name: str
    config: PdfLoaderConfig
   
    def __post_init__(self):
        super().__init__(component_name=self.component_name, config=self.config)

@component_registry.register('pdf_loader')
class PdfLoader(BaseComponent):
    CONFIG_CLASS = PdfLoaderConfig
    INPUT_CLASS = None
    OUTPUT_CLASS = ExtractInput
    RUN_CONTEXT_CLASS = BaseRunContext

    def run(self, data, *, component_ctx: PdfLoaderRunContext, global_ctx) -> ExtractInput:
        source_pdf = Path(component_ctx.config.path)
        output = ExtractInput(
            source_pdf = source_pdf
        )
        return output

