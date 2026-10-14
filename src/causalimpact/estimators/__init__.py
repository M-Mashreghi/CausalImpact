"""Estimator contracts shared across design families."""

from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.estimators.clustering import (
    ClusterInferenceError,
    ClusterPolicy,
    check_clusters,
)

__all__ = [
    "ClusterInferenceError",
    "ClusterPolicy",
    "Estimator",
    "check_clusters",
    "run_estimator",
]
