#ki/bootstrap/internal/pipe_mlrunner.py
#Füllt component_registry mit den Komponenten für die Pipeline ki/pipelines/mlrunner

# adapter_registry befüllen
from ki.pipelines.mlrunner.adapter import bootstrap

# spec_registry und modeldef_registry befüllen
from ki.pipelines.mlrunner.models import bootstrap

# component_registry mit Komponenten für ML Runner Pipeline befüllen
from ki.pipelines.mlrunner.csvloader import CSVLoader
from ki.pipelines.mlrunner.stratifiedsampler import StratifiedSampler
from ki.pipelines.mlrunner.mlrunner import MLRunner
from ki.pipelines.mlrunner.scikitlearnmetrics import SciKitLearnMetrics
