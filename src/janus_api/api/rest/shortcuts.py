from typing import Dict, Any, Callable, Iterable, List, Optional, Union
from fastapi import Request

from janus_api.conf import settings
from janus_api.utils import import_string, resolve_callable

TEMPLATE = getattr(settings, "TEMPLATE")


def _processor_cache_key(proc: Callable) -> str:
    """
    Create a reasonably stable key for a context-processor callable.
    Prefer module + name when available; fallback to id().
    """
    try:
        name = proc.__name__
        module = proc.__module__
        return f"{module}.{name}"
    except Exception:
        return f"id:{id(proc)}"


class TemplatesWrapper:
    """
    Wrapper around backend instance which:
      - runs context processors and merges their results into the template context
      - optionally caches each processor result on request.state to avoid re-running
        expensive processors multiple times during the same request
    """
    def __init__(
        self,
        backend_instance: Any,
        context_processors: Optional[Iterable[Callable]] = None,
        cache_processors: bool = True,
        cache_state_attr: str = "_template_context_processor_cache",
    ):
        self._backend = backend_instance
        self._context_processors: List[Callable] = list(context_processors or [])
        self._cache_processors = bool(cache_processors)
        self._cache_state_attr = cache_state_attr

    def _ensure_request_cache(self, request: Request) -> Dict[str, Dict]:
        """
        Ensure request.state has a dict to hold cached processor results.
        Returns the dict.
        """
        cache = getattr(request.state, self._cache_state_attr, None)
        if cache is None:
            cache = {}
            setattr(request.state, self._cache_state_attr, cache)
        return cache

    def response(self, *, request: Request, name: str, context: Dict[str, Any]):
        # Start with a shallow copy so we don't mutate caller's dict
        merged_context = dict(context or {})

        # Ensure request is always available to templates
        merged_context.setdefault("request", request)

        # Prepare or fetch the per-request cache container
        if self._cache_processors:
            request_cache = self._ensure_request_cache(request)
        else:
            request_cache = None

        # Execute context processors and merge their contexts
        for cp in self._context_processors:
            cp_key = _processor_cache_key(cp)

            if request_cache is not None and cp_key in request_cache:
                cp_result = request_cache[cp_key]
            else:
                # call the processor; support both signatures (request) or ()
                try:
                    cp_result = cp(request)
                except TypeError:
                    cp_result = cp()
                if cp_result and not isinstance(cp_result, dict):
                    raise TypeError(f"context processor {cp!r} must return a dict, got {type(cp_result)}")

                if request_cache is not None:
                    # cache even empty dicts (to avoid future calls)
                    request_cache[cp_key] = cp_result or {}

            if cp_result:
                # Later processors override earlier keys (Django-style)
                merged_context.update(cp_result)

        # Delegate to backend TemplateResponse
        return self._backend.TemplateResponse(request=request, name=name, context=merged_context)


_templates_wrapper: Optional[TemplatesWrapper] = None


def _get_templates() -> TemplatesWrapper:
    global _templates_wrapper
    if _templates_wrapper is not None:
        return _templates_wrapper

    backend_path = TEMPLATE.get("BACKEND")
    if not backend_path:
        raise RuntimeError("TEMPLATE['BACKEND'] is not configured in settings")

    BackendClass = import_string(backend_path) # type: ignore

    # Build kwargs for backend instantiation. Pass DIR and any OPTIONS except context_processors and our cache flag.
    kwargs = {}
    if "DIR" in TEMPLATE:
        kwargs["directory"] = TEMPLATE["DIR"]
    options = TEMPLATE.get("OPTIONS", {}) or {}
    for key, val in options.items():
        if key in ("context_processors", "cache_context_processors"):
            continue
        kwargs[key] = val

    backend_instance = BackendClass(**kwargs)

    # Resolve context processors (strings or callables)
    context_processors_config = options.get("context_processors", []) or []
    resolved_cps = [resolve_callable(cp) for cp in context_processors_config]

    cache_processors = options.get("cache_context_processors", True)

    _templates_wrapper = TemplatesWrapper(
        backend_instance=backend_instance,
        context_processors=resolved_cps,
        cache_processors=cache_processors,
    )
    return _templates_wrapper # type: ignore


def render(request: Request, template_name: str, context: Dict[str, Any]):
    return _get_templates().response(request=request, name=template_name, context=context)
