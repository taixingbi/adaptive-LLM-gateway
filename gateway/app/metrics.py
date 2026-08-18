from __future__ import annotations

import atexit
import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ResultWriter:
    """Enqueue JSONL off the request path; a worker flushes batches to S3."""

    def __init__(self, s3_client, bucket: str, run_id: str, flush_every: int = 25) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._run_id = run_id
        self._flush_every = flush_every
        self._q: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        if bucket:
            self._thread = threading.Thread(target=self._run, name="s3-results", daemon=True)
            self._thread.start()
            atexit.register(self.flush)

    def write(self, event: dict[str, Any]) -> None:
        if not self._bucket:
            logger.info("result %s", json.dumps(event, default=str, separators=(",", ":")))
            return
        self._q.put(event)

    def flush(self) -> None:
        if not self._thread:
            return
        self._q.put(None)
        self._thread.join(timeout=5)

    def _run(self) -> None:
        buf: list[str] = []
        while True:
            try:
                item = self._q.get(timeout=1.0)
            except queue.Empty:
                if buf:
                    self._put(buf)
                    buf = []
                continue
            if item is None:
                if buf:
                    self._put(buf)
                return
            buf.append(json.dumps(item, default=str, separators=(",", ":")))
            if len(buf) >= self._flush_every:
                self._put(buf)
                buf = []

    def _put(self, lines: list[str]) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"results/{self._run_id}/{day}/{uuid.uuid4()}.jsonl"
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=("\n".join(lines) + "\n").encode("utf-8"),
                ContentType="application/jsonl",
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to write %s result lines to s3", len(lines))
