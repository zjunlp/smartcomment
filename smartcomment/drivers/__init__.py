"""Graph storage driver backends."""

from collections import OrderedDict
from .base import GraphDriver
from .in_memory import InMemoryGraphDriver


_DRIVER_BACKENDS: OrderedDict[str, type[GraphDriver]] = OrderedDict(
    (
        ("in_memory", InMemoryGraphDriver),
    )
)
