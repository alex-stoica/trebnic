"""
Cryptographic services for field-level encryption and key derivation.

This module provides:
- Master password key derivation using Argon2id (preferred) or PBKDF2 (fallback)
- AES-256-GCM authenticated encryption for sensitive fields
- Secure key storage in memory only (never persisted)

Security Model:
- Master password is NEVER stored, only used to derive encryption key
- Encryption key lives only in memory during app session
- Each encrypted field has a unique nonce/IV
- Authentication tag prevents tampering

Usage:
    crypto = CryptoService()
    crypto.derive_key_from_password("user_password", salt)

    encrypted = crypto.encrypt_field("sensitive data")
    decrypted = crypto.decrypt_field(encrypted)
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import argon2 for preferred key derivation, fall back to PBKDF2
try:
    from argon2.low_level import hash_secret_raw, Type
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    logger.info("argon2-cffi not available, using PBKDF2 for key derivation")

# Try to import cryptography for AES-GCM
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    InvalidTag = Exception
    logger.warning("cryptography library not available - encryption disabled")


# ============================================================================
# Constants
# ============================================================================

# Key derivation parameters (Argon2id - OWASP recommended for password hashing)
ARGON2_TIME_COST = 3          # Number of iterations
ARGON2_MEMORY_COST = 65536    # 64 MB memory usage
ARGON2_PARALLELISM = 4        # Parallel threads
ARGON2_HASH_LEN = 32          # 256-bit key output

# PBKDF2 fallback parameters
PBKDF2_ITERATIONS = 600_000   # OWASP 2023 recommendation for SHA-256
PBKDF2_HASH_LEN = 32          # 256-bit key output

# Salt for key derivation (generated once per installation, stored in settings)
SALT_LENGTH = 32              # 256-bit salt

# AES-GCM parameters
AES_KEY_SIZE = 32             # 256-bit key
GCM_NONCE_SIZE = 12           # 96-bit nonce (recommended for GCM)
GCM_TAG_SIZE = 16             # 128-bit authentication tag

# Encrypted field format prefix (for identification)
ENCRYPTED_PREFIX = "ENC:1:"   # Version 1 encryption format

# Placeholder shown when app is locked and encrypted data can't be decrypted
LOCKED_PLACEHOLDER = "[Locked]"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EncryptedData:
    """Container for encrypted data with its nonce."""
    nonce: bytes       # 12 bytes
    ciphertext: bytes  # Variable length (plaintext + 16-byte tag)

    def to_string(self) -> str:
        """Encode to base64 string for database storage."""
        combined = self.nonce + self.ciphertext
        return ENCRYPTED_PREFIX + base64.b64encode(combined).decode('utf-8')

    @classmethod
    def from_string(cls, data: str) -> Optional["EncryptedData"]:
        """Decode from base64 string. Returns None if format is invalid."""
        if not data.startswith(ENCRYPTED_PREFIX):
            return None
        try:
            combined = base64.b64decode(data[len(ENCRYPTED_PREFIX):])
            if len(combined) < GCM_NONCE_SIZE + GCM_TAG_SIZE:
                return None
            return cls(
                nonce=combined[:GCM_NONCE_SIZE],
                ciphertext=combined[GCM_NONCE_SIZE:]
            )
        except (ValueError, TypeError):
            return None


# ============================================================================
# Key Derivation
# ============================================================================

def derive_key_argon2(password: str, salt: bytes) -> bytes:
    """Derive encryption key using Argon2id (preferred method).

    Argon2id is resistant to both side-channel and GPU attacks.
    """
    if not ARGON2_AVAILABLE:
        raise RuntimeError("Argon2 not available")

    return hash_secret_raw(
        secret=password.encode('utf-8'),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID  # Argon2id - hybrid of Argon2i and Argon2d
    )


def derive_key_pbkdf2(password: str, salt: bytes) -> bytes:
    """Derive encryption key using PBKDF2-SHA256 (fallback method).

    PBKDF2 is widely available but less GPU-resistant than Argon2.
    """
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        PBKDF2_ITERATIONS,
        dklen=PBKDF2_HASH_LEN
    )


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive encryption key from password using best available method."""
    if ARGON2_AVAILABLE:
        return derive_key_argon2(password, salt)
    return derive_key_pbkdf2(password, salt)


def generate_salt() -> bytes:
    """Generate a cryptographically secure random salt."""
    return secrets.token_bytes(SALT_LENGTH)


def compute_key_verification_hash(key: bytes) -> str:
    """Compute a verification hash of the derived key.

    This is stored to verify the password is correct without storing the key.
    Uses HMAC-SHA256 with a fixed context to prevent key recovery.
    """
    # Use HMAC with a context string to derive a verification hash
    # This ensures the verification hash can't be used to recover the key
    verification = hmac.new(
        key,
        b"trebnic-key-verification-v1",
        hashlib.sha256
    ).digest()
    return base64.b64encode(verification).decode('utf-8')


