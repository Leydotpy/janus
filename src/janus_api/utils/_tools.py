import importlib
from typing import Callable, Union


def import_string(dotted_path: str):
    try:
        module_path, attr = dotted_path.rsplit(".", 1)
    except ValueError as e:
        raise ImportError(f"Invalid dotted path '{dotted_path}'") from e

    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as e:
        raise ImportError(f"Module '{module_path}' has no attribute '{attr}'") from e

def resolve_callable(obj: Union[str, Callable]) -> Callable:
    if isinstance(obj, str):
        callable_obj = import_string(obj)
    else:
        callable_obj = obj

    if not callable(callable_obj):
        raise TypeError(f"context processor {obj!r} is not callable")
    return callable_obj