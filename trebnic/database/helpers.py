import json
import logging
from datetime import date
from typing import Any, Dict, Optional

from registry import registry, Services

logger = logging.getLogger(__name__)

LOCKED_PLACEHOLDER = "[Locked]"


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class LockedDataWriteError(DatabaseError):
    """Raised when attempting to save placeholder data while app is locked.

    This prevents data corruption where encrypted fields would be overwritten
    with the "[Locked]" placeholder string.
    """
    pass


def _encrypt_field(value: Optional[str]) -> Optional[str]:
    """Encrypt a field value if encryption is enabled and unlocked.

    Returns the original value if:
    - Value is None or empty
    - Encryption is not available
    - App is not unlocked

    Raises:
        LockedDataWriteError: If attempting to encrypt the locked placeholder
    """
    if not value:
        return value
    # Guard: never encrypt the locked placeholder - this would corrupt data
    if value == LOCKED_PLACEHOLDER:
        raise LockedDataWriteError(
            f"Cannot encrypt locked placeholder '{LOCKED_PLACEHOLDER}'. "
            "This indicates an attempt to save data while app is locked."
        )
    crypto = registry.get(Services.CRYPTO)
    if crypto is None:
        return value
    return crypto.encrypt_if_unlocked(value)


def _decrypt_field(value: Optional[str]) -> Optional[str]:
    """Decrypt a field value if it's encrypted.

    Returns the original value if:
    - Value is None or empty
    - Value is not in encrypted format
    - Decryption fails (wrong key, corrupted)
    """
    if not value:
        return value
    crypto = registry.get(Services.CRYPTO)
    if crypto is None:
        return value
    return crypto.decrypt_if_encrypted(value)


def _is_encrypted(value: Optional[str]) -> bool:
    """Check if a value is in encrypted format."""
    if not value:
        return False
    crypto = registry.get(Services.CRYPTO)
    if crypto is None:
        return False
    return crypto.is_encrypted(value)


def _deserialize_task_row(row) -> Dict[str, Any]:
    """Convert a raw database row into a task dict with decrypted fields.

    Handles decrypting title and notes, parsing JSON weekdays,
    setting defaults for optional fields, and converting date strings.
    """
    task_dict = dict(row)
    task_dict["title"] = _decrypt_field(task_dict.get("title", ""))
    task_dict["notes"] = _decrypt_field(task_dict.get("notes", ""))
    task_dict["recurrence_weekdays"] = json.loads(task_dict.get("recurrence_weekdays", "[]"))
    task_dict["recurrence_end_type"] = task_dict.get("recurrence_end_type", "never")
    task_dict["recurrence_from_completion"] = task_dict.get("recurrence_from_completion", 0)
    if task_dict.get("due_date"):
        task_dict["due_date"] = date.fromisoformat(task_dict["due_date"])
    if task_dict.get("recurrence_end_date"):
        task_dict["recurrence_end_date"] = date.fromisoformat(task_dict["recurrence_end_date"])
    return task_dict
