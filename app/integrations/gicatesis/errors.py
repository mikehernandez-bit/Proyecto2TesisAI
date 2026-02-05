"""
GicaTesis Integration - Custom Exceptions

SRP: Only error definitions, no logic.
Used by client.py and propagated to router.py for HTTP error mapping.
"""
from __future__ import annotations


class GicaTesisError(Exception):
    """Base error for GicaTesis integration."""
    pass


class UpstreamUnavailable(GicaTesisError):
    """GicaTesis server is not responding or connection refused."""
    pass


class UpstreamTimeout(GicaTesisError):
    """Timeout while connecting to GicaTesis."""
    pass


class BadUpstreamResponse(GicaTesisError):
    """Unexpected response from GicaTesis (malformed JSON, etc.)."""
    pass
