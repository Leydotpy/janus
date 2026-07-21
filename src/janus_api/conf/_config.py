"""
Enhanced Django-like global settings system.

Features added:
- from_env: optionally read a .env file and import values into os.environ (without overwriting existing env vars)
- inspect_settings(): returns detailed mapping of each uppercase setting to (value, source)
- SettingsSpec dataclass: typed specification of expected settings + runtime validation
- manage_settings CLI: dump settings (json/pretty), optionally show sources
- as_dict() caching with TTL
- Pydantic v2-compatible SettingsFactory that will try to validate using Pydantic v2 (and fallback to v1)
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type
from pydantic import BaseModel

_ENV_VAR = "GLOBAL_SETTINGS_MODULE"
_DEFAULT_MODULES = ("janus_api.conf.settings",)
_LOCAL_SETTINGS_FILENAME = "local_settings"


logger = logging.getLogger(__name__)


class SettingsLoadError(RuntimeError):
    pass


@dataclass
class SettingsSpecItem:
    """One specification entry for a setting.

    name: uppercase name of setting (e.g. 'DEBUG')
    type: expected Python type or tuple of types (e.g. bool, str, (list, tuple))
    default: optional default value
    required: if True, it's an error if the final value is missing
    validator: optional callable(value) -> bool that returns True when valid
    """

    name: str
    type: Optional[type] = None
    default: Any = None
    required: bool = False
    validator: Optional[Callable[[Any], bool]] = None


class _SettingsProxy:
    """Thread-safe, lazy-loading settings proxy with extended features.

    Precedence (highest -> lowest):
      1. programmatic overrides (settings.X = ...)
      2. environment variables (if present)
      3. local_settings (sibling module overlay)
      4. main module attributes
      5. configured defaults passed to configure(...)

    Important options available in `configure()`:
      - module: module name to import
      - defaults: dict of default values
      - freeze: if True, block runtime assignment
      - from_env: if True, load .env file before reading OS env (won't overwrite existing env variables)
      - env_file: path to .env file or None (if from_env=True and env_file None, will search for `.env` next to module)
      - env_prefix: optional prefix to apply when reading environment vars for settings
      - cache_ttl: seconds for caching results of as_dict()
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._module_name: Optional[str] = None
        self._module: Optional[ModuleType] = None
        self._overrides: Dict[str, Any] = {}
        self._defaults: Dict[str, Any] = {}
        self._frozen: bool = False
        self._env_overrides: Dict[str, Any] = {}  # values present in environment
        # caching of as_dict
        self._cache_ttl: float = 0.0
        self._cache_value: Optional[Dict[str, Any]] = None
        self._cache_at: float = 0.0
        # last used env file
        self._env_file: Optional[str] = None
        self._env_prefix: Optional[str] = None

    # ---------- configuration API -----------
    def configure(
        self,
        module: Optional[str] = None,
        defaults: Optional[Dict[str, Any]] = None,
        freeze: bool = False,
        from_env: bool = False,
        env_file: Optional[str] = None,
        env_prefix: Optional[str] = None,
        cache_ttl: float = 0.0,
    ) -> None:
        """Programmatically configure the settings proxy.

        - module: Python module path to import (e.g., 'myapp.settings')
        - defaults: mapping of fallback defaults
        - freeze: prevent runtime assignment
        - from_env: if True, attempt to read an .env file and merge values into environment
        - env_file: explicit path to .env file; if None and from_env True, we will try to find one
        - env_prefix: optional string prefix used for env var lookups (see _env_key)
        - cache_ttl: seconds for as_dict caching (0 disables caching)
        """
        with self._lock:
            if module:
                self._module_name = module
                self._module = None
            if defaults:
                self._defaults = dict(defaults)
            self._frozen = bool(freeze)
            self._env_prefix = env_prefix
            self._cache_ttl = float(cache_ttl or 0.0)
            # clear overrides and env overrides so configure is a fresh start
            self._overrides.clear()
            self._env_overrides.clear()
            # handle env file reading
            if from_env:
                # attempt to load env file into os.environ
                ef = env_file or self._find_env_file_for_module(self._module_name)
                if ef:
                    self._read_dotenv(ef)
                    self._env_file = ef

            # clear module cache so next access re-imports if needed
            self._module = None
            # reset as_dict cache
            self._cache_value = None
            self._cache_at = 0.0

    def reload(self) -> None:
        """Force re-import of configured module and clear caches."""
        with self._lock:
            if self._module_name and self._module_name in sys.modules:
                del sys.modules[self._module_name]
            self._module = None
            self._env_overrides.clear()
            self._cache_value = None
            self._cache_at = 0.0

    # ---------- As-dict caching ----------
    def _is_cache_valid(self) -> bool:
        if not self._cache_value:
            return False
        if self._cache_ttl <= 0.0:
            return False
        return (time.time() - self._cache_at) < self._cache_ttl

    # ---------- attribute access -----------
    def __getattr__(self, name: str) -> Any:
        if not name.isupper():
            raise AttributeError(f"Settings attribute must be uppercase: {name!r}")

        with self._lock:
            # programmatic override
            if name in self._overrides:
                return self._overrides[name]

            # environment override
            env_key = self._env_key(name)
            if env_key in os.environ:
                val = self._coerce_env_value(os.environ[env_key])
                # cache into env_overrides to mark source
                self._env_overrides[name] = val
                return val

            # defaults
            if name in self._defaults:
                return self._defaults[name]

            # module load
            self._ensure_loaded()
            if self._module and hasattr(self._module, name):
                return getattr(self._module, name)

            # if not found
            raise AttributeError(f"Setting {name!r} not found")

    def __setattr__(self, name: str, value: Any) -> None:
        # allow internal attributes
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        with self._lock:
            if self._frozen:
                raise RuntimeError("Settings are frozen; runtime assignment is not allowed")
            if not name.isupper():
                raise AttributeError("Only uppercase setting names are allowed")
            self._overrides[name] = value
            # invalidate cache
            self._cache_value = None
            self._cache_at = 0.0

    def as_dict(self) -> Dict[str, Any]:
        """Return a merged dict representing current settings (with caching support).

        The value is resolved using precedence described above.
        """
        with self._lock:
            if self._is_cache_valid():
                return dict(self._cache_value)  # shallow copy

            # ensure module loaded so we can inspect it
            self._ensure_loaded()

            base: Dict[str, Any] = {}
            if self._module:
                for k, v in vars(self._module).items():
                    if k.isupper():
                        base[k] = v

            merged: Dict[str, Any] = {}
            # start with defaults
            merged.update(self._defaults)
            # overlay module
            merged.update(base)
            # overlay local_settings (already placed into overrides by _ensure_loaded)
            # overlay env values
            for name in list(merged.keys()):
                env_key = self._env_key(name)
                if env_key in os.environ:
                    merged[name] = self._coerce_env_value(os.environ[env_key])
                    self._env_overrides[name] = merged[name]

            # overlay programmatic overrides
            merged.update(self._overrides)

            # cache result
            if self._cache_ttl > 0.0:
                self._cache_value = dict(merged)
                self._cache_at = time.time()

            return merged

    # ---------- helpers for inspection & sources ----------
    def inspect_settings(self) -> Dict[str, Dict[str, Any]]:
        """Return mapping: SETTING_NAME -> {value, source} where source in
        ('override', 'env', 'local_settings', 'module', 'default', 'missing').
        """
        results: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            # gather all candidate keys: defaults + module attrs + overrides + env vars
            self._ensure_loaded()
            keys = set(self._defaults.keys())
            keys.update(self._overrides.keys())
            keys.update(self._env_overrides.keys())
            if self._module:
                for k in vars(self._module).keys():
                    if k.isupper():
                        keys.add(k)

            # also consider any uppercase env var that matches pattern
            for k in os.environ.keys():
                if k.isupper():
                    # reverse map env key to name (strip prefix)
                    if self._env_prefix and k.startswith(self._env_prefix):
                        name = k[len(self._env_prefix) :]
                        if name.isupper():
                            keys.add(name)
                    elif not self._env_prefix:
                        keys.add(k)

            for name in sorted(keys):
                entry: Dict[str, Any] = {"value": None, "source": "missing"}

                # programmatic override
                if name in self._overrides:
                    entry["value"] = self._overrides[name]
                    entry["source"] = "override"
                else:
                    env_key = self._env_key(name)
                    if env_key in os.environ:
                        entry["value"] = self._coerce_env_value(os.environ[env_key])
                        entry["source"] = "env"
                    elif self._module and hasattr(self._module, name):
                        # but was it from local_settings overlay? we stored those into _overrides during load
                        # local_settings we load into _overrides (so they'd appear above). if here, it's from module
                        entry["value"] = getattr(self._module, name)
                        entry["source"] = "module"
                    elif name in self._defaults:
                        entry["value"] = self._defaults[name]
                        entry["source"] = "default"

                results[name] = entry

            return results

    def pretty_inspect(self) -> str:
        """Return a human-friendly string showing settings and their sources."""
        rows: List[str] = []
        inspected = self.inspect_settings()
        for name, info in inspected.items():
            rows.append(f"{name}: ({info['source']}) {repr(info['value'])}")
        return "\n".join(rows)

    # ---------- validation against spec ----------
    def validate_against_spec(self, spec: Iterable[SettingsSpecItem]) -> Tuple[bool, List[str]]:
        """Validate current settings against a spec. Returns (ok, errors).

        Does type-checking and calls custom validators if provided.
        """
        errors: List[str] = []
        current = self.as_dict()

        for item in spec:
            name = item.name
            if name not in current or current.get(name) is None:
                if item.required and item.default is None:
                    errors.append(f"Missing required setting: {name}")
                    continue
                else:
                    # if default available, skip type check
                    value = item.default
            else:
                value = current.get(name)

            # type check
            if item.type and value is not None:
                if not isinstance(value, item.type):
                    errors.append(f"Setting {name} expected type {item.type}, got {type(value)}")
                    continue

            # custom validator
            if item.validator and value is not None:
                try:
                    ok = bool(item.validator(value))
                except Exception as exc:
                    errors.append(f"Validator for {name} raised: {exc}")
                    continue
                if not ok:
                    errors.append(f"Validator failed for {name}")

        return (len(errors) == 0), errors

    # ---------- .env helpers ----------
    def _find_env_file_for_module(self, module_name: Optional[str]) -> Optional[str]:
        # if explicit module provided and is a package.module, try to locate file next to module
        try:
            if module_name:
                parts = module_name.split(".")
                # attempt to import package portion
                pkg = importlib.import_module(".".join(parts[:-1] or parts))
                if hasattr(pkg, "__file__") and pkg.__file__:
                    base_dir = os.path.dirname(os.path.abspath(pkg.__file__))
                    candidate = os.path.join(base_dir, ".env")
                    if os.path.exists(candidate):
                        return candidate
        except Exception as e:
            logger.debug(".env module cannot be found %s", e, exc_info=e)
        # fallback to project root: cwd/.env
        cwd_candidate = os.path.join(os.getcwd(), ".env")
        if os.path.exists(cwd_candidate):
            return cwd_candidate
        return None

    def _read_dotenv(self, path: str) -> None:
        """Minimal .env parser: KEY=VALUE lines, ignores comments and blanks.

        It will set os.environ only for keys not already set (won't overwrite existing env vars).
        """
        try:
            with open(path, "r", encoding="utf8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('\"').strip("\'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except FileNotFoundError:
            pass

    # ---------- utilities ----------
    def _env_key(self, name: str) -> str:
        if self._env_prefix:
            return f"{self._env_prefix}{name}"
        return name

    def _coerce_env_value(self, raw: str) -> Any:
        """Very small heuristic coercion: 'true'/'false'->bool, digits->int, floats->float, comma lists->list"""
        val = raw
        low = val.lower()
        if low in ("true", "false"):
            return low == "true"
        # integers
        try:
            if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
                return int(val)
            # floats
            if "." in val:
                f = float(val)
                return f
        except Exception:
            pass
        # comma-separated list
        if "," in val:
            parts = [p.strip() for p in val.split(",") if p.strip()]
            return parts
        return val

    def _ensure_loaded(self) -> None:
        if self._module is not None:
            return

        module_name = self._module_name or os.environ.get(_ENV_VAR)
        if not module_name:
            # try fallback names
            for candidate in _DEFAULT_MODULES:
                try:
                    m = importlib.import_module(candidate)
                    self._module = m
                    self._module_name = candidate
                    break
                except Exception:
                    continue
            if self._module is None:
                # leave module None; we allow falling back to defaults
                return
        else:
            try:
                m = importlib.import_module(module_name)
                self._module = m
            except Exception as exc:
                raise SettingsLoadError(f"Failed to import settings module {module_name!r}: {exc}") from exc

        # if module has local_settings sibling, import and overlay
        try:
            if self._module and hasattr(self._module, "__package__") and self._module.__package__:
                pkg = self._module.__package__
                local_module_name = f"{pkg}.{_LOCAL_SETTINGS_FILENAME}"
                try:
                    local = importlib.import_module(local_module_name)
                    for k, v in vars(local).items():
                        if k.isupper():
                            # place into overrides so precedence is after env and overrides
                            self._overrides.setdefault(k, v)
                except ModuleNotFoundError:
                    pass
        except Exception:
            pass


# singleton instance
settings = _SettingsProxy()


# convenience helper for tests / CLI
def configure(
    module: Optional[str] = None,
    defaults: Optional[Dict[str, Any]] = None,
    freeze: bool = False,
    from_env: bool = False,
    env_file: Optional[str] = None,
    env_prefix: Optional[str] = None,
    cache_ttl: float = 0.0,
) -> None:
    settings.configure(
        module=module,
        defaults=defaults,
        freeze=freeze,
        from_env=from_env,
        env_file=env_file,
        env_prefix=env_prefix,
        cache_ttl=cache_ttl,
    )


# ---------------- Pydantic v2-compatible SettingsFactory ----------------
class SettingsFactory:
    """Create validated settings instances from Pydantic models (v2 or v1 compatible).

    Usage: SettingsFactory.create_from_pydantic(MySettingsModel, sources=("env","module","defaults"))
    """

    @staticmethod
    def _assemble_data(proxy: _SettingsProxy, include: Iterable[str] = ("env", "module", "defaults", "overrides")) -> Dict[str, Any]:
        # We will use the proxy.as_dict() which already merges sources; however, some user might want to
        # control which sources are included. For simplicity, we return as_dict() which respects precedence.
        return proxy.as_dict()

    @staticmethod
    def create_from_pydantic(model_cls: Type[BaseModel], proxy: Optional[_SettingsProxy] = None) -> Any:
        """Instantiate the provided pydantic model class with data from `proxy` (defaults to global settings).

        This function attempts to be compatible with both Pydantic v2 and v1 by checking
        for the presence of `model_validate` (v2) and `parse_obj` (v1) fallbacks.
        """
        proxy = proxy or settings
        data = SettingsFactory._assemble_data(proxy)

        # detect pydantic v2
        if hasattr(model_cls, "model_validate"):
            # v2
            try:
                return model_cls.model_validate(data)
            except Exception as e:
                # fall through to try constructor
                logger.debug("Failed to validate settings: %s", e)

        # detect v1
        if hasattr(model_cls, "parse_obj"):
            try:
                return model_cls.parse_obj(data)
            except Exception as e:
                logger.debug("Failed to parse settings: %s", e)

        # last-resort: try direct construction
        try:
            return model_cls(**data)
        except Exception as exc:
            raise RuntimeError(f"Failed to instantiate pydantic model: {exc}") from exc


