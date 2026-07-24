from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Backed by Redis (same instance as everything else) so limits are shared across
# worker processes rather than each process tracking its own in-memory counters.
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
