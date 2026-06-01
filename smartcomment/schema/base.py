"""Base Pydantic models with metadata support and traceability."""

import os
from datetime import datetime
from pydantic import (
    BaseModel,
    ModelWrapValidatorHandler,
    PrivateAttr,
    computed_field,
    model_validator,
    Field, 
    field_validator, 
)
from pydantic import JsonValue
from typing import Any, Self


def _get_timestamp(add_random_suffix: bool = False) -> str:
    """Get the current timestamp in the format ``YYYY-MM-DD HH:MM:SS.sss``.

    Args:
        add_random_suffix (`bool`, defaults to `False`):
            Whether to append a random hex suffix for uniqueness.

    Returns:
        `str`:
            Formatted timestamp string.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if add_random_suffix:
        timestamp += f"_{os.urandom(3).hex()}"
    return timestamp


class BaseMetadataModel(BaseModel):
    """Base class that provides a private metadata field and its serialization logic.

    This class ensures that metadata is stored as a private attribute while
    remaining accessible and serializable through a computed field.
    """

    _metadata: dict[str, JsonValue] = PrivateAttr(default_factory=dict)

    def update_metadata(self, metadata: dict[str, JsonValue]) -> None:
        """Update the metadata of the object.

        Args:
            metadata (`dict[str, JsonValue]`):
                The metadata to be merged into the existing metadata.
        """
        self._metadata.update(metadata)

    @model_validator(mode="wrap")
    @classmethod
    def _restore_metadata_private_attrs(
        cls,
        values: Any,
        handler: ModelWrapValidatorHandler[Self],
    ) -> Self:
        """Restore private metadata from serialized data during deserialization.

        Args:
            values (`Any`):
                The input values to validate.
            handler (`ModelWrapValidatorHandler[Self]`):
                The handler function to create the instance.

        Returns:
            `Self`:
                The validated instance with private metadata restored.
        """
        if not isinstance(values, dict):
            return handler(values)

        metadata = values.get("metadata", {})
        instance = handler(values)
        instance._metadata = metadata
        return instance

    @computed_field  # type: ignore[prop-decorator]
    @property
    def metadata(self) -> dict[str, JsonValue]:
        """Get the metadata of the object.

        Returns:
            `dict[str, JsonValue]`:
                A copy of the metadata dictionary.
        """
        return self._metadata.copy()


class TraceableModel(BaseMetadataModel):
    """It is a base class for all traceable models. It extends the parent class
    with creation timestamp and caller location."""

    created_at: str = Field(
        default_factory=_get_timestamp,
        min_length=1,
        description="Creation timestamp in the format `YYYY-MM-DD HH:MM:SS.sss`.",
    )
    filename: str = Field(
        ...,
        description="Source filename where this object was created.",
    )
    lineno: int = Field(
        ...,
        ge=0,
        description="Source line number where this object was created.",
    )


    @field_validator("created_at")
    @classmethod
    def _validate_timestamp_format(cls, value: str) -> str:
        """Validate that the creation timestamp is a valid timestamp in the format `YYYY-MM-DD HH:MM:SS.sss`."""
        try:
            datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            raise ValueError(
                f"`created_at` must be a valid timestamp in 'YYYY-MM-DD HH:MM:SS.sss' format "
                f"but '{value}' is found."
            )
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trigger_point(self) -> str:
        """Return ``{filename}:{lineno}`` indicating where this object is created.

        Returns:
            `str`:
                The trigger point string.
        """
        return f"{self.filename}:{self.lineno}"
