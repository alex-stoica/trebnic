"""
Authentication service for Trebnic.

This module provides:
- Master password setup and verification
- App lock/unlock state management
- Passkey/WebAuthn integration (placeholder for OS biometrics)

Authentication Flow:
1. First-time setup: User creates master password
2. App stores: salt + key verification hash (NOT the password or key)
3. On launch: User enters password -> derive key -> verify -> unlock
4. Optional: Use passkey/biometrics to unlock (stores key in OS keychain)

Security Model:
- Master password never stored
- Encryption key derived at runtime, held only in memory
- Passkeys use OS-level secure storage (Keychain/Credential Manager)
"""
import base64
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Awaitable

from services.crypto import crypto, generate_salt, CRYPTO_AVAILABLE

logger = logging.getLogger(__name__)


# ============================================================================
# Settings Keys (stored in database.settings table)
# ============================================================================

SETTING_ENCRYPTION_ENABLED = "encryption_enabled"
SETTING_ENCRYPTION_SALT = "encryption_salt"           # Base64 encoded salt
SETTING_KEY_VERIFICATION = "encryption_key_hash"      # Verification hash
SETTING_PASSKEY_ENABLED = "passkey_enabled"           # Whether passkey is set up
SETTING_KDF_METHOD = "encryption_kdf_method"          # "argon2" or "pbkdf2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class AuthState(Enum):
    """Current authentication state of the app."""
    NOT_CONFIGURED = "not_configured"  # First launch, no master password set
    LOCKED = "locked"                   # Master password set, app locked
    UNLOCKED = "unlocked"               # App unlocked, encryption key available


class AuthError(Exception):
    """Authentication-related error."""
    pass


@dataclass
class AuthConfig:
    """Authentication configuration stored in settings."""
    encryption_enabled: bool
    salt: Optional[bytes]
    key_verification_hash: Optional[str]
    passkey_enabled: bool
    kdf_method: str  # "argon2" or "pbkdf2"

    @classmethod
    def not_configured(cls) -> "AuthConfig":
        """Return a default config for first-time setup."""
        return cls(
            encryption_enabled=False,
            salt=None,
            key_verification_hash=None,
            passkey_enabled=False,
            kdf_method="argon2" if crypto.uses_argon2 else "pbkdf2"
        )


# ============================================================================
# Passkey / WebAuthn Integration (Placeholder)
# ============================================================================

# TODO: Implement actual WebAuthn/Passkey integration
#
# For Flet apps, this would involve:
#
# 1. Desktop (Windows/macOS/Linux):
#    - Use platform credential manager APIs
#    - Windows: Windows Hello / Credential Manager
#    - macOS: Keychain Services + Touch ID
#    - Linux: libsecret / GNOME Keyring
#
# 2. Mobile (iOS/Android):
#    - iOS: Local Authentication framework (Face ID / Touch ID)
#    - Android: BiometricPrompt API
#
# 3. Web:
#    - WebAuthn API for browser-based passkeys
#    - navigator.credentials.create() / get()
#
# The flow would be:
# 1. User sets up master password (derives key)
# 2. User opts to enable biometrics
# 3. Store encrypted key in OS secure storage (protected by biometrics)
# 4. On next launch, biometrics unlocks access to stored key
#
# For now, this is a placeholder that always returns False for availability


class PasskeyService:
    """
    Placeholder for OS-level biometric authentication.

    This will integrate with:
    - Windows Hello (Windows)
    - Touch ID / Face ID (macOS/iOS)
    - BiometricPrompt (Android)
    - Fingerprint/Face unlock (Linux if available)

    The actual implementation requires platform-specific code
    and potentially Flet native extensions.
    """

    def __init__(self) -> None:
        self._available: Optional[bool] = None

    @property
    def is_available(self) -> bool:
        """Check if passkey/biometric authentication is available on this platform."""
        # TODO: Implement platform detection
        #
        # This would check:
        # - Platform capabilities (has TouchID, Windows Hello, etc.)
        # - User has enrolled biometrics
        # - App has necessary permissions
        #
        # For now, always return False until implemented
        return False

    async def store_key_for_biometric(self, key: bytes, user_id: str) -> bool:
        """Store encryption key in OS secure storage, protected by biometrics.

        Args:
            key: The derived encryption key to store
            user_id: Identifier for this key (e.g., "trebnic-master-key")

        Returns:
            True if stored successfully, False otherwise

        The stored key can only be retrieved after biometric verification.
        """
        # TODO: Implement platform-specific secure storage
        #
        # macOS example (using keychain):
        #   import keyring
        #   keyring.set_password("trebnic", user_id, base64.b64encode(key).decode())
        #
        # Windows example (using Windows Credential Manager):
        #   import keyring
        #   keyring.set_password("trebnic", user_id, base64.b64encode(key).decode())
        #
        # The keyring library provides cross-platform support, but biometric
        # protection requires additional platform-specific configuration.
        logger.warning("Passkey storage not implemented")
        return False

    async def retrieve_key_with_biometric(self, user_id: str) -> Optional[bytes]:
        """Retrieve encryption key from OS secure storage using biometrics.

        Args:
            user_id: Identifier for the key to retrieve

        Returns:
            The encryption key if biometric auth succeeds, None otherwise

        This will prompt the user for biometric verification (fingerprint, face, etc.)
        """
        # TODO: Implement platform-specific retrieval with biometric prompt
        logger.warning("Passkey retrieval not implemented")
        return None

    async def delete_stored_key(self, user_id: str) -> bool:
        """Delete stored encryption key (when user disables biometrics)."""
        # TODO: Implement
        logger.warning("Passkey deletion not implemented")
        return False


