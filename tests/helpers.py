"""Shared test fixtures for the smartcomment test suite."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from smartcomment import (
    IdentityRegistry,
    enable_tracing,
)


@dataclass
class MemoryItem:
    """Simple mutable memory item used by the tests."""

    memory_id: str
    content: str


class BaseTracingTest(unittest.TestCase):
    """Base test case that enables tracing and registers the ``MemoryItem``
    identity strategy before each test, and restores tracing afterwards."""

    def setUp(self) -> None:
        enable_tracing()
        IdentityRegistry.register(
            MemoryItem,
            lambda v: v.memory_id,
            exist_ok=True,
        )

    def tearDown(self) -> None:
        enable_tracing()
