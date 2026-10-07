# Python SDK Code Samples

Code examples for the `snowpipe-streaming` Python SDK (High-Performance Architecture).

**Install**: `pip install snowpipe-streaming`

---

## Minimal Example

```python
import json
from snowflake.ingest.streaming import StreamingIngestClient

profile = {
    "account": "myorg-myaccount",
    "user": "STREAMING_USER",
    "url": "https://myorg-myaccount.snowflakecomputing.com:443",
    "private_key": open("keys/rsa_key.p8").read(),
}

with open("/tmp/profile.json", "w") as f:
    json.dump(profile, f)

client = StreamingIngestClient(
    client_name="my_client",
    db_name="MY_DATABASE",
    schema_name="MY_SCHEMA",
    pipe_name="MY_TABLE-STREAMING",
    profile_json="/tmp/profile.json",
)

channel, status = client.open_channel(channel_name="channel_1")

channel.append_row(
    {"col1": "hello", "col2": 42, "col3": {"nested": "data"}},
    offset_token="1",
)

channel.wait_for_flush(timeout_seconds=30)
client.close()
```

---

## Production Service with Self-Healing Channels

Production-ready streaming service pattern:

```python
import json
import logging
import threading
from typing import List, Dict, Optional, Set

logger = logging.getLogger(__name__)
MAX_RECOVERY_ATTEMPTS = 3

class StreamingService:
    def __init__(self, account, user, private_key_path, database, schema, table,
                 partition_count=4, instance_id="default"):
        self.account = account
        self.user = user
        self.private_key_path = private_key_path
        self.database = database
        self.schema = schema
        self.table = table
        self.pipe_name = f"{table}-STREAMING"
        self.partition_count = partition_count
        self.instance_id = instance_id
        self.client = None
        self.channels: List = []
        self._lock = threading.Lock()
        self._recovering: Set[int] = set()

    def initialize(self):
        from snowflake.ingest.streaming import StreamingIngestClient

        with open(self.private_key_path, "r") as f:
            private_key = f.read()

        profile = {
            "account": self.account,
            "user": self.user,
            "url": f"https://{self.account}.snowflakecomputing.com:443",
            "private_key": private_key,
        }

        profile_path = f"/tmp/profile_{self.instance_id}.json"
        with open(profile_path, "w") as f:
            json.dump(profile, f)

        self.client = StreamingIngestClient(
            client_name=f"client_{self.instance_id}",
            db_name=self.database,
            schema_name=self.schema,
            pipe_name=self.pipe_name,
            profile_json=profile_path,
        )

        self.channels = []
        for i in range(self.partition_count):
            ch, _ = self.client.open_channel(f"{self.instance_id}_p{i}")
            self.channels.append(ch)

        logger.info(f"Initialized with {len(self.channels)} channels")

    def _hash_to_partition(self, key: str) -> int:
        h = 0
        for c in key:
            h = ((h << 5) - h) + ord(c)
        return abs(h) % self.partition_count

    def _is_recoverable(self, error: Exception) -> bool:
        err = str(error).lower()
        return any(k in err for k in [
            "token has expired", "invalid state",
            "invalidchannelerror", "unauthorized",
        ])

    def _recover_channel(self, partition_id: int) -> bool:
        with self._lock:
            if partition_id in self._recovering:
                return False
            self._recovering.add(partition_id)
        try:
            try:
                self.channels[partition_id].close()
            except Exception:
                pass
            ch, _ = self.client.open_channel(f"{self.instance_id}_p{partition_id}")
            self.channels[partition_id] = ch
            return True
        except Exception as e:
            logger.error(f"Recovery failed for partition {partition_id}: {e}")
            return False
        finally:
            with self._lock:
                self._recovering.discard(partition_id)

    def stream_row(self, row: Dict, partition_key: str) -> bool:
        partition = self._hash_to_partition(partition_key)
        for attempt in range(MAX_RECOVERY_ATTEMPTS):
            try:
                self.channels[partition].append_row(row)
                return True
            except Exception as e:
                if self._is_recoverable(e) and attempt < MAX_RECOVERY_ATTEMPTS - 1:
                    if self._recover_channel(partition):
                        continue
                raise
        return False

    def stream_batch(self, rows: List[Dict], partition_key: str) -> int:
        partition = self._hash_to_partition(partition_key)
        for attempt in range(MAX_RECOVERY_ATTEMPTS):
            try:
                self.channels[partition].append_rows(rows)
                return len(rows)
            except Exception as e:
                if self._is_recoverable(e) and attempt < MAX_RECOVERY_ATTEMPTS - 1:
                    if self._recover_channel(partition):
                        continue
                raise
        return 0

    def flush_and_wait(self, timeout_seconds=30):
        self.client.wait_for_flush(timeout_seconds=timeout_seconds)

    def shutdown(self):
        for ch in self.channels:
            try:
                ch.close()
            except Exception:
                pass
        if self.client:
            self.client.close()
```