def verify_key(key: bytes, stored_hash: str) -> bool:
    """Verify that a derived key matches the stored verification hash."""
    computed = compute_key_verification_hash(key)
    return hmac.compare_digest(computed, stored_hash)


# ============================================================================
# CryptoService Class
# ============================================================================

class CryptoService:
    """
    Service for encrypting and decrypting sensitive fields.

    The encryption key is held only in memory and must be derived
    from the master password at app startup (unlock).

    Thread Safety:
        Uses double-check locking for thread-safe singleton initialization.
        The key should be set once during app initialization and not modified
        during operation.

    Example:
        crypto = CryptoService()

        # First-time setup
        salt = crypto.generate_salt()
        crypto.derive_key_from_password("master_password", salt)
        verification_hash = crypto.get_key_verification_hash()
        # Store salt and verification_hash in settings

        # Subsequent unlocks
        crypto.derive_key_from_password("master_password", stored_salt)
        if not crypto.verify_key(stored_verification_hash):
            raise ValueError("Invalid password")

        # Encrypt/decrypt fields
        encrypted = crypto.encrypt_field("sensitive data")
        decrypted = crypto.decrypt_field(encrypted)
    """

    _instance: Optional["CryptoService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "CryptoService":
        """Singleton pattern - one crypto service for the app."""
        if cls._instance is None:
            with cls._instance_lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._key: Optional[bytes] = None
                    cls._instance._aesgcm: Optional[AESGCM] = None
        return cls._instance

    @property
    def is_available(self) -> bool:
        """Check if encryption is available (cryptography library installed)."""
        return CRYPTO_AVAILABLE

    @property
    def is_unlocked(self) -> bool:
        """Check if the encryption key has been derived (app is unlocked)."""
        return self._key is not None

    @property
    def uses_argon2(self) -> bool:
        """Check if Argon2 is being used for key derivation."""
        return ARGON2_AVAILABLE

    def derive_key_from_password(self, password: str, salt: bytes) -> None:
        """Derive and store the encryption key from the master password.

        Args:
            password: The user's master password (never stored)
            salt: Random salt (stored in database settings)
        """
        self._key = derive_key(password, salt)
        if CRYPTO_AVAILABLE:
            self._aesgcm = AESGCM(self._key)

    def get_key_verification_hash(self) -> str:
        """Get the verification hash for the current key.

        This hash should be stored in settings to verify future unlock attempts.

        Returns:
            Base64-encoded verification hash

        Raises:
            RuntimeError: If no key has been derived yet
        """
        if self._key is None:
            raise RuntimeError("No encryption key derived")
        return compute_key_verification_hash(self._key)

    def verify_key(self, stored_hash: str) -> bool:
        """Verify that the current key matches the stored verification hash.

        Args:
            stored_hash: The verification hash from settings

        Returns:
            True if the key is correct, False otherwise
        """
        if self._key is None:
            return False
        return verify_key(self._key, stored_hash)

    def lock(self) -> None:
        """Clear the encryption key from memory (lock the app)."""
        if self._key is not None:
            # Overwrite key in memory before clearing reference
            # Note: Python's memory model doesn't guarantee this is effective,
            # but it's better than nothing
            key_len = len(self._key)
            # We can't actually mutate bytes, so just clear the reference
            self._key = None
            self._aesgcm = None

    def encrypt_field(self, plaintext: str) -> str:
        """Encrypt a field value for storage.

        Args:
            plaintext: The sensitive data to encrypt

        Returns:
            Encrypted string in format "ENC:1:<base64(nonce + ciphertext + tag)>"

        Raises:
            RuntimeError: If encryption is not available or key not derived
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("Encryption not available - install cryptography library")
        if self._aesgcm is None:
            raise RuntimeError("Encryption key not derived - unlock the app first")

        # Generate unique nonce for this encryption
        nonce = secrets.token_bytes(GCM_NONCE_SIZE)

        # Encrypt with AES-GCM (includes authentication tag)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

        return EncryptedData(nonce=nonce, ciphertext=ciphertext).to_string()

    def decrypt_field(self, encrypted: str) -> Optional[str]:
        """Decrypt a field value from storage.

        Args:
            encrypted: The encrypted string from the database

        Returns:
            Decrypted plaintext, or None if decryption fails

        Note:
            Returns None rather than raising on decryption failure
            to handle graceful degradation (e.g., wrong key, corrupted data)
        """
        if not CRYPTO_AVAILABLE:
            logger.warning("Encryption not available - returning None")
            return None
        if self._aesgcm is None:
            logger.warning("Encryption key not derived - returning None")
            return None

        data = EncryptedData.from_string(encrypted)
        if data is None:
            # Not an encrypted field or invalid format
            return None

        try:
            plaintext_bytes = self._aesgcm.decrypt(data.nonce, data.ciphertext, None)
            return plaintext_bytes.decode('utf-8')
        except (InvalidTag, ValueError) as e:
            # Decryption failed - wrong key, corrupted data, or tampered
            logger.warning(f"Decryption failed: {e}")
            return None

    def is_encrypted(self, value: str) -> bool:
        """Check if a value is in encrypted format."""
        return value.startswith(ENCRYPTED_PREFIX)

    def encrypt_if_unlocked(self, plaintext: str) -> str:
        """Encrypt if the key is available, otherwise return plaintext.

        This allows gradual migration - fields are encrypted when the
        app is unlocked, but still readable when encryption is disabled.
        """
        if self.is_unlocked and CRYPTO_AVAILABLE:
            return self.encrypt_field(plaintext)
        return plaintext

    def decrypt_if_encrypted(self, value: str) -> str:
        """Decrypt if the value is encrypted, otherwise return as-is.

        This allows reading both encrypted and plaintext values during migration.
        When the app is locked or decryption fails, returns LOCKED_PLACEHOLDER
        instead of gibberish encrypted data.
        """
        if self.is_encrypted(value):
            # If app is locked, return placeholder immediately
            if not self.is_unlocked:
                return LOCKED_PLACEHOLDER
            decrypted = self.decrypt_field(value)
            if decrypted is not None:
                return decrypted
            # Decryption failed (wrong key, corrupted data) - return placeholder
            return LOCKED_PLACEHOLDER
        return value

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance.

        Note: This method is primarily used for testing to ensure
        a fresh CryptoService instance between test cases. Not typically
        called in production code.
        """
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.lock()
                cls._instance = None


# ============================================================================
# Key Wrapping for Biometric Storage
# ============================================================================

def wrap_key_for_biometric(encryption_key: bytes, biometric_secret: bytes, salt: bytes) -> str:
    """Wrap (encrypt) the encryption key for secure biometric storage.

    Instead of storing the raw encryption key in the OS keyring, we:
    1. Derive a wrapping key from the biometric secret + salt
    2. Encrypt the encryption key with AES-GCM using the wrapping key
    3. Store the wrapped key in the database (not the raw key)

    This way, compromising the keyring alone doesn't reveal the encryption key.

    Args:
        encryption_key: The AES-256 encryption key to wrap
        biometric_secret: Random secret stored in OS keyring
        salt: Salt stored in database

    Returns:
        Base64-encoded wrapped key (nonce + ciphertext)
    """
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("Encryption not available")

    # Derive wrapping key from biometric secret
    wrapping_key = derive_key_pbkdf2(biometric_secret.hex(), salt)

    # Wrap the encryption key with AES-GCM
    aesgcm = AESGCM(wrapping_key)
    nonce = secrets.token_bytes(GCM_NONCE_SIZE)
    wrapped = aesgcm.encrypt(nonce, encryption_key, None)

    # Combine nonce + wrapped key
    combined = nonce + wrapped
    return base64.b64encode(combined).decode('utf-8')


def unwrap_key_from_biometric(wrapped_key_b64: str, biometric_secret: bytes, salt: bytes) -> Optional[bytes]:
    """Unwrap (decrypt) the encryption key from biometric storage.

    Args:
        wrapped_key_b64: Base64-encoded wrapped key from database
        biometric_secret: Secret retrieved from OS keyring
        salt: Salt stored in database

    Returns:
        The unwrapped encryption key, or None if unwrapping fails
    """
    if not CRYPTO_AVAILABLE:
        return None

    try:
        combined = base64.b64decode(wrapped_key_b64)
        if len(combined) < GCM_NONCE_SIZE + GCM_TAG_SIZE:
            return None

        nonce = combined[:GCM_NONCE_SIZE]
        wrapped = combined[GCM_NONCE_SIZE:]

        # Derive wrapping key from biometric secret
        wrapping_key = derive_key_pbkdf2(biometric_secret.hex(), salt)

        # Unwrap the encryption key
        aesgcm = AESGCM(wrapping_key)
        return aesgcm.decrypt(nonce, wrapped, None)
    except (InvalidTag, ValueError) as e:
        logger.warning(f"Key unwrapping failed: {e}")
        return None


def generate_biometric_secret() -> bytes:
    """Generate a cryptographically secure random secret for biometric storage."""
    return secrets.token_bytes(32)  # 256-bit secret


# ============================================================================
# Module-level singleton instance
# ============================================================================

crypto = CryptoService()
