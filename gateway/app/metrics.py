from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ResultWriter:
    def __init__(self, s3_client, bucket: str, run_id: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._run_id = run_id

    def write(self, event: dict[str, Any]) -> None:
        if not self._bucket:
            logger.info("result %s", json.dumps(event, default=str))
            return
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"results/{self._run_id}/{day}/{uuid.uuid4()}.jsonl"
        body = json.dumps(event, default=str) + "\n"
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/jsonl",
        )