---

## FastAPI Integration

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

service = StreamingService(
    account="myorg-myaccount",
    user="STREAMING_USER",
    private_key_path="keys/rsa_key.p8",
    database="MY_DB",
    schema="MY_SCHEMA",
    table="MY_TABLE",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    service.initialize()
    yield
    service.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/ingest")
async def ingest(event: dict):
    service.stream_row(event, partition_key=event.get("tenant_id", "default"))
    return {"status": "ok"}

@app.post("/ingest/batch")
async def ingest_batch(events: list[dict]):
    count = 0
    for event in events:
        service.stream_row(event, partition_key=event.get("tenant_id", "default"))
        count += 1
    return {"status": "ok", "count": count}
```

---

## Offset Token Tracking

```python
channel, status = client.open_channel("my_channel")

for i, record in enumerate(records):
    channel.append_row(record, offset_token=str(i))

token = channel.get_latest_committed_offset_token()
print(f"Committed up to offset: {token}")

channel.wait_for_commit(
    token_checker=lambda t: t is not None and int(t) >= len(records) - 1,
    timeout_seconds=60,
)
```

---

## Channel Status Monitoring

```python
status = channel.get_channel_status()
print(f"Status code: {status.status_code}")
print(f"Row error count: {status.row_error_count}")
print(f"Last committed offset: {status.last_committed_offset_token}")

statuses = client.get_channel_statuses(["ch1", "ch2", "ch3"])
for name, s in statuses.items():
    print(f"{name}: {s.status_code}, errors={s.row_error_count}")
```

---

## Circuit Breaker Pattern

Prevents thundering herd when Snowflake is under pressure. Opens circuit after repeated failures, allows periodic probes to check recovery.

```python
import time
import random
import logging
from enum import Enum
from threading import Lock

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
            return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.OPEN:
            return False
        if state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
            return False
        return False

    def record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit breaker CLOSED (recovered)")
            self._failure_count = 0

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker OPEN (half-open probe failed)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")


class ResilientStreamingService:
    """Streaming service with circuit breaker and exponential backoff."""
    
    def __init__(self, streaming_service, circuit_breaker: CircuitBreaker = None):
        self.service = streaming_service
        self.circuit = circuit_breaker or CircuitBreaker()
        self.base_delay = 0.1
        self.max_delay = 10.0
        self.max_retries = 5

    def _backoff_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.1)
        return min(delay + jitter, self.max_delay)

    def stream_row(self, row: dict, partition_key: str) -> bool:
        if not self.circuit.allow_request():
            logger.warning("Circuit open, rejecting request")
            raise CircuitOpenError("Circuit breaker is open")
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = self.service.stream_row(row, partition_key)
                self.circuit.record_success()
                return result
            except Exception as e:
                last_error = e
                self.circuit.record_failure()
                
                if not self.circuit.allow_request():
                    raise CircuitOpenError("Circuit opened during retries") from e
                
                delay = self._backoff_delay(attempt)
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}")
                time.sleep(delay)
        
        raise last_error


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass
```

Usage:

```python
service = StreamingService(...)
service.initialize()

resilient = ResilientStreamingService(service, CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30.0,
))

try:
    resilient.stream_row({"col1": "value"}, partition_key="tenant_1")
except CircuitOpenError:
    return 503  # Service unavailable
```
