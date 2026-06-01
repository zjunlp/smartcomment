"""Utility functions for visualization."""

from __future__ import annotations
import warnings
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from matplotlib.colors import Colormap


def _truncate(val: str, max_len: int = 30) -> str:
    """Truncate a string for graph labels (newlines collapsed to spaces).

    Args:
        val (`str`):
            Text to truncate.
        max_len (`int`, defaults to `30`):
            Maximum length of the string.

    Returns:
        `str`:
            Truncated string without newlines.
    """
    s = val.replace("\n", " ").replace("\r", "")
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _escape_html(s: str) -> str:
    """Escape string for HTML labels."""
    return s.replace(
        "&", 
        "&amp;"
    ).replace(
        "<", 
        "&lt;"
    ).replace(
        ">", 
        "&gt;"
    ).replace(
        '"', 
        "&quot;"
    )


def _get_color_map(
    categories: Iterable[str], 
    cmap: str | Colormap | None = None, 
    max_auto: int = 20
) -> dict[str, str]:
    """Generate a hex color mapping for a set of categories using Matplotlib.
    
    Args:
        categories (`Iterable[str]`): 
            Unique categories to colorize.
        cmap (`str | Colormap | None`, optional): 
            Matplotlib colormap name or a colormap object. 
            If not provided, the default colormap will be used.
        max_auto (`int`): 
            If no color map is provided and categories exceed this, return no colors.
        
    Returns:
        `dict[str, str]`:
            Mapping from category string to hex color string.
    """
    if not categories:
        raise ValueError("No categories are provided.")
        
    if cmap is None and len(categories) > max_auto:
        return {}
        
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
    except ImportError as e:
        if cmap is not None:
            raise ImportError(
                "`matplotlib` is required for custom colormaps. "
                "Install it via `pip install matplotlib`."
            ) from e

        # Graceful fallback to no colors if default behavior and no matplotlib. 
        warnings.warn(
            "`matplotlib` is required for custom colormaps, but it is not installed. "
            "No colors will be assigned to categories."
        )
        return {}  

    if cmap is None:
        cmap_obj = plt.get_cmap("tab20")
    elif isinstance(cmap, str):
        cmap_obj = plt.get_cmap(cmap)
    else:
        cmap_obj = cmap

    n = len(categories)
    color_dict = {}
    for i, cat in enumerate(sorted(categories)):
        rgba = cmap_obj(i / max(1, n - 1))
        color_dict[cat] = mcolors.to_hex(rgba)
        
    return color_dict