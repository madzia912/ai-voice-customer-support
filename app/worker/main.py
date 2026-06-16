"""Worker entry point: consume jobs from RabbitMQ and run the pipeline.

Run with::

    python -m app.worker.main

Scale horizontally by starting more worker containers; each one consumes
independently from the durable work queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from pathlib import Path

import aio_pika
from pydantic import ValidationError

from ..config import get_settings
from ..llm import build_llm_service
from ..logging_config import configure_logging
from ..messaging import declare_topology, get_rabbitmq_client
from ..models import JobMessage
from ..tts import build_tts_service
from .handler import JobHandler

logger = logging.getLogger(__name__)


async def _consume(handler: JobHandler) -> None:
    settings = get_settings()
    client = get_rabbitmq_client()
    connection = await client.connect()

    channel = await connection.channel()
    await channel.set_qos(prefetch_count=settings.worker_prefetch)
    queue = await declare_topology(channel, settings)

    logger.info(
        "worker consuming",
        extra={"queue": settings.rabbitmq_job_queue, "prefetch": settings.worker_prefetch},
    )

    async with queue.iterator() as it:
        async for message in it:
            # ``requeue=False`` on failure routes the message to the DLQ via the DLX,
            # so we never spin forever on poisoned input.
            async with message.process(requeue=False, ignore_processed=True):
                try:
                    payload = json.loads(message.body.decode("utf-8"))
                    job_msg = JobMessage.model_validate(payload)
                except (json.JSONDecodeError, ValidationError) as exc:
                    logger.error("rejecting malformed message: %s", exc)
                    continue  # message.process already nacks-to-DLQ on raise; loop on parse error
                await handler.handle(job_msg)


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    # Pre-create the audio + jobs dirs so the first job doesn't race.
    Path(settings.audio_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.jobs_dir).mkdir(parents=True, exist_ok=True)

    llm = build_llm_service(settings)
    tts = build_tts_service(settings)
    handler = JobHandler(llm=llm, tts=tts)
    logger.info(
        "worker starting", extra={"llm_provider": llm.name, "tts_provider": tts.name}
    )

    stop_event = asyncio.Event()

    def _request_stop(*_: object) -> None:
        logger.info("shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, _request_stop)

    consumer_task = asyncio.create_task(_consume(handler))
    stop_task = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait(
        {consumer_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()
    for task in done:
        if task is consumer_task:
            exc = task.exception()
            if exc:
                logger.exception("consumer crashed", exc_info=exc)

    try:
        await llm.aclose()
        await tts.aclose()
    finally:
        await get_rabbitmq_client().close()
    logger.info("worker stopped")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
