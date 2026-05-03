"""Vercel serverless entry point.

Vercel's @vercel/python runtime detects an ASGI `app` export and serves it.
We re-export the FastAPI app from backend.main here.
"""
import sys
import os

# Make backend importable from /var/task on Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app  # noqa: E402,F401

# Vercel inspects this module-level variable
__all__ = ["app"]
