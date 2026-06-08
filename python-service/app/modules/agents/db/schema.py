"""
QuestDB schema for the multi-agent pipeline output tables.

  agent_run_log       — one row per agent LLM call (provider-agnostic audit)
  daily_briefs        — SynthesisAgent output, one row per day
  agent_trade_params  — StrategyAgent output, one row per flagged signal
"""
import os
import requests


def create_agent_tables() -> None:
    host = os.getenv("QUESTDB_HOST", "questdb")
    base = f"http://{host}:9000"

    tables = [
        """
        CREATE TABLE IF NOT EXISTS agent_run_log (
            run_at        TIMESTAMP,
            flow_run_id   STRING,
            agent_name    SYMBOL,
            symbol        SYMBOL,
            model_alias   SYMBOL,
            provider      SYMBOL,
            model_id      SYMBOL,
            input_tokens  INT,
            output_tokens INT,
            cost_usd      DOUBLE,
            latency_ms    INT,
            status        SYMBOL,
            error_msg     STRING
        ) TIMESTAMP(run_at) PARTITION BY MONTH;
        """,
        """
        CREATE TABLE IF NOT EXISTS daily_briefs (
            brief_at          TIMESTAMP,
            target_date       DATE,
            regime_summary    STRING,
            top_setups_json   STRING,
            macro_risks_json  STRING,
            daily_narrative   STRING,
            provider          SYMBOL,
            model_id          SYMBOL,
            cost_usd          DOUBLE
        ) TIMESTAMP(brief_at) PARTITION BY MONTH;
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_trade_params (
            generated_at     TIMESTAMP,
            signal_id        STRING,
            symbol           SYMBOL,
            direction        SYMBOL,
            conviction_score DOUBLE,
            params_json      STRING,
            provider         SYMBOL,
            model_id         SYMBOL
        ) TIMESTAMP(generated_at) PARTITION BY MONTH;
        """,
    ]

    for ddl in tables:
        resp = requests.get(base + "/exec", params={"query": ddl.strip()}, timeout=10)
        resp.raise_for_status()
