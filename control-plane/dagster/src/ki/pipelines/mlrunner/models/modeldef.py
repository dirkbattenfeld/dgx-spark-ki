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
# ki/pipelines/mlrunner/models/modeldef.py
# Scikit Learn

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
#from xgboost import XGBClassifier

from ki.pipelines.mlrunner.models.registry import modeldef_registry
from ki.pipelines.mlrunner.models.base import ModelDef
from ki.pipelines.mlrunner.models.scikit_specs import RandomForestSpec, GradientBoostingSpec, LogisticRegressionSpec, SVCSpec
#from ki.pipelines.mlrunner.models.keras_specs import KerasDenseSpec
#from ki.pipelines.mlrunner.models.xgboost_specs import XGBoostSpec
from ki.pipelines.mlrunner.adapter.base import ModelCapability

# %%
modeldef_registry.register("randomforest")(ModelDef(
    name="randomforest",
    spec_cls=RandomForestSpec,
    model_cls=RandomForestClassifier,
    adapter_key="general_scikit",
    capabilities={ModelCapability.TRAIN, ModelCapability.PREDICT}
))

modeldef_registry.register("gradient_boosting")(ModelDef(
    name="gradient_boosting",
    spec_cls=GradientBoostingSpec,
    model_cls=GradientBoostingClassifier,
    adapter_key="general_scikit",
    capabilities={ModelCapability.TRAIN, ModelCapability.PREDICT}
))

modeldef_registry.register("logistic_regression")(ModelDef(
    name="logistic_regression",
    spec_cls=LogisticRegressionSpec,
    model_cls=LogisticRegression,
    adapter_key="general_scikit",
    capabilities={ModelCapability.TRAIN, ModelCapability.PREDICT}
))

modeldef_registry.register("svc")(ModelDef(
    name="svc",
    spec_cls=SVCSpec,
    model_cls=SVC,
    adapter_key="general_scikit",
    capabilities={ModelCapability.TRAIN, ModelCapability.PREDICT}
))

# Keras
#modeldef_registry.register("keras_dense")(ModelDef(
#    name="keras_dense",
#    spec_cls=KerasDenseSpec,
#    model_cls=None,   # bewusst None, Keras baut intern
#    adapter_key="keras",
#    capabilities={
#        ModelCapability.BUILD,
#        ModelCapability.TRAIN,
#        ModelCapability.PREDICT,
#    }
#))

# XGBoost
#modeldef_registry.register("xgboost")(ModelDef(
#    name="xgboost",
#    spec_cls=XGBoostSpec,
#    model_cls=XGBClassifier,
#    adapter_key="general_scikit",
#    capabilities={ModelCapability.TRAIN, ModelCapability.PREDICT}
#))
