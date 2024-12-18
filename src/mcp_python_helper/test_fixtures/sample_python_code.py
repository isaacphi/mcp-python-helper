import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

# Constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30.0
SUPPORTED_FORMATS = ["json", "xml", "yaml"]

# Simple variable assignments
counter = 0
name = "Test User"
is_active = True
price = 19.99


# Enums
class Status(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


# Regular class with properties
class User:
    def __init__(self, username: str, email: str):
        self._username = username
        self._email = email
        self._created_at = datetime.now()

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not value:
            raise ValueError("Username cannot be empty")
        self._username = value

    def __str__(self) -> str:
        return f"User({self._username})"


# Dataclass example
@dataclass
class Point:
    x: float
    y: float
    label: str | None = None

    def distance_from_origin(self) -> float:
        return (self.x**2 + self.y**2) ** 0.5


# Generic class
T = TypeVar("T")


class Queue(Generic[T]):
    def __init__(self):
        self.items: list[T] = []

    def enqueue(self, item: T) -> None:
        self.items.append(item)

    def dequeue(self) -> T | None:
        return self.items.pop(0) if self.items else None


# Function with type hints and default values
def calculate_discount(
    price: float, discount_percent: float = 10.0, max_discount: float | None = None
) -> float:
    discount = price * (discount_percent / 100)
    if max_discount is not None:
        discount = min(discount, max_discount)
    return price - discount


# Async function
async def fetch_data(url: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, any]:
    await asyncio.sleep(0.1)  # Simulate network delay
    return {"url": url, "status": Status.COMPLETED}


# Class with context manager
class DatabaseConnection:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.is_connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self) -> None:
        self.is_connected = True
        print("Connected to database")

    def disconnect(self) -> None:
        self.is_connected = False
        print("Disconnected from database")


# Decorator example
def retry(max_attempts: int = MAX_RETRIES):
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise e
                    await asyncio.sleep(2**attempt)

        return wrapper

    return decorator


# Multiple inheritance
class Loggable:
    def log(self, message: str) -> None:
        print(f"Log: {message}")


class Serializable:
    def to_dict(self) -> dict[str, any]:
        return self.__dict__


class Task(Loggable, Serializable):
    def __init__(self, name: str, priority: int):
        self.name = name
        self.priority = priority
        self.created_at = datetime.now()

    def execute(self) -> None:
        self.log(f"Executing task: {self.name}")
        # Task execution logic here


# Exception hierarchy
class ServiceError(Exception):
    pass


class ValidationError(ServiceError):
    pass


class ResourceNotFoundError(ServiceError):
    pass


# Usage examples
def main():
    # Create some objects
    user = User("testuser", "test@example.com")
    point = Point(3.0, 4.0, "Test Point")
    queue: Queue[str] = Queue()

    # Use the objects
    queue.enqueue("first item")
    queue.enqueue("second item")
    print(f"Distance from origin: {point.distance_from_origin()}")

    # Test error handling
    try:
        if not user.username:
            raise ValidationError("Username cannot be empty")
    except ValidationError as e:
        print(f"Validation error: {e}")

    # Context manager usage
    with DatabaseConnection("postgresql://localhost:5432/db") as conn:
        print(f"Connection status: {conn.is_connected}")


if __name__ == "__main__":
    main()