# ============================================================================
# AuthService Class
# ============================================================================

class AuthService:
    """
    Main authentication service managing app lock/unlock state.

    This service coordinates between:
    - CryptoService (key derivation and encryption)
    - PasskeyService (biometric authentication)
    - Database settings (stored configuration)

    Usage:
        auth = AuthService(get_setting, set_setting)

        # First-time setup
        await auth.setup_master_password("user_password")

        # Subsequent launches
        await auth.load_config()
        if auth.state == AuthState.LOCKED:
            success = await auth.unlock_with_password("user_password")

        # Use encryption
        if auth.is_unlocked:
            encrypted = crypto.encrypt_field("sensitive data")
    """

    _instance: Optional["AuthService"] = None

    def __new__(cls, *args, **kwargs) -> "AuthService":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        get_setting: Callable[[str, any], Awaitable[any]],
        set_setting: Callable[[str, any], Awaitable[None]]
    ) -> None:
        """Initialize the auth service.

        Args:
            get_setting: Async function to read settings from database
            set_setting: Async function to write settings to database
        """
        if self._initialized:
            return

        self._get_setting = get_setting
        self._set_setting = set_setting
        self._config: AuthConfig = AuthConfig.not_configured()
        self._state: AuthState = AuthState.NOT_CONFIGURED
        self._passkey = PasskeyService()
        self._initialized = True

    @property
    def state(self) -> AuthState:
        """Current authentication state."""
        return self._state

    @property
    def is_unlocked(self) -> bool:
        """Check if the app is unlocked and encryption key is available."""
        return self._state == AuthState.UNLOCKED and crypto.is_unlocked

    @property
    def is_encryption_enabled(self) -> bool:
        """Check if encryption has been configured."""
        return self._config.encryption_enabled

    @property
    def is_passkey_available(self) -> bool:
        """Check if passkey/biometric auth is available on this platform."""
        return self._passkey.is_available

    @property
    def is_passkey_enabled(self) -> bool:
        """Check if passkey/biometric auth is enabled for this user."""
        return self._config.passkey_enabled and self._passkey.is_available

    @property
    def is_crypto_available(self) -> bool:
        """Check if the cryptography library is installed."""
        return CRYPTO_AVAILABLE

    async def load_config(self) -> None:
        """Load authentication configuration from database settings.

        Call this on app startup to determine initial auth state.
        """
        encryption_enabled = await self._get_setting(SETTING_ENCRYPTION_ENABLED, False)
        salt_b64 = await self._get_setting(SETTING_ENCRYPTION_SALT, None)
        key_hash = await self._get_setting(SETTING_KEY_VERIFICATION, None)
        passkey_enabled = await self._get_setting(SETTING_PASSKEY_ENABLED, False)
        kdf_method = await self._get_setting(
            SETTING_KDF_METHOD,
            "argon2" if crypto.uses_argon2 else "pbkdf2"
        )

        salt = base64.b64decode(salt_b64) if salt_b64 else None

        self._config = AuthConfig(
            encryption_enabled=encryption_enabled,
            salt=salt,
            key_verification_hash=key_hash,
            passkey_enabled=passkey_enabled,
            kdf_method=kdf_method
        )

        # Determine initial state
        if not encryption_enabled or salt is None or key_hash is None:
            self._state = AuthState.NOT_CONFIGURED
        else:
            self._state = AuthState.LOCKED

    async def setup_master_password(self, password: str) -> None:
        """Set up encryption with a new master password.

        This should be called during first-time setup.
        After calling this, the app is unlocked and encryption is enabled.

        Args:
            password: The user's chosen master password

        Raises:
            AuthError: If encryption library is not available
        """
        if not CRYPTO_AVAILABLE:
            raise AuthError(
                "Encryption not available. Install 'cryptography' package: "
                "pip install cryptography"
            )

        # Generate new salt
        salt = generate_salt()

        # Derive key and get verification hash
        crypto.derive_key_from_password(password, salt)
        key_hash = crypto.get_key_verification_hash()

        # Determine KDF method used
        kdf_method = "argon2" if crypto.uses_argon2 else "pbkdf2"

        # Save to settings
        await self._set_setting(SETTING_ENCRYPTION_ENABLED, True)
        await self._set_setting(SETTING_ENCRYPTION_SALT, base64.b64encode(salt).decode('utf-8'))
        await self._set_setting(SETTING_KEY_VERIFICATION, key_hash)
        await self._set_setting(SETTING_KDF_METHOD, kdf_method)

        # Update local config
        self._config = AuthConfig(
            encryption_enabled=True,
            salt=salt,
            key_verification_hash=key_hash,
            passkey_enabled=False,
            kdf_method=kdf_method
        )
        self._state = AuthState.UNLOCKED

    async def unlock_with_password(self, password: str) -> bool:
        """Unlock the app with the master password.

        Args:
            password: The user's master password

        Returns:
            True if unlock succeeded, False if password is wrong
        """
        if self._config.salt is None or self._config.key_verification_hash is None:
            logger.error("Cannot unlock - encryption not configured")
            return False

        # Derive key from password
        crypto.derive_key_from_password(password, self._config.salt)

        # Verify the key
        if not crypto.verify_key(self._config.key_verification_hash):
            crypto.lock()  # Clear the wrong key
            return False

        self._state = AuthState.UNLOCKED
        return True

    async def unlock_with_passkey(self) -> bool:
        """Unlock the app using biometric authentication.

        Returns:
            True if unlock succeeded, False otherwise
        """
        if not self._passkey.is_available or not self._config.passkey_enabled:
            return False

        # TODO: Implement biometric unlock
        # key = await self._passkey.retrieve_key_with_biometric("trebnic-master-key")
        # if key is None:
        #     return False
        # crypto._key = key
        # crypto._aesgcm = AESGCM(key)
        # self._state = AuthState.UNLOCKED
        # return True

        return False

    def lock(self) -> None:
        """Lock the app, clearing the encryption key from memory."""
        crypto.lock()
        if self._config.encryption_enabled:
            self._state = AuthState.LOCKED
        else:
            self._state = AuthState.NOT_CONFIGURED

    async def change_master_password(
        self,
        old_password: str,
        new_password: str,
        reencrypt_data_fn: Optional[Callable[
            [Callable[[str], Optional[str]], Callable[[str], str]],
            Awaitable[tuple]
        ]] = None
    ) -> bool:
        """Change the master password.

        This re-encrypts all data with the new key.

        Args:
            old_password: Current master password (for verification)
            new_password: New master password to set
            reencrypt_data_fn: Optional async function to re-encrypt data.
                              Signature: (decrypt_fn, encrypt_fn) -> (tasks_count, projects_count)
                              If not provided, only password is changed (data loss warning!).

        Returns:
            True if password changed successfully, False if old password wrong
        """
        # Verify old password and derive old key
        if not await self.unlock_with_password(old_password):
            return False

        # Store old key reference for decryption during re-encryption
        old_key = crypto._key
        old_aesgcm = crypto._aesgcm

        # Create decrypt function that uses the old key
        def decrypt_with_old_key(encrypted: str) -> Optional[str]:
            """Decrypt a value using the old key."""
            from services.crypto import EncryptedData, CRYPTO_AVAILABLE
            if not CRYPTO_AVAILABLE or old_aesgcm is None:
                return None
            data = EncryptedData.from_string(encrypted)
            if data is None:
                return None
            try:
                plaintext_bytes = old_aesgcm.decrypt(data.nonce, data.ciphertext, None)
                return plaintext_bytes.decode('utf-8')
            except Exception as e:
                logger.warning(f"Decryption with old key failed: {e}")
                return None

        # Generate new salt and derive new key
        salt = generate_salt()
        crypto.derive_key_from_password(new_password, salt)
        key_hash = crypto.get_key_verification_hash()
        kdf_method = "argon2" if crypto.uses_argon2 else "pbkdf2"

        # Create encrypt function that uses the new key
        def encrypt_with_new_key(plaintext: str) -> str:
            """Encrypt a value using the new key."""
            return crypto.encrypt_field(plaintext)

        # Re-encrypt all data if function provided
        if reencrypt_data_fn is not None:
            try:
                tasks_count, projects_count = await reencrypt_data_fn(
                    decrypt_with_old_key,
                    encrypt_with_new_key
                )
                logger.info(f"Re-encrypted {tasks_count} tasks and {projects_count} projects")
            except Exception as e:
                # Rollback: restore old key
                crypto._key = old_key
                crypto._aesgcm = old_aesgcm
                logger.error(f"Re-encryption failed, rolled back: {e}")
                raise

        # Save new credentials to settings
        await self._set_setting(SETTING_ENCRYPTION_SALT, base64.b64encode(salt).decode('utf-8'))
        await self._set_setting(SETTING_KEY_VERIFICATION, key_hash)
        await self._set_setting(SETTING_KDF_METHOD, kdf_method)

        # Update local config
        self._config.salt = salt
        self._config.key_verification_hash = key_hash
        self._config.kdf_method = kdf_method

        logger.info("Master password changed successfully")
        return True

    async def disable_encryption(
        self,
        password: str,
        decrypt_data_fn: Optional[Callable[
            [Callable[[str], Optional[str]], Callable[[str], str]],
            Awaitable[tuple]
        ]] = None
    ) -> bool:
        """Disable encryption and remove master password.

        This decrypts all data before disabling encryption so data is preserved.

        Args:
            password: Master password for verification
            decrypt_data_fn: Optional async function to decrypt all data.
                            Signature: (decrypt_fn, identity_fn) -> (tasks_count, projects_count)
                            If not provided, encrypted data will become unreadable.

        Returns:
            True if disabled successfully, False if password wrong
        """
        # Verify password
        if not await self.unlock_with_password(password):
            return False

        # Decrypt all data if function provided
        if decrypt_data_fn is not None:
            def decrypt_fn(encrypted: str) -> Optional[str]:
                return crypto.decrypt_field(encrypted)

            def identity_fn(plaintext: str) -> str:
                """Return plaintext as-is (no encryption)."""
                return plaintext

            try:
                tasks_count, projects_count = await decrypt_data_fn(decrypt_fn, identity_fn)
                logger.info(f"Decrypted {tasks_count} tasks and {projects_count} projects")
            except Exception as e:
                logger.error(f"Failed to decrypt data: {e}")
                raise

        await self._set_setting(SETTING_ENCRYPTION_ENABLED, False)
        await self._set_setting(SETTING_ENCRYPTION_SALT, None)
        await self._set_setting(SETTING_KEY_VERIFICATION, None)
        await self._set_setting(SETTING_PASSKEY_ENABLED, False)

        crypto.lock()
        self._config = AuthConfig.not_configured()
        self._state = AuthState.NOT_CONFIGURED

        logger.info("Encryption disabled")
        return True

    async def enable_passkey(self, password: str) -> bool:
        """Enable biometric/passkey authentication.

        Args:
            password: Master password (needed to store key securely)

        Returns:
            True if enabled successfully
        """
        if not self._passkey.is_available:
            logger.warning("Passkey not available on this platform")
            return False

        # Verify password and get key
        if not await self.unlock_with_password(password):
            return False

        # TODO: Store key in secure storage
        # success = await self._passkey.store_key_for_biometric(
        #     crypto._key,
        #     "trebnic-master-key"
        # )
        # if not success:
        #     return False

        await self._set_setting(SETTING_PASSKEY_ENABLED, True)
        self._config.passkey_enabled = True

        logger.info("Passkey enabled")
        return True

    async def disable_passkey(self) -> bool:
        """Disable biometric/passkey authentication."""
        # Delete stored key
        await self._passkey.delete_stored_key("trebnic-master-key")

        await self._set_setting(SETTING_PASSKEY_ENABLED, False)
        self._config.passkey_enabled = False

        logger.info("Passkey disabled")
        return True


# ============================================================================
# Module-level factory (lazy initialization)
# ============================================================================

_auth_instance: Optional[AuthService] = None


def get_auth_service(
    get_setting: Callable[[str, Any], Awaitable[Any]],
    set_setting: Callable[[str, Any], Awaitable[None]]
) -> AuthService:
    """Get or create the AuthService singleton.

    Args:
        get_setting: Database get_setting function
        set_setting: Database set_setting function

    Returns:
        The AuthService singleton instance
    """
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = AuthService(get_setting, set_setting)
    return _auth_instance
