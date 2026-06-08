"""
Prefect flow — Archive / Historian Pipeline

Schedule: weekly, Sunday 00:00 ET
Triggered also on milestone commits (new agent shipped, first real-data run, etc.)

Runs the archive_node: git log + WORKLOG → milestones, glossary update, technical
explainer, performance summary → QuestDB tables → served by GET /api/v1/archive/
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from prefect import flow, get_run_logger, task

log = logging.getLogger(__name__)


@task(name="run_archive_graph", retries=1, retry_delay_seconds=300)
def run_archive_graph_task(
    last_archive_date: str,
    model_aliases: dict,
    dry_run: bool,
) -> dict:
    from langchain_core.runnables import RunnableConfig
    from app.modules.agents.archive.archive_graph import build_archive_graph, make_archive_initial_state
    from app.modules.llm.qdb_callback import QDBCostCallback

    logger = get_run_logger()
    logger.info("archive_graph: since=%s dry_run=%s", last_archive_date, dry_run)

    graph = build_archive_graph()
    state = make_archive_initial_state(
        last_archive_date=last_archive_date,
        model_aliases=model_aliases,
        dry_run=dry_run,
    )
    config = RunnableConfig(
        callbacks=[QDBCostCallback(agent_name="archive_graph")],
    )
    result = graph.invoke(state, config=config)

    report = result.get("archive_report") or {}
    logger.info(
        "archive_graph complete: %d milestones, %d glossary updates, %d explainers",
        len(report.get("milestones", [])),
        len(report.get("glossary_updates", [])),
        len(report.get("technical_explainers", [])),
    )
    for err in result.get("errors", []):
        logger.warning("archive error: %s", err)

    return result


@flow(
    name="archive_pipeline",
    description="Weekly archive: git log → milestones, glossary, technical explainers",
    log_prints=True,
)
def archive_flow(
    last_archive_date: str | None = None,
    model_aliases: dict | None = None,
    dry_run: bool = False,
) -> dict:
    since   = last_archive_date or str(date.today() - timedelta(weeks=1))
    aliases = model_aliases or {}

    result = run_archive_graph_task(
        last_archive_date=since,
        model_aliases=aliases,
        dry_run=dry_run,
    )
    return {
        "since":   since,
        "report":  result.get("archive_report"),
        "errors":  result.get("errors", []),
    }


if __name__ == "__main__":
    archive_flow()
