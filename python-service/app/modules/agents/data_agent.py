"""
DataAgent — code-only agent (no LLM calls).

Queries QuestDB + signal_catalog, builds feature vectors for all signals
in the target date range, ranks by premium-weighted volume anomaly, and
clusters by (dte_bucket, otm_pct) fingerprint using HDBSCAN.

Output: SignalBatch — the input to MLAgent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from app.modules.agents.base_agent import AgentContext, BaseAgent

log = logging.getLogger(__name__)

MIN_PREMIUM = 50_000.0
MIN_VOLUME_RATIO = 3.0


@dataclass
class SignalBatch:
    signals: list[dict]
    feature_matrix: pd.DataFrame
    clusters: dict[str, list[str]]     # cluster_id → [signal_id, ...]
    ranked_ids: list[str]              # signal_id sorted by raw_score desc
    symbol: str
    date: str


class DataAgent(BaseAgent):
    name = "data"
    default_model_alias = "haiku"   # unused — no LLM calls

    def run(self, ctx: AgentContext, symbol: str, **_) -> dict:
        log.info("DataAgent: loading signals for %s on %s", symbol, ctx.target_date)

        df = self._load_features(symbol, ctx.target_date)
        if df.empty:
            log.info("DataAgent: no signals for %s on %s", symbol, ctx.target_date)
            return {"symbol": symbol, "count": 0, "batch": None}

        df = self._rank(df)
        clusters = self._cluster(df)

        batch = SignalBatch(
            signals=df.to_dict("records"),
            feature_matrix=df,
            clusters=clusters,
            ranked_ids=df["id"].astype(str).tolist(),
            symbol=symbol,
            date=ctx.target_date,
        )
        log.info("DataAgent: %d signals ranked for %s", len(df), symbol)
        return {"symbol": symbol, "count": len(df), "batch": batch}

    # ------------------------------------------------------------------

    def _load_features(self, symbol: str, target_date: str) -> pd.DataFrame:
        from app.modules.tos.ml.features.tos_feature_builder import load_training_data

        try:
            df = load_training_data(symbol=symbol, min_labeled_days=1, min_rows=1)
            # filter to target date ± 1 day (some signals detected late session)
            df = df[df["detected_at"].dt.date.astype(str) == target_date]
        except ValueError as exc:
            log.warning("DataAgent load_training_data: %s", exc)
            df = pd.DataFrame()

        # Apply baseline filters
        if not df.empty:
            df = df[
                (df["volume_ratio_20d"] >= MIN_VOLUME_RATIO) &
                (df["premium_total"] >= MIN_PREMIUM)
            ]

        return df.reset_index(drop=True)

    def _rank(self, df: pd.DataFrame) -> pd.DataFrame:
        import numpy as np
        # Composite rank: volume anomaly × premium size × (IV context boost)
        df["_raw_score"] = (
            df["volume_ratio_20d"].clip(upper=20)
            * np.log1p(df["premium_total"])
            * (1 + df.get("iv_rank", pd.Series(50.0, index=df.index)) / 100)
        )
        return df.sort_values("_raw_score", ascending=False).reset_index(drop=True)

    def _cluster(self, df: pd.DataFrame) -> dict[str, list[str]]:
        """Group by (dte_bucket, otm_pct quintile) — lightweight fingerprinting."""
        if df.empty:
            return {}
        clusters: dict[str, list[str]] = {}
        df["_otm_q"] = pd.qcut(df["otm_pct"].fillna(0), q=5, labels=False, duplicates="drop")
        for _, row in df.iterrows():
            key = f"dte{row.get('dte_bucket', 0)}_otm{row.get('_otm_q', 0)}"
            clusters.setdefault(key, []).append(str(row["id"]))
        return clusters
