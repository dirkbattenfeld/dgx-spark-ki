import dagster.components.core.load_defs as ld
import inspect

# Wir schauen uns an, welche Typen die Funktion WIRKLICH erwartet
print(inspect.signature(ld.build_component_defs))

print("-------------------------------------")

import pkgutil
import dagster.components.core as dg_core

# Wir listen alle Submodule von .core auf
print([name for _, name, _ in pkgutil.iter_modules(dg_core.__path__)])