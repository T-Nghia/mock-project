"""Real prefork Celery with a test-only embedding barrier; no live AI calls."""

import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from sqlalchemy.engine import make_url


def main():
    if os.environ.get("RELIABILITY_FAULT_PROCESS") != "1" or not re.fullmatch(
        r"-csearch_path=cleanup_reliability_[0-9a-f]{32},public",
        make_url(os.environ["DATABASE_URL"]).query.get("options", ""),
    ):
        raise SystemExit("Isolated M2 test schema required")
    from celery import current_task, signals
    from app.services import document_service
    from app.worker import celery_app

    directory, queue = Path(sys.argv[1]), sys.argv[2]

    def record(name, values):
        path = directory / (name + "-" + uuid.uuid4().hex + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values))
        temporary.replace(path)

    class BarrierEmbeddingProvider:
        def embed_batch(self, texts, **_):
            record("embedding", {"pid": os.getpid(), "task_id": current_task.request.id})
            deadline = time.monotonic() + 60
            while not (directory / "release").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("M2 controlled embedding barrier timed out")
                time.sleep(0.05)
            return [[0.1] * 384 for _ in texts]

        def close(self):
            pass

    document_service.GeminiEmbeddingProvider = BarrierEmbeddingProvider
    document_service.generate_summary = lambda *_args, **_kwargs: "Test summary"
    document_service.generate_suggested_questions = lambda *_args, **_kwargs: []

    @signals.worker_ready.connect(weak=False)
    def ready(**_):
        record("ready", {"pid": os.getpid()})

    @signals.task_prerun.connect(weak=False)
    def delivery(task_id=None, task=None, **_):
        if task.name == "documents.process":
            record("delivery", {"task_id": task_id, "pid": os.getpid(),
                                "redelivered": bool(task.request.delivery_info.get("redelivered"))})

    @signals.task_postrun.connect(weak=False)
    def complete(task_id=None, task=None, retval=None, state=None, **_):
        if task.name == "documents.process":
            record("complete", {"task_id": task_id, "outcome": retval, "state": state})

    celery_app.worker_main([
        "worker", "--pool=prefork", "--concurrency=1", "--loglevel=WARNING",
        "--without-gossip", "--without-mingle", "--without-heartbeat", "--queues=" + queue,
    ])


if __name__ == "__main__":
    main()
