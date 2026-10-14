"""Specification robustness runner (Task 5.1).

A ``SpecificationGrid`` is declared (timestamped and fingerprinted) *before* it is run.
Every declared variant is run and every outcome is stored, including refusals and
failures; nothing is filtered, ranked or selected. One variant is the declared primary
specification; the others are compared with it descriptively.

All variants must target the same estimand: a variant whose estimator cannot target it
is recorded as ``refused`` rather than silently re-targeted. Diagnostic refusals
(insufficient overlap, too few clusters) are also ``refused``; other errors are
``failed``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, JsonValue

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandMismatchError
from causalimpact.domain.fingerprint import content_hash
from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.estimators.clustering import ClusterInferenceError
from causalimpact.observational.overlap import OverlapRefusedError


@dataclass(frozen=True)
class SpecificationVariant:
    label: str
    estimator: Estimator
    description: str = ""

    def config(self) -> dict[str, JsonValue]:
        return {
            "label": self.label,
            "estimator": self.estimator.name,
            "definition": repr(self.estimator),
            "description": self.description,
        }


@dataclass(frozen=True)
class SpecificationGrid:
    variants: tuple[SpecificationVariant, ...]
    primary: str
    declared_at: datetime

    def __post_init__(self) -> None:
        labels = [v.label for v in self.variants]
        if len(labels) != len(set(labels)):
            raise ValueError("specification labels must be unique")
        if self.primary not in labels:
            raise ValueError("the primary specification must be one of the variants")
        if self.declared_at.tzinfo is None:
            raise ValueError("declared_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        return content_hash(
            {
                "primary": self.primary,
                "declared_at": self.declared_at.isoformat(),
                "variants": [v.config() for v in self.variants],
            }
        )


class SpecStatus(StrEnum):
    SUCCEEDED = "succeeded"
    REFUSED = "refused"
    FAILED = "failed"


class SpecificationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    is_primary: bool
    status: SpecStatus
    estimator: str
    estimate: EffectEstimate | None = None
    error: str | None = None


class SpecificationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    grid_fingerprint: str
    estimand_id: str
    outcomes: tuple[SpecificationOutcome, ...]
    summary: dict[str, JsonValue]


def run_specifications(
    grid: SpecificationGrid,
    data: pd.DataFrame,
    estimand: Estimand,
    *,
    run_at: datetime,
    confidence_level: float = 0.95,
) -> SpecificationReport:
    if grid.declared_at > run_at:
        raise ValueError("the specification grid must be declared before it is run")
    outcomes: list[SpecificationOutcome] = []
    for variant in grid.variants:
        base = {
            "label": variant.label,
            "is_primary": variant.label == grid.primary,
            "estimator": variant.estimator.name,
        }
        try:
            est = run_estimator(
                variant.estimator, data, estimand, confidence_level=confidence_level
            )
        except (EstimandMismatchError, OverlapRefusedError, ClusterInferenceError) as exc:
            outcomes.append(SpecificationOutcome(**base, status=SpecStatus.REFUSED, error=str(exc)))
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            outcomes.append(
                SpecificationOutcome(
                    **base, status=SpecStatus.FAILED, error=f"{type(exc).__name__}: {exc}"
                )
            )
        else:
            outcomes.append(SpecificationOutcome(**base, status=SpecStatus.SUCCEEDED, estimate=est))
    return SpecificationReport(
        grid_fingerprint=grid.fingerprint,
        estimand_id=estimand.estimand_id,
        outcomes=tuple(outcomes),
        summary=_summarize(outcomes),
    )


def _summarize(outcomes: Sequence[SpecificationOutcome]) -> dict[str, JsonValue]:
    done = [o for o in outcomes if o.estimate is not None]
    primary = next((o for o in outcomes if o.is_primary), None)
    summary: dict[str, JsonValue] = {
        "n_declared": len(outcomes),
        "n_succeeded": len(done),
        "n_refused": sum(o.status is SpecStatus.REFUSED for o in outcomes),
        "n_failed": sum(o.status is SpecStatus.FAILED for o in outcomes),
        "primary_status": primary.status.value if primary else None,
    }
    if not done:
        return summary
    values = np.array([o.estimate.estimate for o in done if o.estimate is not None])
    summary |= {
        "min_estimate": float(values.min()),
        "max_estimate": float(values.max()),
        "median_estimate": float(np.median(values)),
        "share_ci_excludes_zero": float(
            np.mean(
                [
                    o.estimate.ci_lower > 0 or o.estimate.ci_upper < 0
                    for o in done
                    if o.estimate is not None
                ]
            )
        ),
    }
    if primary is not None and primary.estimate is not None:
        sign = np.sign(primary.estimate.estimate)
        summary["share_same_sign_as_primary"] = float(np.mean(np.sign(values) == sign))
    return summary
