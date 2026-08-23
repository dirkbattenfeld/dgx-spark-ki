# ki/bootstrap/core.py
# Hier werden alle bootstraps für das Core System durchgeführt

from ki.artifactstore.serializer import bootstrap
from ki.core.pipelineresult.projector import bootstrap
from ki.core.pipelineresult.flattener import bootstrap
from ki.core.pipelineresult.writer import bootstrap

from ki.core.pipelineorchestrator.generator import bootstrap
