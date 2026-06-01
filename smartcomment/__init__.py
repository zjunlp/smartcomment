"""smartcomment: A General-Purpose Execution Graph Tracing Package."""

from .runtime import (
    current_context,
    current_graph,
    current_op,
    current_session,
    comment_graph,
    comment_op_scope,
    comment_session,
    disable_tracing,
    enable_tracing,
    is_tracing_enabled,
    propagate_attributes,
)
from .api import (
    comment_fn,
    comment_link,
    comment_mutation,
    comment_op,
    comment_variable,
)
from .identity import IdentityRegistry
from .logging import logger, setup_logger
from .debugging import draw_graph


__all__ = [
    "IdentityRegistry",
    "logger",
    "setup_logger",
    "comment_graph",
    "comment_op_scope",
    "comment_session",
    "current_context",
    "current_graph",
    "current_op",
    "current_session",
    "disable_tracing",
    "draw_graph",
    "enable_tracing",
    "is_tracing_enabled",
    "propagate_attributes",
    "comment_fn",
    "comment_link",
    "comment_mutation",
    "comment_op",
    "comment_variable",
]
