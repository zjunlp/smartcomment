"""Identity strategy registry using plain callables."""

import json
from hashlib import sha1
from ..logging import logger
from typing import (
    Any,
    Callable,
    ClassVar,
    Literal,
    KeysView, 
    ValuesView,
)


def _canonicalize(value: Any) -> str:
    """Create a deterministic text representation for content-based identity."""
    try:
        return json.dumps(value, sort_keys=True, default=repr)
    except TypeError:
        return repr(value)


def _content_strategy(value: Any) -> str:
    """SHA-1 of the canonicalized value, prefixed by the qualified class name."""
    digest = sha1(_canonicalize(value).encode("utf-8")).hexdigest()
    return f"{type(value).__qualname__}:{digest}"


def _hash_strategy(value: Any) -> str:
    """Python hash of the value, prefixed by the qualified class name."""
    return f"{type(value).__qualname__}:{hash(value)}"


def _object_id_strategy(value: Any) -> str:
    """Python object identity, prefixed by the qualified class name."""
    return f"{type(value).__qualname__}:{id(value)}"


class IdentityRegistry:
    """Global registry that resolves identity strategies by name or Python type.

    Example::

        IdentityRegistry.register("my_strategy", lambda v: f"custom-{v.id}")
        IdentityRegistry.register(MyType, lambda v: f"my-{v.pk}")
        fn = IdentityRegistry.get("my_strategy")
    """

    _name_to_fn: ClassVar[dict[str, Callable[[Any], str]]] = {
        "content": _content_strategy,
        "hash": _hash_strategy,
        "object_id": _object_id_strategy,
    }
    _type_to_fn: ClassVar[dict[type, Callable[[Any], str]]] = {}

    def __init__(self) -> None:
        raise OSError(
            "`IdentityRegistry` is designed to manage identity strategies globally. "
            "It cannot be instantiated. Please use its class methods instead."
        )

    @classmethod
    def register(
        cls,
        key: str | type,
        fn: Callable[[Any], str],
        exist_ok: bool = False,
    ) -> None:
        """Register an identity strategy by name or by Python type.

        Args:
            key (`str | type`):
                A string name or a Python type.
            fn (`Callable[[Any], str]`):
                The identity function.
            exist_ok (`bool`, defaults to `False`):
                If it not enabled, an error will be raised when the key already
                exists. Otherwise, it will overwrite the existing strategy.

        Raises:
            `ValueError`:
                If the key already exists and `exist_ok` is `False`.
            `TypeError`:
                If the key is not a string or a Python type.
        """
        if isinstance(key, str):
            if not exist_ok and key in cls._name_to_fn:
                raise ValueError(
                    f"Identity strategy '{key}' is already registered."
                )
            cls._name_to_fn[key] = fn
        elif isinstance(key, type):
            if not exist_ok and key in cls._type_to_fn:
                raise ValueError(
                    f"Identity strategy for type '{key.__name__}' is already registered."
                )
            cls._type_to_fn[key] = fn
        else:
            raise TypeError(
                f"Key must be a string or a Python type "
                f"but an instance of `{type(key).__name__}` is provided."
            )

    @classmethod
    def get(cls, key: str | type) -> Callable[[Any], str]:
        """Retrieve an identity strategy by name or type.

        Args:
            key (`str | type`):
                A string name or a Python type.

        Returns:
            `Callable[[Any], str]`:
                The registered identity function.

        Raises:
            `KeyError`:
                If no strategy is registered for the key.
            `TypeError`:
                If the key is not a string or a Python type.
        """
        if isinstance(key, str):
            if key not in cls._name_to_fn:
                raise KeyError(
                    f"No identity strategy registered for name '{key}'."
                )
            return cls._name_to_fn[key]
        if isinstance(key, type):
            if key not in cls._type_to_fn:
                raise KeyError(
                    f"No identity strategy registered for type '{key.__name__}'."
                )
            return cls._type_to_fn[key]
        raise TypeError(
            f"Key must be a string or a Python type "
            f"but an instance of `{type(key).__name__}` is provided."
        )

    @classmethod
    def resolve(
        cls,
        value: Any,
        override: Callable[[Any], str] | str | None = None,
    ) -> Callable[[Any], str]:
        """Resolve the most specific identity strategy for a value.

        The lookup order is: 
        1. Explicit override the user provides.
        2. Type-based lookup based on the provided value's type.
        3. Default ``content`` strategy if no other strategy is found.

        Args:
            value (`Any`):
                The runtime value whose strategy is needed.
            override (`Callable[[Any], str] | str | None`, optional):
                Optional per-call override. It can be a callable or a registered name.

        Returns:
            `Callable[[Any], str]`:
                The resolved identity function.
        """
        if override is not None:
            # A `str` subclass could theoretically define `__call__`. 
            # We still treat it as a registered strategy name, not as a custom identity function.
            if callable(override) and not isinstance(override, str):
                return override
            if isinstance(override, str):
                return cls.get(override)

        # We don't directly look up the type of the value, 
        # because the type could be a subclass of the registered type.
        for vtype, fn in cls._type_to_fn.items():
            if isinstance(value, vtype):
                return fn

        logger.debug(
            "No type-specific strategy is found for %s. " 
            "It will fallback to the default 'content' strategy.",
            type(value).__qualname__,
        )
        return cls._name_to_fn["content"]

    @classmethod
    def keys(cls, category: Literal["name", "type"] = "name") -> KeysView[str | type]:
        """Return registered keys.

        Args:
            category (`Literal["name", "type"]`, defaults to `"name"`):
                Which mapping to inspect.

        Returns:
            `KeysView[str | type]`:
                The keys.
        """
        if category == "name":
            return cls._name_to_fn.keys()
        return cls._type_to_fn.keys()

    @classmethod
    def values(cls, category: Literal["name", "type"] = "name") -> ValuesView[Callable[[Any], str]]:
        """Return registered strategy functions.

        Args:
            category (`Literal["name", "type"]`, defaults to `"name"`):
                Which mapping to inspect.

        Returns:
            `ValuesView[Callable[[Any], str]]`:
                The strategy functions.
        """
        if category == "name":
            return cls._name_to_fn.values()
        return cls._type_to_fn.values()
