"""Driver factory tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_session,
    comment_variable,
)
from smartcomment.runtime.network import ExecNetwork
from tests.helpers import BaseTracingTest


class DriverFactoryTests(BaseTracingTest):
    """Test driver_type resolution and ExecNetwork factory construction."""

    def test_default_driver_type_is_in_memory(self) -> None:
        """New graphs default to the in_memory driver type."""
        with comment_graph() as graph:
            self.assertEqual(graph.driver_type, "in_memory")

    def test_driver_type_in_exported_data(self) -> None:
        """Exported data includes driver_type and data."""
        with comment_graph() as graph:
            with comment_session(session_name="dt"):
                comment_variable("v", id_strategy="content")
            exported = graph.export_graph()

        self.assertEqual(exported["driver_type"], "in_memory")
        self.assertIn("data", exported)
        self.assertIsInstance(exported["data"], dict)
        self.assertIn("nodes", exported["data"])

    def test_driver_type_roundtrip(self) -> None:
        """driver_type survives export -> import."""
        with comment_graph() as graph:
            with comment_session(session_name="rt"):
                comment_variable("hello", id_strategy="content")
            exported = graph.export_graph()

        imported = ExecNetwork.import_graph(exported)
        self.assertEqual(imported.driver_type, "in_memory")
        self.assertEqual(imported.graph_id, graph.graph_id)
        self.assertEqual(
            len(imported._driver.all_nodes()),
            len(graph._driver.all_nodes()),
        )

    def test_unknown_driver_type_raises(self) -> None:
        """Constructing with an unknown driver_type raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            ExecNetwork(driver_type="nonexistent")
        self.assertIn("nonexistent", str(cm.exception))

    def test_driver_backends_includes_in_memory(self) -> None:
        """Built-in driver map includes the in-memory backend."""
        from smartcomment.drivers import _DRIVER_BACKENDS

        self.assertIn("in_memory", _DRIVER_BACKENDS)
