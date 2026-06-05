"""Shippy helpers for GitHub pull request summaries and reviews."""

from importlib.metadata import version

from shippy.review import review_pull_request
from shippy.summary import summarize_pull_request

__version__ = version("shippy-ai")

__all__ = ["__version__", "review_pull_request", "summarize_pull_request"]
