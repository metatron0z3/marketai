"""
SynthesisAgent — 1 LLM call per day (full-tier model).

Aggregates all TradeParams + ResearchContext into a cross-symbol daily brief:
  - regime summary (market state)
  - top 3 setups with key risks
  - macro risk flags (GLD/TLT/SPY unusual volume)
  - sector rotation note
  - 2-3 sentence daily narrative

Output: DailyBrief dict written to daily_briefs table.
"""
from __future__ import annotations

import json
import logging
import os

from app.modules.agents.base_agent import AgentContext, BaseAgent

log = logging.getLogger(__name__)


class SynthesisAgent(BaseAgent):
    name = "synthesis"
    default_model_alias = "sonnet"

    def run(
        self,
        ctx: AgentContext,
        trade_params_list: list[dict],
        research_context: dict,
        **_,
    ) -> dict:
        log.info(
            "SynthesisAgent: synthesising %d trade setups for %s",
            len(trade_params_list), ctx.target_date
        )

        if not trade_params_list:
            brief = self._empty_brief(ctx.target_date)
            self._persist(brief, ctx.target_date)
            return {"brief": brief}

        system = (
            "You are a senior options strategist writing the morning brief for a systematic "
            "trading desk. Return ONLY valid JSON — no markdown, no commentary."
        )

        user = (
            f"Date: {ctx.target_date}\n\n"
            f"Research context:\n{json.dumps(research_context, indent=2)}\n\n"
            f"Trade setups generated today ({len(trade_params_list)} total):\n"
            f"{json.dumps(trade_params_list, indent=2)}\n\n"
            "Produce a DailyBrief JSON with these exact keys:\n"
            "{\n"
            '  "regime_summary": "",\n'
            '  "top_3_setups": [\n'
            '    {"ticker":"","direction":"","thesis":"","key_risk":""}\n'
            "  ],\n"
            '  "macro_risk_flags": [""],\n'
            '  "sector_rotation": "",\n'
            '  "daily_narrative": "2-3 sentences a trader reads first thing"\n'
            "}"
        )

        try:
            raw = self._llm(
                messages=[{"role": "user", "content": user}],
                system=system,
                max_tokens=800,
            )
            brief = self._parse_json(raw)
        except Exception as exc:
            log.warning("SynthesisAgent LLM call failed: %s", exc)
            brief = self._fallback_brief(ctx.target_date, trade_params_list, research_context)

        brief["target_date"] = ctx.target_date
        self._persist(brief, ctx.target_date)

        log.info(
            "SynthesisAgent: brief written for %s — regime=%r",
            ctx.target_date, brief.get("regime_summary", "")[:60]
        )
        return {"brief": brief}

    # ------------------------------------------------------------------

    def _persist(self, brief: dict, target_date: str) -> None:
        try:
            from questdb.ingress import Sender, TimestampNanos
            from app.modules.llm.model_registry import resolve_alias
            provider, model_id = resolve_alias(self.model_alias)
            conf = os.getenv("QDB_CLIENT_CONF", "http::addr=questdb:9000;")
            with Sender.from_conf(conf) as sender:
                sender.row(
                    "daily_briefs",
                    symbols={"provider": provider, "model_id": model_id},
                    columns={
                        "target_date":      target_date,
                        "regime_summary":   brief.get("regime_summary", ""),
                        "top_setups_json":  json.dumps(brief.get("top_3_setups", [])),
                        "macro_risks_json": json.dumps(brief.get("macro_risk_flags", [])),
                        "daily_narrative":  brief.get("daily_narrative", ""),
                    },
                    at=TimestampNanos.now(),
                )
                sender.flush()
        except Exception as exc:
            log.warning("daily_briefs write failed: %s", exc)

    @staticmethod
    def _empty_brief(target_date: str) -> dict:
        return {
            "target_date": target_date,
            "regime_summary": "No flagged signals today",
            "top_3_setups": [],
            "macro_risk_flags": [],
            "sector_rotation": "No rotation signal",
            "daily_narrative": "No high-conviction unusual options activity detected today.",
        }

    @staticmethod
    def _fallback_brief(target_date: str, trade_params: list, research: dict) -> dict:
        tickers = [p.get("trade_params", {}).get("ticker", "?") for p in trade_params[:3]]
        return {
            "target_date": target_date,
            "regime_summary": research.get("regime_note", "Unknown regime"),
            "top_3_setups": [
                {"ticker": t, "direction": "?", "thesis": "See trade params", "key_risk": "LLM synthesis failed"}
                for t in tickers
            ],
            "macro_risk_flags": [],
            "sector_rotation": research.get("dominant_theme", ""),
            "daily_narrative": (
                f"LLM synthesis failed — fallback summary for {target_date}. "
                f"{len(trade_params)} trade setups generated. "
                f"Dominant theme: {research.get('dominant_theme', 'N/A')}."
            ),
        }
