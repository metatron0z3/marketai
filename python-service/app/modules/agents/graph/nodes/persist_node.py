"""persist_node — writes all graph outputs to QuestDB via ILP."""
from __future__ import annotations

import logging
import os

from app.modules.agents.graph.state import GraphState

log = logging.getLogger(__name__)

QDB_CONF = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")


def _write_trade_params(trade_params: list[dict]) -> None:
    if not trade_params:
        return
    try:
        from questdb.ingress import Sender, TimestampNanos
        with Sender.from_conf(QDB_CONF) as sender:
            for tp in trade_params:
                if not tp:
                    continue
                ps = tp.get("position_sizing", {})
                sender.row(
                    "agent_trade_params",
                    symbols={
                        "ticker":    tp.get("ticker", ""),
                        "direction": tp.get("direction", ""),
                        "signal_id": tp.get("signal_id", ""),
                    },
                    columns={
                        "entry_condition":   tp.get("entry_condition", ""),
                        "strike_preference": tp.get("strike_preference", ""),
                        "dte_target":        tp.get("dte_target", ""),
                        "stop_loss":         tp.get("stop_loss", ""),
                        "profit_target":     tp.get("profit_target", ""),
                        "hedges":            tp.get("hedges", ""),
                        "rationale":         tp.get("rationale", ""),
                        "conviction_score":  float(tp.get("conviction_score", 0)),
                        "kelly_fraction":    float(ps.get("kelly_fraction", 0)),
                        "recommended_pct":   ps.get("recommended_pct", ""),
                        "max_contracts":     int(ps.get("max_contracts", 0)),
                    },
                    at=TimestampNanos.now(),
                )
            sender.flush()
        log.info("persist_node: wrote %d trade_params rows", len(trade_params))
    except Exception as exc:
        log.error("persist_node trade_params write failed: %s", exc)


def _write_daily_brief(brief: dict | None, target_date: str) -> None:
    if not brief:
        return
    try:
        from questdb.ingress import Sender, TimestampNanos
        with Sender.from_conf(QDB_CONF) as sender:
            sender.row(
                "agent_daily_briefs",
                symbols={"target_date": target_date},
                columns={
                    "regime_summary":   brief.get("regime_summary", ""),
                    "sector_rotation":  brief.get("sector_rotation", ""),
                    "daily_narrative":  brief.get("daily_narrative", ""),
                    "macro_risk_flags": str(brief.get("macro_risk_flags", [])),
                    "top_setups_json":  str(brief.get("top_3_setups", [])),
                },
                at=TimestampNanos.now(),
            )
            sender.flush()
        log.info("persist_node: wrote daily_brief for %s", target_date)
    except Exception as exc:
        log.error("persist_node daily_brief write failed: %s", exc)


def persist_node(state: GraphState) -> dict:
    _write_trade_params(state.get("trade_params") or [])
    _write_daily_brief(state.get("daily_brief"), state.get("target_date", ""))
    return {}
