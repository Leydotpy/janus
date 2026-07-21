from typing import Dict
from fastapi import Request

def debug_processor(request: Request) -> Dict:
    # example: add DEBUG flag from settings
    from janus_api.conf import settings
    return {"DEBUG": getattr(settings, "DEBUG", False)}

def common_context(request: Request) -> Dict:
    # example: add something derived from request
    user_agent = request.headers.get("user-agent", "")
    return {"client_ua": user_agent}
