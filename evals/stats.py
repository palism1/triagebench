# FILE MAP
#   12-30  bootstrap_ci: seeded percentile bootstrap over issues for any metric
#
# Purpose: every headline number in a report carries a 95% interval. Resampling is per issue,
# so an interval reflects how much the number would move on a different sample of issues.

from __future__ import annotations

import random
from collections.abc import Callable


def bootstrap_ci(
    rows: list, metric: Callable[[list], float], n: int = 1000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float]:
    if not rows:
        return (0.0, 0.0)
    rng = random.Random(seed)
    stats = sorted(metric([rows[rng.randrange(len(rows))] for _ in rows]) for _ in range(n))
    lo = stats[int(alpha / 2 * n)]
    hi = stats[min(n - 1, int((1 - alpha / 2) * n))]
    return (lo, hi)
