"""Standard IR metrics + a reproducible bootstrap confidence interval."""
from __future__ import annotations

import numpy as np


def precision_at_k(ranked: list[int], relevant: set[int], k: int) -> float:
    return sum(1 for r in ranked[:k] if r in relevant) / k if k else 0.0


def recall_at_k(ranked: list[int], relevant: set[int], k: int) -> float:
    return sum(1 for r in ranked[:k] if r in relevant) / len(relevant) if relevant else 0.0


def reciprocal_rank(ranked: list[int], relevant: set[int]) -> float:
    for i, r in enumerate(ranked, 1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def hit_at_k(ranked: list[int], relevant: set[int], k: int) -> float:
    return 1.0 if any(r in relevant for r in ranked[:k]) else 0.0


def bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 13, alpha: float = 0.05):
    if not values:
        return (None, None)
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    return (round(float(np.percentile(means, 100 * alpha / 2)), 4), round(float(np.percentile(means, 100 * (1 - alpha / 2))), 4))


def summarise(per_query: list[dict], ks: list[int]) -> dict:
    out = {"n_queries": len(per_query)}
    for k in ks:
        for m in ("precision", "recall", "hit"):
            vals = [q[f"{m}@{k}"] for q in per_query]
            out[f"{m}@{k}"] = round(float(np.mean(vals)), 4) if vals else None
    rr = [q["rr"] for q in per_query]
    out["mrr"] = round(float(np.mean(rr)), 4) if rr else None
    out["mrr_ci95"] = bootstrap_ci(rr)
    k5 = [q.get("precision@5", 0) for q in per_query]
    out["precision@5_ci95"] = bootstrap_ci(k5) if 5 in ks else None
    return out
