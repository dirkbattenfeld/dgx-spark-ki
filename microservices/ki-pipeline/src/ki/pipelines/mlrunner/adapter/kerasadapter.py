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
# ki/pipelines/mlrunner/adapter/kerasadapter.py

from tensorflow import keras
from tensorflow.keras import layers, models
from tensorflow.keras import layers
import numpy as np

from ki.pipelines.mlrunner.adapter.registry import adapter_registry
from ki.pipelines.mlrunner.adapter.base import BaseAdapter


# %%
@adapter_registry.register("keras")
class KerasAdapter(BaseAdapter):
    def __init__(self, spec, model_cls=None):
        """
        model_cls wird ignoriert, Keras baut selbst
        """
        self.spec = spec
        self.model = None

    def build(self, X=None, y=None):
        """
        Baut das Keras-Modell anhand der Layer-Spezifikation.
        """
        model = keras.Sequential()
        input_dim = X.shape[1] if X is not None else self.spec.input_dim

        for i, layer_cfg in enumerate(self.spec.layers):
            if i == 0:
                # erster Layer muss input_dim kennen
                model.add(layers.Dense(layer_cfg.units,
                                       activation=layer_cfg.activation,
                                       input_dim=input_dim))
            else:
                model.add(layers.Dense(layer_cfg.units,
                                       activation=layer_cfg.activation))

        # Output-Layer für Klassifikation oder Regression
        if self.spec.task_type == "classification":
            if self.spec.num_classes == 2:
                # Binärklassifikation
                model.add(layers.Dense(1, activation="sigmoid"))
            else:
                # Multi-Klassen
                model.add(layers.Dense(self.spec.num_classes, activation="softmax"))
        else:
            # Regression
            model.add(layers.Dense(1, activation="linear"))

        optimizer = getattr(keras.optimizers, self.spec.optimizer)()
        model.compile(optimizer=optimizer,
                      loss=self.spec.loss,
                      metrics=self.spec.metrics)
        self.model = model

    def train(self, X, y):
        """
        Trainiert das Modell.
        """
        self.model.fit(
            X, y,
            epochs=self.spec.epochs,
            batch_size=self.spec.batch_size,
            verbose=0
        )

    def predict(self, X):
        """
        Liefert Labels für Klassifikation oder Werte für Regression.
        """
        y_pred = self.model.predict(X, verbose=0)

        if self.spec.task_type == "classification":
            if y_pred.shape[1] == 1:
                # Binärklassifikation: Threshold bei 0.5
                y_pred_labels = (y_pred > 0.5).astype(int).flatten()
            else:
                # Multi-Klassen: argmax
                y_pred_labels = np.argmax(y_pred, axis=1)
            return y_pred_labels
        else:
            return y_pred.flatten()

# %%
