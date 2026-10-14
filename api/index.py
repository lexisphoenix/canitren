"""Vercel Serverless entrypoint."""
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.src.main import app as fastapi_app


class VercelPathFixMiddleware:
    """Fix ASGI scope['path'] when Vercel rewrites requests to /api/index.py."""

    def __init__(self, app):
        self.app = app

    def __getattr__(self, name):
        return getattr(self.app, name)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            matched_path = (
                headers.get(b"x-matched-path", b"")
                or headers.get(b"x-forwarded-uri", b"")
            ).decode("latin1")

            current_path = scope.get("path", "")
            if matched_path and ("index.py" in current_path or current_path in ("/api", "/api/")):
                clean_path = matched_path.split("?")[0]
                scope["path"] = clean_path

        await self.app(scope, receive, send)


app = VercelPathFixMiddleware(fastapi_app)
