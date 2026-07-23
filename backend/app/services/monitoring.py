from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

hiring_pipeline_duration_seconds = Histogram(
    "hiring_pipeline_duration_seconds",
    "Duration of a full hiring pipeline run (parse -> match -> questions/report)",
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300),
)

llm_token_usage_total = Counter(
    "llm_token_usage_total",
    "Total LLM tokens consumed",
    ["model", "agent", "token_type"],
)

match_score_distribution = Histogram(
    "match_score_distribution",
    "Distribution of candidate-job match scores (0-100 scale)",
    buckets=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
)

api_request_total = Counter(
    "api_request_total",
    "Total API requests",
    ["endpoint", "status"],
)


def get_metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records api_request_total for every request. The route's path template
    (not the raw URL) is used as the label so per-candidate/job/session UUIDs
    don't explode the metric's cardinality."""

    async def dispatch(self, request: Request, call_next):
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            endpoint = route.path if route is not None else request.url.path
            api_request_total.labels(endpoint=endpoint, status=str(status_code)).inc()
