"""Vercel entry — re-exports the FastAPI app."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.main import app  # noqa: E402,F401

__all__ = ["app"]
