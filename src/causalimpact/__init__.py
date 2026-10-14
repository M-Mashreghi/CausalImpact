"""CausalImpact: an estimand-first, assumption-aware causal inference platform."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("causalimpact")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
