import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import get_db_context
from app.services import slack_service
from app.services.mlops import drift_detector, llm_judge_evaluator, ragas_evaluator

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _alert_slack(text: str) -> None:
    try:
        await slack_service.send_slack_alert(text)
    except slack_service.SlackNotConfiguredError:
        logger.info("MLOps alert (Slack not configured, logging instead): %s", text)
    except Exception:
        logger.exception("Failed to deliver MLOps alert to Slack")


async def run_scheduled_mlops_checks() -> None:
    """Runs the same RAGAS eval + drift check the /analytics page's "Run" buttons
    trigger manually, on a recurring schedule, and pushes a Slack alert for any
    threshold breach. One failing check must not block the other."""
    logger.info("Running scheduled MLOps checks")

    async with get_db_context() as db:
        try:
            ragas_summary = await ragas_evaluator.run_evaluation(
                db, sample_size=settings.MLOPS_SCHEDULE_RAGAS_SAMPLE_SIZE
            )
            if ragas_summary.get("alert_triggered"):
                await _alert_slack(
                    f":warning: Scheduled RAGAS eval: avg faithfulness "
                    f"{ragas_summary['avg_faithfulness']:.2f} is below the "
                    f"{ragas_evaluator.FAITHFULNESS_ALERT_THRESHOLD} threshold "
                    f"({ragas_summary['sample_size']} samples)."
                )
        except ValueError as exc:
            # Not enough eval data yet — expected in a fresh/low-traffic environment.
            logger.info("Skipped scheduled RAGAS eval: %s", exc)
        except Exception:
            logger.exception("Scheduled RAGAS eval failed")

    async with get_db_context() as db:
        try:
            drift_report = await drift_detector.run_drift_check(db)
            if drift_report["alert_triggered"]:
                await _alert_slack(
                    f":warning: Scheduled embedding drift check: PSI="
                    f"{drift_report['psi_score']:.3f} exceeds the "
                    f"{drift_report['psi_threshold']} threshold "
                    f"(baseline={drift_report['baseline_size']}, current={drift_report['current_size']})."
                )
        except ValueError as exc:
            logger.info("Skipped scheduled drift check: %s", exc)
        except Exception:
            logger.exception("Scheduled drift check failed")

    async with get_db_context() as db:
        try:
            judge_summary = await llm_judge_evaluator.run_evaluation(
                db, sample_size=settings.MLOPS_SCHEDULE_RAGAS_SAMPLE_SIZE
            )
            if judge_summary.get("alert_triggered"):
                await _alert_slack(
                    f":warning: Scheduled LLM-judge eval: agreement rate "
                    f"{judge_summary['agreement_rate']:.0%} with the live scoring model is below "
                    f"threshold ({judge_summary['sample_size']} samples, avg score diff "
                    f"{judge_summary['avg_absolute_score_diff']:.2f})."
                )
        except ValueError as exc:
            logger.info("Skipped scheduled LLM-judge eval: %s", exc)
        except Exception:
            logger.exception("Scheduled LLM-judge eval failed")


def start_scheduler() -> None:
    global _scheduler
    if not settings.MLOPS_SCHEDULE_ENABLED:
        logger.info("MLOps scheduled checks disabled (MLOPS_SCHEDULE_ENABLED=false)")
        return

    _scheduler = AsyncIOScheduler()
    # First run fires shortly after startup, then every MLOPS_SCHEDULE_INTERVAL_HOURS —
    # APScheduler's default for a fresh interval trigger with no start_date.
    _scheduler.add_job(
        run_scheduled_mlops_checks,
        trigger="interval",
        hours=settings.MLOPS_SCHEDULE_INTERVAL_HOURS,
        id="mlops_checks",
    )
    _scheduler.start()
    logger.info("MLOps scheduled checks enabled: every %sh", settings.MLOPS_SCHEDULE_INTERVAL_HOURS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
