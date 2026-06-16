"""RabbitMQ client + topology helpers.

We use ``aio_pika`` for both the API publisher and the worker consumer so we
share one library and one connection style across processes.

Topology
--------
* Durable work queue: ``RABBITMQ_JOB_QUEUE`` (default ``voice.jobs``)
* Dead-letter exchange + queue for messages that exhausted retries.

The publisher uses persistent delivery so jobs survive broker restarts.
"""

from __future__ import annotations

import logging
from typing import Optional

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractRobustConnection

from ..config import Settings, get_settings
from ..models import JobMessage

logger = logging.getLogger(__name__)


class RabbitMQClient:
    """Thin convenience wrapper around an ``aio_pika`` robust connection."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: Optional[AbstractRobustConnection] = None

    async def connect(self) -> AbstractRobustConnection:
        if self._connection is None or self._connection.is_closed:
            logger.info("connecting to RabbitMQ")
            self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        return self._connection

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

    async def publish_job(self, message: JobMessage) -> None:
        connection = await self.connect()
        channel = await connection.channel(publisher_confirms=True)
        try:
            await declare_topology(channel, self._settings)
            body = message.model_dump_json().encode("utf-8")
            await channel.default_exchange.publish(
                Message(
                    body=body,
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id=message.job_id,
                ),
                routing_key=self._settings.rabbitmq_job_queue,
            )
            logger.info(
                "published job to queue",
                extra={"job_id": message.job_id, "queue": self._settings.rabbitmq_job_queue},
            )
        finally:
            await channel.close()


async def declare_topology(
    channel: aio_pika.abc.AbstractChannel, settings: Settings
) -> aio_pika.abc.AbstractQueue:
    """Idempotently declare the work queue + dead-letter topology.

    Returns the main work queue (useful for the worker).
    """
    # Dead-letter exchange + queue for poisoned messages.
    dlx = await channel.declare_exchange(
        settings.rabbitmq_dlx, ExchangeType.FANOUT, durable=True
    )
    dlq = await channel.declare_queue(settings.rabbitmq_dlq, durable=True)
    await dlq.bind(dlx)

    # Main work queue routes rejections to the DLX.
    queue = await channel.declare_queue(
        settings.rabbitmq_job_queue,
        durable=True,
        arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx},
    )
    return queue


_client: Optional[RabbitMQClient] = None


def get_rabbitmq_client() -> RabbitMQClient:
    global _client
    if _client is None:
        _client = RabbitMQClient(get_settings())
    return _client
