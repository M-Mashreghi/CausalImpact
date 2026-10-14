"""Multi-period DiD baseline for a single adoption cohort (Task 4.3).

Supported only when every treated unit starts treatment in the *same* period (no
staggered adoption) and the panel is balanced. In that case the static two-way fixed
effects coefficient equals the simple contrast

    ATT = mean_{i in T}(ybar_i,post - ybar_i,pre) - mean_{i in C}(ybar_i,post - ybar_i,pre)

so it is computed that way, transparently, with unit-clustered Welch inference on the
unit-level differences. It is the ATT averaged over post periods with equal weight per
post period. Staggered adoption is refused here: a static TWFE coefficient is not a
clean ATT when timing and effects vary (use the group-time estimator, Task 4.7).

Comparison-group rule is explicit:

* ``never_treated``: only units with no treatment start (units starting after the
  window are excluded and counted);
* ``not_yet_treated``: never-treated units plus units whose start is after the window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd
from scipy import stats

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.panel.contract import PanelSpec, validate_panel


class ComparisonGroup(StrEnum):
    NEVER_TREATED = "never_treated"
    NOT_YET_TREATED = "not_yet_treated"


@dataclass(frozen=True)
class SingleCohortDiD:
    spec: PanelSpec
    comparison: ComparisonGroup = ComparisonGroup.NEVER_TREATED
    name: str = "did_single_cohort_multi_period"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ATT})

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        s = self.spec
        if estimand.type is not EstimandType.ATT:
            raise ValueError("DiD identifies the ATT")
        if estimand.outcome != s.outcome:
            raise ValueError("estimand outcome differs from the panel outcome column")
        result, timing = validate_panel(data, s)
        if result.is_blocking or timing is None:
            raise ValueError(f"panel timing is invalid: {sorted(result.codes())}")
        if not timing.balanced or data[s.outcome].isna().any():
            raise ValueError("the multi-period baseline needs a balanced panel without gaps")
        if timing.n_always_treated:
            raise ValueError("always-treated units have no pre-period; remove them explicitly")
        if len(timing.cohorts) != 1:
            raise ValueError(
                f"{len(timing.cohorts)} adoption cohorts found: staggered adoption is not "
                "supported by this baseline (use the group-time ATT estimator)"
            )
        (start,) = timing.cohorts
        last = max(timing.periods)
        unit_start = data.groupby(s.unit)[s.treatment_start].first()
        treated_units = unit_start.index[unit_start == start]
        never = unit_start.index[unit_start.isna()]
        after = unit_start.index[unit_start > last]
        control_units = (
            never if self.comparison is ComparisonGroup.NEVER_TREATED else never.union(after)
        )
        if len(treated_units) < 2 or len(control_units) < 2:
            raise ValueError("need at least two treated and two comparison units")

        is_post = data[s.period] >= start
        unit_means = data.assign(_post=is_post).groupby([s.unit, "_post"])[s.outcome].mean()
        wide = unit_means.unstack("_post")  # noqa: PD010 - unique (unit, post) keys
        diff = wide[True] - wide[False]
        d_t, d_c = diff.loc[treated_units].to_numpy(), diff.loc[control_units].to_numpy()

        effect = float(d_t.mean() - d_c.mean())
        v_t, v_c = d_t.var(ddof=1) / d_t.size, d_c.var(ddof=1) / d_c.size
        se = math.sqrt(v_t + v_c)
        df = (v_t + v_c) ** 2 / (v_t**2 / (d_t.size - 1) + v_c**2 / (d_c.size - 1))
        crit = float(stats.t.ppf(0.5 + confidence_level / 2, df))
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=effect,
            std_error=se,
            ci_lower=effect - crit * se,
            ci_upper=effect + crit * se,
            confidence_level=confidence_level,
            inference_method="unit_level_welch_t (clustered on unit)",
            p_value=float(2 * stats.t.sf(abs(effect) / se, df)),
            degrees_of_freedom=float(df),
            n_units=int(d_t.size + d_c.size),
            n_treated=int(d_t.size),
            n_control=int(d_c.size),
            details={
                "treatment_start": start,
                "periods": list(timing.periods),
                "n_pre_periods": sum(p < start for p in timing.periods),
                "n_post_periods": sum(p >= start for p in timing.periods),
                "comparison_group": self.comparison.value,
                "n_excluded_start_after_window": len(after)
                if self.comparison is ComparisonGroup.NEVER_TREATED
                else 0,
                "aggregation": "ATT averaged over post periods, equal weight per period",
                "identifying_assumptions": ["parallel_trends", "no_anticipation"],
            },
        )
