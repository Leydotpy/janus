import importlib
import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class PluginFilesLoader:
    _ready = False
    _MODULE_DIR_NAME = "plugins"  # directory name inside project root

    @classmethod
    def find_plugins_dir(cls, start: Path | None = None) -> Path:
        start = (start or Path(__file__)).resolve()
        project_root = start
        # simple upward search for .git or pyproject.toml etc (same logic as earlier)
        for p in [start] + list(start.parents):
            if (p / cls._MODULE_DIR_NAME).exists():
                return p / cls._MODULE_DIR_NAME
        raise RuntimeError("plugins directory not found")

    @classmethod
    def load(cls) -> None:
        if cls._ready:
            return
        try:
            plugins_dir = cls.find_plugins_dir()
        except Exception as e:
            logger.exception("Could not find plugins directory: %s", e)
            raise

        for entry in plugins_dir.iterdir():
            # load only python files or packages with __init__.py
            if entry.is_file() and entry.suffix == ".py" and entry.name != "__init__.py":
                module_name = f"file_plugin_{entry.stem}"
                spec = importlib.util.spec_from_file_location(module_name, entry)
                if spec and spec.loader:
                    m = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = m
                    try:
                        spec.loader.exec_module(m)
                        logger.debug("Loaded plugin module from file: %s", entry)
                    except Exception:
                        logger.exception("Failed to exec plugin module %s", entry)
            elif entry.is_dir() and (entry / "__init__.py").exists():
                # package: load its __init__.py
                init_file = entry / "__init__.py"
                module_name = f"file_plugin_pkg_{entry.name}"
                spec = importlib.util.spec_from_file_location(module_name, init_file)
                if spec and spec.loader:
                    m = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = m
                    try:
                        spec.loader.exec_module(m)
                        logger.debug("Loaded plugin package from: %s", entry)
                    except Exception:
                        logger.exception("Failed to exec package %s", entry)
        cls._ready = True
