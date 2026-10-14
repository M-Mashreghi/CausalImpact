"""Two-period (2x2) difference-in-differences (Task 4.2).

Target: the ATT in the post period for units that start treatment in the post period,
identified under parallel trends and no anticipation (assumptions, not facts).

    DiD = (Y_T,post - Y_T,pre) - (Y_C,post - Y_C,pre)

computed as the difference in mean unit-level first differences. Inference uses the
Welch/Neyman variance of those first differences, which is equivalent to clustering on
the unit. The four group-period means are returned as descriptive components.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
from scipy import stats

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.panel.contract import PanelSpec, validate_panel


@dataclass(frozen=True)
class TwoPeriodDiD:
    spec: PanelSpec
    pre_period: int
    post_period: int
    name: str = "did_2x2"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ATT})

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        if self.post_period <= self.pre_period:
            raise ValueError("post_period must come after pre_period")
        if estimand.type is not EstimandType.ATT:
            raise ValueError("2x2 DiD identifies the ATT")
        if estimand.outcome != self.spec.outcome:
            raise ValueError("estimand outcome differs from the panel outcome column")
        s = self.spec
        window = data[data[s.period].isin([self.pre_period, self.post_period])]
        result, _ = validate_panel(window, s)
        if result.is_blocking:
            raise ValueError(f"panel timing is invalid: {sorted(result.codes())}")
        starts = window.groupby(s.unit)[s.treatment_start].first()
        if (starts <= self.pre_period).any():
            raise ValueError(
                "units treated at or before the pre period break the 2x2 design; restrict "
                "the sample explicitly before estimation"
            )
        # pivot (not pivot_table): duplicates must fail loudly, never be averaged.
        wide = window.pivot(index=s.unit, columns=s.period, values=s.outcome)  # noqa: PD010
        if wide.isna().any().any():
            raise ValueError("2x2 DiD needs an outcome for every unit in both periods")
        delta = wide[self.post_period] - wide[self.pre_period]
        treated = (starts == self.post_period).reindex(delta.index).to_numpy()
        not_yet = int((starts > self.post_period).sum())
        d_t, d_c = delta.to_numpy()[treated], delta.to_numpy()[~treated]
        if d_t.size < 2 or d_c.size < 2:
            raise ValueError("need at least two treated and two comparison units")

        effect = float(d_t.mean() - d_c.mean())
        v_t, v_c = d_t.var(ddof=1) / d_t.size, d_c.var(ddof=1) / d_c.size
        se = math.sqrt(v_t + v_c)
        df = (v_t + v_c) ** 2 / (v_t**2 / (d_t.size - 1) + v_c**2 / (d_c.size - 1))
        crit = float(stats.t.ppf(0.5 + confidence_level / 2, df))

        def mean(group: pd.Index, period: int) -> float:
            return float(wide.loc[group, period].mean())

        idx_t, idx_c = delta.index[treated], delta.index[~treated]
        components = {
            "treated_pre": mean(idx_t, self.pre_period),
            "treated_post": mean(idx_t, self.post_period),
            "comparison_pre": mean(idx_c, self.pre_period),
            "comparison_post": mean(idx_c, self.post_period),
        }
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=effect,
            std_error=se,
            ci_lower=effect - crit * se,
            ci_upper=effect + crit * se,
            confidence_level=confidence_level,
            inference_method="unit_first_difference_welch_t (clustered on unit)",
            p_value=float(2 * stats.t.sf(abs(effect) / se, df)),
            degrees_of_freedom=float(df),
            n_units=int(delta.size),
            n_treated=int(d_t.size),
            n_control=int(d_c.size),
            details={
                "pre_period": self.pre_period,
                "post_period": self.post_period,
                "group_period_means": components,
                "comparison_group": "never treated and not-yet-treated units",
                "n_not_yet_treated_in_comparison": not_yet,
                "identifying_assumptions": ["parallel_trends", "no_anticipation"],
            },
        )
