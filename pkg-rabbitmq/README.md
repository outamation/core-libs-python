# Outamation RabbitMQ Package

A robust asynchronous RabbitMQ client utility package built on aio-pika for Outamation projects.

## Features

- **Asynchronous Operations**: Built on `aio-pika` for high-performance async operations
- **Connection Management**: Automatic connection handling with robust reconnection
- **Priority Queues**: Support for priority-based message handling
- **Consumer Support**: Easy-to-use consumer patterns for message processing
- **Management API**: HTTP API integration for queue monitoring and management
- **Environment Configuration**: Flexible configuration through environment variables

## Installation

```bash
pip install git+https://github.com/outamation/core-libs-python.git#subdirectory=pkg-rabbitmq
```

## Configuration

Set the following environment variables or create a `.env` file:

```env
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_VHOST=/
RABBITMQ_MGMT_PORT=15672
```

## Quick Start

### Basic Usage

```python
import asyncio
from outamation_pkg_rabbitmq import RabbitMqService

async def main():
    # Create RabbitMQ service instance
    rabbitmq = await RabbitMqService.create()
    
    # Publish a message
    await rabbitmq.publish_message_persistent(
        queue_name="my_queue",
        body="Hello, RabbitMQ!",
        priority=5
    )
    
    # Get a single message
    message = await rabbitmq.get_message("my_queue")
    if message:
        print(f"Received: {message.body.decode()}")
        await message.ack()
    
    # Close connection
    await rabbitmq.close()

asyncio.run(main())
```

### Consumer Pattern

```python
import asyncio
from aio_pika import IncomingMessage
from outamation_pkg_rabbitmq import RabbitMqService

async def message_handler(message: IncomingMessage):
    """Handle incoming messages"""
    try:
        body = message.body.decode()
        print(f"Processing message: {body}")
        
        # Process your message here
        await asyncio.sleep(1)  # Simulate work
        
        # Acknowledge the message
        await message.ack()
    except Exception as e:
        print(f"Error processing message: {e}")
        await message.reject(requeue=False)

async def start_consumer():
    rabbitmq = await RabbitMqService.create(prefetch_count=10)
    
    # Create consumer
    await rabbitmq.create_consumer(
        queue="processing_queue",
        callback=message_handler
    )
    
    print("Consumer started. Press Ctrl+C to exit...")
    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        print("Shutting down consumer...")
        await rabbitmq.close()

asyncio.run(start_consumer())
```

### Batch Publishing

```python
import asyncio
from outamation_pkg_rabbitmq import RabbitMqService

async def publish_batch():
    rabbitmq = await RabbitMqService.create()
    
    # Publish multiple messages with different priorities
    messages = [
        {"body": "Low priority task", "priority": 1},
        {"body": "Medium priority task", "priority": 5},
        {"body": "High priority task", "priority": 10},
    ]
    
    for msg in messages:
        await rabbitmq.publish(
            queue_name="task_queue",
            body=msg["body"],
            priority=msg["priority"]
        )
    
    await rabbitmq.close()

asyncio.run(publish_batch())
```

## API Reference

### RabbitMqService

The main service class for RabbitMQ operations.

#### Class Methods

##### `create(prefetch_count=1)`
Create and initialize a new RabbitMQ service instance.

**Parameters:**
- `prefetch_count` (int): Number of unacknowledged messages that a consumer can handle simultaneously

**Returns:**
- `RabbitMqService`: Initialized service instance

#### Instance Methods

##### `connect_to_server(prefetch_count=1)`
Connect to the RabbitMQ server.

**Parameters:**
- `prefetch_count` (int): QoS prefetch count

##### `publish_message_persistent(queue_name, body, priority)`
Create/declare a queue and publish a persistent message with priority.

**Parameters:**
- `queue_name` (str): Name of the queue
- `body` (str): Message content
- `priority` (int): Message priority (0-255)

##### `publish(queue_name, body, priority=0)`
Publish a message to an existing queue.

**Parameters:**
- `queue_name` (str): Name of the queue
- `body` (str): Message content
- `priority` (int): Message priority (default: 0)

##### `declare_new_queue(queue_name)`
Declare a new queue with priority support.

**Parameters:**
- `queue_name` (str): Name of the queue

**Returns:**
- Queue object

##### `create_consumer(queue, callback)`
Create a consumer for a specific queue.

**Parameters:**
- `queue` (str): Queue name
- `callback` (Callable): Function to handle incoming messages

##### `get_message(queue_name)`
Get a single message from a queue (polling mode).

**Parameters:**
- `queue_name` (str): Name of the queue

**Returns:**
- Message object or `None` if queue is empty

##### `close()`
Close the RabbitMQ connection and channel.

#### Static Methods

##### `peek_and_sum_page_count(queue_name, count=1000, api_url="", username="", password="", vhost=None)`
Use RabbitMQ HTTP API to peek messages and sum page counts.

**Parameters:**
- `queue_name` (str): Name of the queue to peek
- `count` (int): Maximum number of messages to peek (default: 1000)
- `api_url` (str): Management API URL (optional)
- `username` (str): Management API username (optional)
- `password` (str): Management API password (optional)
- `vhost` (str): Virtual host (optional)

**Returns:**
- `tuple[int, int]`: Total page count and message count

## Error Handling

The package includes robust error handling:

```python
import asyncio
from outamation_pkg_rabbitmq import RabbitMqService

async def safe_operations():
    try:
        rabbitmq = await RabbitMqService.create()
        await rabbitmq.publish("test_queue", "test message")
    except Exception as e:
        print(f"RabbitMQ operation failed: {e}")
    finally:
        if 'rabbitmq' in locals():
            await rabbitmq.close()
```

## Advanced Features

### Connection Resilience

The service automatically handles connection failures with:
- Automatic reconnection attempts
- Connection heartbeat monitoring
- Blocked connection timeout handling
- Retry delays with exponential backoff

### Priority Queues

All queues are created with priority support (0-255):

```python
# High priority message
await rabbitmq.publish("urgent_queue", "Critical task", priority=255)

# Low priority message  
await rabbitmq.publish("urgent_queue", "Background task", priority=1)
```

### Management API Integration

Monitor queue statistics using the management API:

```python
total_pages, message_count = await RabbitMqService.peek_and_sum_page_count(
    queue_name="processing_queue",
    count=100
)
print(f"Queue has {message_count} messages with {total_pages} total pages")
```

## Requirements

- Python 3.8+
- aio-pika >= 9.0.0
- python-dotenv >= 1.0.0
- requests >= 2.25.0

## License

Proprietary - Outamation Internal Use

## Contributing

This package is maintained internally by the Outamation team. For issues or feature requests, please contact the development team.
