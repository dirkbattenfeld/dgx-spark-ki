import pkgutil

import dagster
import dagster.components
import dagster.preview
import dagster.components.components
import dagster.components.component.component_loader
import dagster.components.component.component_scaffolder

print("DEBUG: Submodule von dagster:")
for loader, module_name, is_pkg in pkgutil.walk_packages(dagster.__path__, dagster.__name__ + "."):
    print(f" - {module_name}")

print("DEBUG: Submodule von dagster.components:")
for loader, module_name, is_pkg in pkgutil.walk_packages(dagster.components.__path__, dagster.components.__name__ + "."):
    print(f" - {module_name}")

print([item for item in dir(dagster) if not item.startswith("_")])

print([item for item in dir(dagster.components) if not item.startswith("_")])

print([item for item in dir(dagster.components.components) if not item.startswith("_")])

print([item for item in dir(dagster.components.component) if not item.startswith("_")])

print([item for item in dir(dagster.components.component.component_loader) if not item.startswith("_")])

print([item for item in dir(dagster.components.component.component_scaffolder) if not item.startswith("_")])

print([item for item in dir(dagster.preview) if not item.startswith("_")])
