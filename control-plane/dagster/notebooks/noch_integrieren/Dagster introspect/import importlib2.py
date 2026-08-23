import importlib
import inspect
import pkgutil



print("DEBUG: Submodule von dagster_components:")
for loader, module_name, is_pkg in pkgutil.walk_packages(dagster_components.__path__, dagster_components.__name__ + "."):
    print(f" - {module_name}")

def inspect_subpackage(package_name):
    print(f"\n--- Scanning Package: {package_name} ---")
    try:
        module = importlib.import_module(package_name)
        # Wir suchen nach allen Klassen, die in diesem Modul definiert sind
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj):
                # Wir prüfen, ob die Klasse wirklich in diesem Modul definiert wurde 
                # (und nicht nur von woanders importiert wurde)
                if obj.__module__ == package_name:
                    print(f" gefunden: Klasse '{name}'")
    except ImportError as e:
        print(f" Fehler: {e}")

inspect_subpackage("dagster_components.dagster")
inspect_subpackage("dagster_components.dagster_dbt")
inspect_subpackage("dagster_components.dagster_sling")
inspect_subpackage("dagster_components.version")