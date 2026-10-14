"""FastAPI layer. Calls services; contains no causal math."""

from causalimpact.api.app import ApiState, create_app

__all__ = ["ApiState", "create_app"]
