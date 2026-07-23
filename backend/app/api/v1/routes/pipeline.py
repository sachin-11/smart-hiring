import json
import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.orchestrator import get_compiled_graph, initial_state
from app.schemas.pipeline import PipelineRunRequest
from app.services import llm_router
from app.services.mlops import experiment_tracker
from app.services.monitoring import hiring_pipeline_duration_seconds

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/run")
async def run_pipeline(payload: PipelineRunRequest) -> StreamingResponse:
    async def event_stream():
        started_at = time.time()
        graph = get_compiled_graph()
        state = dict(initial_state(payload.candidate_id, payload.job_id))

        try:
            async for event in graph.astream(state):
                for node_name, partial_update in event.items():
                    state.update(partial_update)
                    yield _sse_event({"step": node_name, "state": state})
        except Exception as exc:
            logger.exception("Pipeline stream failed for candidate=%s job=%s", payload.candidate_id, payload.job_id)
            yield _sse_event({"step": "error_handler", "state": {**state, "errors": [*state["errors"], str(exc)]}})

        duration = time.time() - started_at
        hiring_pipeline_duration_seconds.observe(duration)

        try:
            token_costs = await llm_router.get_recent_costs_by_model(started_at)
            match_score = state.get("match_score")
            await experiment_tracker.log_pipeline_run(
                payload.candidate_id, payload.job_id, match_score * 100 if match_score else None, token_costs
            )
        except Exception:
            logger.exception("Failed to log pipeline run to MLflow")

        yield _sse_event({"step": "__end__", "state": state})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
