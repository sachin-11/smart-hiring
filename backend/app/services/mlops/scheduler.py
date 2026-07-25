import logging
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import get_db_context
from app.core.redis_client import get_redis_client
from app.services import slack_service
from app.services.mlops import drift_detector, llm_judge_evaluator, ragas_evaluator

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Every horizontally-scaled replica runs its own APScheduler instance (there's
# no shared job store), so without this lock N replicas would each run — and
# Slack-alert — the same scheduled check N times. A short-lived Redis lock
# (SET NX + TTL) ensures only whichever replica's tick wins the race actually
# runs it; the rest see the lock held and skip that tick.
_LOCK_KEY = "mlops:scheduler:leader_lock"
_LOCK_TTL_SECONDS = 20 * 60  # comfortably longer than a full ragas+drift+judge run
_RELEASE_IF_OWNER_SCRIPT = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


async def _try_acquire_leader_lock() -> str | None:
    redis = get_redis_client()
    token = uuid.uuid4().hex
    try:
        acquired = await redis.set(_LOCK_KEY, token, nx=True, ex=_LOCK_TTL_SECONDS)
        return token if acquired else None
    except Exception:
        logger.warning("Failed to acquire MLOps scheduler leader lock (Redis unavailable?)", exc_info=True)
        return None
    finally:
        await redis.aclose()


async def _release_leader_lock(token: str) -> None:
    """Atomically deletes the lock only if we still hold it (token matches) —
    otherwise a run that outlasts the TTL could release a lock a DIFFERENT
    replica has since legitimately acquired."""
    redis = get_redis_client()
    try:
        await redis.eval(_RELEASE_IF_OWNER_SCRIPT, 1, _LOCK_KEY, token)
    except Exception:
        logger.warning("Failed to release MLOps scheduler leader lock", exc_info=True)
    finally:
        await redis.aclose()


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
    lock_token = await _try_acquire_leader_lock()
    if lock_token is None:
        logger.info("MLOps scheduled checks: another replica holds the leader lock, skipping this tick")
        return

    try:
        await _run_mlops_checks_locked()
    finally:
        await _release_leader_lock(lock_token)


async def _run_mlops_checks_locked() -> None:
    logger.info("Running scheduled MLOps checks (leader lock held)")

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
