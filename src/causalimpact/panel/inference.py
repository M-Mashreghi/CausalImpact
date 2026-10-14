"""Inference for DiD contrasts of unit-level summaries.

Without a cluster column, units are the clusters and the Welch/Neyman variance of the
unit-level differences is used. With ``PanelSpec.cluster`` (e.g. state), units must be
nested in clusters; the contrast is then estimated with CR1 standard errors clustered at
that level and t(G - 1) intervals, after the cluster-count checks of Task 4.6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import JsonValue
from scipy import stats

from causalimpact.estimators.clustering import (
    ClusterPolicy,
    check_clusters,
    clustered_mean_difference,
    ensure_clusters,
)
from causalimpact.panel.contract import PanelSpec


@dataclass(frozen=True)
class ContrastInference:
    estimate: float
    std_error: float
    degrees_of_freedom: float
    critical_value: float
    method: str
    cluster_diagnostics: dict[str, JsonValue]

    def p_value(self) -> float:
        return float(2 * stats.t.sf(abs(self.estimate) / self.std_error, self.degrees_of_freedom))


def unit_cluster_labels(data: pd.DataFrame, spec: PanelSpec, units: pd.Index) -> np.ndarray:
    assert spec.cluster is not None
    per_unit = data.groupby(spec.unit)[spec.cluster].nunique()
    if (per_unit > 1).any():
        raise ValueError("units must be nested in clusters (cluster constant within unit)")
    labels: np.ndarray = data.groupby(spec.unit)[spec.cluster].first().loc[units].to_numpy()
    return labels


def contrast_inference(
    data: pd.DataFrame,
    spec: PanelSpec,
    units: pd.Index,
    values: np.ndarray,
    treated: np.ndarray,
    confidence_level: float,
    policy: ClusterPolicy | None = None,
) -> ContrastInference:
    t = np.asarray(treated, dtype=bool)
    if spec.cluster is None:
        d_t, d_c = values[t], values[~t]
        v_t, v_c = d_t.var(ddof=1) / d_t.size, d_c.var(ddof=1) / d_c.size
        se = math.sqrt(v_t + v_c)
        df = (v_t + v_c) ** 2 / (v_t**2 / (d_t.size - 1) + v_c**2 / (d_c.size - 1))
        crit = float(stats.t.ppf(0.5 + confidence_level / 2, df))
        diag = check_clusters(np.asarray(units), t, policy)
        return ContrastInference(
            estimate=float(d_t.mean() - d_c.mean()),
            std_error=se,
            degrees_of_freedom=float(df),
            critical_value=crit,
            method="unit_level_welch_t (clustered on unit)",
            cluster_diagnostics={
                "cluster_level": spec.unit,
                **diag.metrics,
                "findings": [f.model_dump(mode="json") for f in diag.findings],
            },
        )
    clusters = unit_cluster_labels(data, spec, units)
    diag = check_clusters(clusters, t, policy)
    ensure_clusters(diag)
    estimate, se, df, crit = clustered_mean_difference(values, t, clusters, confidence_level)
    return ContrastInference(
        estimate=estimate,
        std_error=se,
        degrees_of_freedom=df,
        critical_value=crit,
        method=f"CR1 clustered on {spec.cluster}, t with G-1 df",
        cluster_diagnostics={
            "cluster_level": spec.cluster,
            **diag.metrics,
            "findings": [f.model_dump(mode="json") for f in diag.findings],
        },
    )
