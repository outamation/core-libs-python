import os
from typing import Optional, Callable
import asyncio
import json
from urllib.parse import quote
from outamation_pkg_logger import setup_logging, trace

from dotenv import load_dotenv
import aio_pika
from aio_pika import connect_robust, Message, DeliveryMode
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel
import aiohttp

# Load environment variables
load_dotenv()

# Configuration from environment variables
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")
RABBITMQ_MGMT_PORT = os.getenv("RABBITMQ_MGMT_PORT", 15672)

logger = setup_logging(console_level="TRACE", rotation="20 MB", retention="30 days")


class RabbitMqService:
    def __init__(self) -> None:
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractRobustChannel] = None
        self._is_closed = False
        self._connection_lock = asyncio.Lock()

    async def get_channel(self) -> AbstractRobustChannel:
        # Check connection status before acquiring lock for performance
        if self.channel and not self.channel.is_closed and not self._is_closed:
            return self.channel

        async with self._connection_lock:
            # Double-check inside lock
            if self.channel and not self.channel.is_closed and not self._is_closed:
                return self.channel
            await self.connect_to_server()
            return self.channel

    @classmethod
    async def create(cls, prefetch_count: int = 1) -> "RabbitMqService":
        instance = cls()
        await instance.connect_to_server(prefetch_count)
        return instance

    async def connect_to_server(self, prefetch_count: int = 1) -> None:
        try:
            # Close existing connection if any
            if self.connection and not self.connection.is_closed:
                await self.connection.close()

            # Build connection URL
            connection_url = (
                f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@"
                f"{RABBITMQ_HOST}:{RABBITMQ_PORT}{RABBITMQ_VHOST}"
            )

            # Establish robust connection
            self.connection = await connect_robust(
                connection_url,
                heartbeat=400,
                blocked_connection_timeout=300,
                connection_attempts=3,
                retry_delay=5,
            )

            # Create channel and set QoS
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=prefetch_count)
            self._is_closed = False

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    async def publish_message_persistent(
        self, queue_name: str, body: str, priority: int
    ) -> None:
        try:
            channel = await self.get_channel()

            # Declare queue with priority support
            args = {"x-max-priority": 255}
            await channel.declare_queue(queue_name, durable=True, arguments=args)

            # Create message with priority and persistence
            message = Message(
                body.encode(), priority=priority, delivery_mode=DeliveryMode.PERSISTENT
            )

            # Publish message to default exchange
            await channel.default_exchange.publish(message, routing_key=queue_name)

        except Exception as e:
            logger.error(f"Error creating queue/publishing message: {e}")
            raise

    async def declare_new_queue(self, queue_name: str):
        channel = await self.get_channel()
        args = {"x-max-priority": 255}
        return await channel.declare_queue(queue_name, durable=True, arguments=args)

    async def publish(self, queue_name: str, body: str, priority: int = 0) -> None:
        channel = await self.get_channel()
        message = Message(
            body=body.encode(),
            priority=priority,
            delivery_mode=DeliveryMode.PERSISTENT,
        )
        await channel.default_exchange.publish(message, routing_key=queue_name)

    async def create_consumer(self, queue: str, callback: Callable) -> None:
        try:
            channel = await self.get_channel()

            # Declare queue with priority support
            args = {"x-max-priority": 255}
            queue_obj = await channel.declare_queue(queue, durable=True, arguments=args)

            # Start consuming messages
            await queue_obj.consume(callback)

        except Exception as e:
            logger.error(f"Error creating consumer: {e}")
            raise

    async def get_message(self, queue_name: str):
        try:
            channel = await self.get_channel()
            args = {"x-max-priority": 255}
            queue = await channel.declare_queue(
                queue_name, durable=True, arguments=args
            )

            message = await queue.get(no_ack=False)
            return message

        except aio_pika.exceptions.QueueEmpty:
            return None
        except Exception as e:
            logger.error(f"Error getting message: {e}")
            raise

    async def close(self) -> None:
        try:
            self._is_closed = True
            if self.channel and not self.channel.is_closed:
                await self.channel.close()
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")

    @staticmethod
    async def peek_and_sum_page_count(
        queue_name: str,
        count: int = 1000,
        api_url: str = "",
        username: str = "",
        password: str = "",
        vhost: Optional[str] = None,
    ) -> tuple[int, int]:
        """
        Use RabbitMQ HTTP API to peek messages from a queue and sum page numbers.

        This method uses the RabbitMQ Management HTTP API to retrieve messages
        without consuming them, and sums up the 'num_of_pages' field from
        each message's filemetadata.

        Args:
            queue_name: Name of the queue to peek into
            count: Maximum number of messages to retrieve (default: 1000)
            api_url: Management API URL (uses default if empty)
            username: Management API username (uses default if empty)
            password: Management API password (uses default if empty)
            vhost: Virtual host (uses default if None)

        Returns:
            tuple[int, int]: Total page count and number of messages processed

        Reference:
            https://www.rabbitmq.com/docs/http-api.html#post--api-queues-vhost-name-get
        """
        # Use defaults if not provided
        api_url = api_url or f"http://{RABBITMQ_HOST}:{RABBITMQ_MGMT_PORT}"
        username = username or RABBITMQ_USER
        password = password or RABBITMQ_PASS
        vhost = vhost or RABBITMQ_VHOST

        # URL encode vhost and queue name
        vhost_enc = quote(vhost, safe="")
        queue_enc = quote(queue_name, safe="")
        url = f"{api_url}/api/queues/{vhost_enc}/{queue_enc}/get"

        # API payload
        payload = {
            "count": count,
            "ackmode": "ack_requeue_true",  # Don't consume messages
            "encoding": "auto",
            "truncate": 50000,
        }

        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(username, password)
                async with session.post(url, json=payload, auth=auth) as response:
                    response.raise_for_status()
                    messages = await response.json()

            total_page_count = 0
            for msg in messages:
                try:
                    body = msg.get("payload")
                    data = json.loads(body)
                    total_page_count += data.get("filemetadata", {}).get(
                        "num_of_pages", 0
                    )
                except Exception as e:
                    logger.error(f"Error parsing message: {e}")

            return total_page_count, len(messages)

        except Exception as e:
            logger.error(f"Error peeking RabbitMQ queue: {e}")
            return 0, 0


# Package exports
__all__ = [
    "RabbitMqService",
    "RABBITMQ_HOST",
    "RABBITMQ_PORT",
    "RABBITMQ_USER",
    "RABBITMQ_PASS",
    "RABBITMQ_VHOST",
    "RABBITMQ_MGMT_PORT",
]

# Package metadata
__version__ = "0.1.0"
__author__ = "Outamation Team"
__description__ = (
    "A robust asynchronous RabbitMQ client utility package built on aio-pika"
)
