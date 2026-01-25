"""
Authentication service for Trebnic.

This module provides:
- Master password setup and verification
- App lock/unlock state management
- Biometric authentication via OS keychains (Windows Hello, Touch ID, etc.)

Authentication Flow:
1. First-time setup: User creates master password
2. App stores: salt + key verification hash (NOT the password or key)
3. On launch: User enters password -> derive key -> verify -> unlock
4. Optional: Use biometrics to unlock (stores key in OS keychain)

Security Model:
- Master password never stored
- Encryption key derived at runtime, held only in memory
- Biometric unlock uses OS-level secure storage (Keychain/Credential Manager)
"""
import asyncio
import base64
import logging
import platform
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Awaitable

from services.crypto import (
    crypto,
    generate_salt,
    CRYPTO_AVAILABLE,
    wrap_key_for_biometric,
    unwrap_key_from_biometric,
    generate_biometric_secret,
)

# Cross-platform keyring for secure credential storage
try:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    KeyringError = Exception
    PasswordDeleteError = Exception

# macOS Touch ID support via pyobjc
TOUCHID_AVAILABLE = False
if sys.platform == "darwin":
    try:
        import objc
        from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthenticationWithBiometrics
        TOUCHID_AVAILABLE = True
    except ImportError:
        pass

# Windows Hello support detection
WINDOWS_HELLO_AVAILABLE = False
if sys.platform == "win32":
    try:
        # Check if Windows Hello APIs are available (Windows 10+)
        _winrt_available = False
        try:
            import winrt.windows.security.credentials.ui as wincred_ui
            _winrt_available = True
            WINDOWS_HELLO_AVAILABLE = True
        except ImportError:
            # Try alternative: check via registry or other means
            # Windows Hello is available on Windows 10 1607+ with compatible hardware
            pass
    except (ImportError, OSError, ValueError) as e:
        logger.debug(f"Windows Hello availability check failed: {e}")

# Android biometric support detection via pyjnius
ANDROID_BIOMETRIC_AVAILABLE = False
_is_android = False

def _detect_android() -> bool:
    """Detect if running on Android."""
    # Method 1: Check for Android-specific paths
    import os
    if os.path.exists("/system/build.prop"):
        return True
    # Method 2: Check ANDROID_ROOT env variable
    if os.environ.get("ANDROID_ROOT"):
        return True
    # Method 3: Try importing android module (Kivy/P4A)
    try:
        import android
        return True
    except ImportError:
        pass
    return False

_is_android = _detect_android()

if _is_android:
    try:
        from jnius import autoclass
        ANDROID_BIOMETRIC_AVAILABLE = True
    except ImportError:
        pass

logger = logging.getLogger(__name__)


# ============================================================================
# Settings Keys (stored in database.settings table)
# ============================================================================

SETTING_ENCRYPTION_ENABLED = "encryption_enabled"
SETTING_ENCRYPTION_SALT = "encryption_salt"           # Base64 encoded salt
SETTING_KEY_VERIFICATION = "encryption_key_hash"      # Verification hash
SETTING_PASSKEY_ENABLED = "passkey_enabled"           # Whether passkey is set up
SETTING_KDF_METHOD = "encryption_kdf_method"          # "argon2" or "pbkdf2"
SETTING_BIOMETRIC_WRAPPED_KEY = "biometric_wrapped_key"  # Wrapped encryption key (not raw)
SETTING_BIOMETRIC_SALT = "biometric_salt"             # Salt for key wrapping


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
# Biometric Authentication Service
# ============================================================================

# Service name for keyring storage
KEYRING_SERVICE = "trebnic"
KEYRING_KEY_ID = "master-key"


class BiometricResult(Enum):
    """Result of biometric authentication attempt."""
    SUCCESS = "success"
    CANCELLED = "cancelled"
    NOT_ENROLLED = "not_enrolled"
    NOT_AVAILABLE = "not_available"
    FAILED = "failed"
    LOCKOUT = "lockout"


def _check_windows_hello_available() -> bool:
    """Check if Windows Hello is available and configured."""
    if sys.platform != "win32":
        return False

    if not KEYRING_AVAILABLE:
        return False

    # Try using winrt to check Windows Hello availability
    try:
        import winrt.windows.security.credentials.ui as wincred_ui
        from winrt.windows.security.credentials.ui import (
            UserConsentVerifierAvailability,
            UserConsentVerifier,
        )

        # Run async check synchronously
        async def check():
            availability = await UserConsentVerifier.check_availability_async()
            return availability == UserConsentVerifierAvailability.AVAILABLE

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(check())
        finally:
            loop.close()
    except ImportError:
        # winrt not available, check via alternative method
        # Windows Hello requires Windows 10 1607+ with TPM or camera
        try:
            # Check Windows version (10.0.14393 = Windows 10 1607)
            version = platform.version()
            major, minor, build = map(int, version.split(".")[:3])
            if major >= 10 and build >= 14393:
                # Windows 10 1607+, Windows Hello might be available
                # We can't definitively check without winrt, so return True
                # and let the actual auth attempt handle failures
                return True
        except (ValueError, AttributeError):
            pass
    except Exception as e:
        logger.debug(f"Windows Hello check failed: {e}")

    return False


def _check_touchid_available() -> bool:
    """Check if Touch ID / Face ID is available on macOS."""
    if sys.platform != "darwin" or not TOUCHID_AVAILABLE:
        return False

    try:
        context = LAContext.alloc().init()
        error = None
        can_evaluate = context.canEvaluatePolicy_error_(
            LAPolicyDeviceOwnerAuthenticationWithBiometrics,
            error
        )
        return can_evaluate
    except Exception as e:
        logger.debug(f"Touch ID check failed: {e}")
        return False


async def _prompt_windows_hello(reason: str) -> BiometricResult:
    """Prompt for Windows Hello authentication.

    Args:
        reason: Message shown to user explaining why auth is needed

    Returns:
        BiometricResult indicating success or failure reason
    """
    try:
        import winrt.windows.security.credentials.ui as wincred_ui
        from winrt.windows.security.credentials.ui import (
            UserConsentVerificationResult,
            UserConsentVerifier,
        )

        result = await UserConsentVerifier.request_verification_async(reason)

        if result == UserConsentVerificationResult.VERIFIED:
            return BiometricResult.SUCCESS
        elif result == UserConsentVerificationResult.CANCELED:
            return BiometricResult.CANCELLED
        elif result == UserConsentVerificationResult.DEVICE_NOT_PRESENT:
            return BiometricResult.NOT_AVAILABLE
        elif result == UserConsentVerificationResult.NOT_CONFIGURED_FOR_USER:
            return BiometricResult.NOT_ENROLLED
        elif result == UserConsentVerificationResult.RETRIES_EXHAUSTED:
            return BiometricResult.LOCKOUT
        else:
            return BiometricResult.FAILED

    except ImportError:
        logger.warning("winrt package not installed for Windows Hello support")
        return BiometricResult.NOT_AVAILABLE
    except Exception as e:
        logger.error(f"Windows Hello authentication failed: {e}")
        return BiometricResult.FAILED


async def _prompt_touchid(reason: str) -> BiometricResult:
    """Prompt for Touch ID / Face ID authentication on macOS.

    Args:
        reason: Message shown to user explaining why auth is needed

    Returns:
        BiometricResult indicating success or failure reason
    """
    if not TOUCHID_AVAILABLE:
        return BiometricResult.NOT_AVAILABLE

    try:
        context = LAContext.alloc().init()

        # Check if biometrics are available
        error = None
        can_evaluate = context.canEvaluatePolicy_error_(
            LAPolicyDeviceOwnerAuthenticationWithBiometrics,
            error
        )

        if not can_evaluate:
            return BiometricResult.NOT_ENROLLED

        # Perform authentication - this runs on a background thread
        # and blocks until user responds
        def evaluate_sync():
            result = {"success": False, "error": None}

            def callback(success, auth_error):
                result["success"] = success
                result["error"] = auth_error

            context.evaluatePolicy_localizedReason_reply_(
                LAPolicyDeviceOwnerAuthenticationWithBiometrics,
                reason,
                callback
            )
            # Note: The callback is called asynchronously by the system
            # We need to use a different approach for proper async handling

        # Use asyncio to run the blocking call in a thread
        loop = asyncio.get_event_loop()

        # Create a future to get the result
        future = loop.create_future()

        def run_auth():
            try:
                success_holder = [False]
                error_holder = [None]
                done_event = threading.Event()

                def callback(success, auth_error):
                    success_holder[0] = success
                    error_holder[0] = auth_error
                    done_event.set()

                context.evaluatePolicy_localizedReason_reply_(
                    LAPolicyDeviceOwnerAuthenticationWithBiometrics,
                    reason,
                    callback
                )

                # Wait for callback (with timeout)
                done_event.wait(timeout=60)

                if success_holder[0]:
                    loop.call_soon_threadsafe(future.set_result, BiometricResult.SUCCESS)
                elif error_holder[0]:
                    error_code = error_holder[0].code()
                    if error_code == -2:  # LAErrorUserCancel
                        loop.call_soon_threadsafe(future.set_result, BiometricResult.CANCELLED)
                    elif error_code == -5:  # LAErrorPasscodeNotSet
                        loop.call_soon_threadsafe(future.set_result, BiometricResult.NOT_ENROLLED)
                    elif error_code == -8:  # LAErrorBiometryLockout
                        loop.call_soon_threadsafe(future.set_result, BiometricResult.LOCKOUT)
                    else:
                        loop.call_soon_threadsafe(future.set_result, BiometricResult.FAILED)
                else:
                    loop.call_soon_threadsafe(future.set_result, BiometricResult.FAILED)
            except Exception as e:
                logger.error(f"Touch ID thread error: {e}")
                loop.call_soon_threadsafe(future.set_result, BiometricResult.FAILED)

        thread = threading.Thread(target=run_auth, daemon=True)
        thread.start()

        return await future

    except Exception as e:
        logger.error(f"Touch ID authentication failed: {e}")
        return BiometricResult.FAILED


def _check_android_biometric_available() -> bool:
    """Check if Android biometric authentication is available."""
    if not _is_android or not ANDROID_BIOMETRIC_AVAILABLE:
        return False

    try:
        from jnius import autoclass

        Context = autoclass("android.content.Context")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        BiometricManager = autoclass("androidx.biometric.BiometricManager")

        activity = PythonActivity.mActivity
        biometric_manager = BiometricManager.from_(activity)

        # Check if biometrics can be used
        result = biometric_manager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)
        return result == BiometricManager.BIOMETRIC_SUCCESS

    except Exception as e:
        logger.debug(f"Android biometric check failed: {e}")
        return False


async def _prompt_android_biometric(reason: str) -> BiometricResult:
    """Prompt for Android biometric authentication (fingerprint/face).

    Args:
        reason: Message shown to user explaining why auth is needed

    Returns:
        BiometricResult indicating success or failure reason
    """
    if not _is_android or not ANDROID_BIOMETRIC_AVAILABLE:
        return BiometricResult.NOT_AVAILABLE

    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        BiometricPrompt = autoclass("androidx.biometric.BiometricPrompt")
        BiometricPromptInfo = autoclass("androidx.biometric.BiometricPrompt$PromptInfo")
        Executors = autoclass("java.util.concurrent.Executors")

        activity = PythonActivity.mActivity

        # Use asyncio to bridge Java callback with Python
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def run_biometric():
            try:
                # Create callback class
                from jnius import PythonJavaClass, java_method

                class BiometricCallback(PythonJavaClass):
                    __javainterfaces__ = ["androidx/biometric/BiometricPrompt$AuthenticationCallback"]

                    @java_method("(Landroidx/biometric/BiometricPrompt$AuthenticationResult;)V")
                    def onAuthenticationSucceeded(self, result):
                        loop.call_soon_threadsafe(future.set_result, BiometricResult.SUCCESS)

                    @java_method("(ILjava/lang/CharSequence;)V")
                    def onAuthenticationError(self, error_code, err_string):
                        if error_code == 10:  # ERROR_USER_CANCELED
                            loop.call_soon_threadsafe(future.set_result, BiometricResult.CANCELLED)
                        elif error_code == 7:  # ERROR_LOCKOUT
                            loop.call_soon_threadsafe(future.set_result, BiometricResult.LOCKOUT)
                        elif error_code == 11:  # ERROR_NO_BIOMETRICS
                            loop.call_soon_threadsafe(future.set_result, BiometricResult.NOT_ENROLLED)
                        else:
                            loop.call_soon_threadsafe(future.set_result, BiometricResult.FAILED)

                    @java_method("()V")
                    def onAuthenticationFailed(self):
                        # Single failure (wrong finger), prompt stays open
                        pass

                callback = BiometricCallback()
                executor = Executors.newSingleThreadExecutor()
                prompt = BiometricPrompt(activity, executor, callback)

                # Build prompt info
                prompt_info = (
                    BiometricPromptInfo.Builder()
                    .setTitle("Unlock Trebnic")
                    .setSubtitle(reason)
                    .setNegativeButtonText("Cancel")
                    .build()
                )

                # Must run on UI thread
                activity.runOnUiThread(lambda: prompt.authenticate(prompt_info))

            except Exception as e:
                logger.error(f"Android biometric thread error: {e}")
                loop.call_soon_threadsafe(future.set_result, BiometricResult.FAILED)

        thread = threading.Thread(target=run_biometric, daemon=True)
        thread.start()

        return await future

    except Exception as e:
        logger.error(f"Android biometric authentication failed: {e}")
        return BiometricResult.FAILED


class PasskeyService:
    """
    OS-level biometric authentication service.

    Provides cross-platform biometric unlock using:
    - Windows Hello (Windows 10+)
    - Touch ID / Face ID (macOS)
    - Keyring-only fallback (Linux)

    The encryption key is stored in the OS keychain (Credential Manager on Windows,
    Keychain on macOS, libsecret on Linux). On platforms with biometric support,
    a biometric prompt is shown before the key is retrieved.

    Security Model:
    - Key is stored encrypted in OS-level secure storage
    - On Windows/macOS, biometric verification is required before retrieval
    - On Linux, keychain access control depends on the desktop environment
    - If biometrics fail, user falls back to master password

    Usage:
        passkey = PasskeyService()

        if passkey.is_available:
            # Store key after password unlock
            await passkey.store_key_for_biometric(crypto._key, "trebnic-master-key")

            # Later, retrieve with biometric prompt
            key = await passkey.retrieve_key_with_biometric("trebnic-master-key")
            if key is not None:
                # Use key to unlock app
    """

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._biometric_type: Optional[str] = None

    def _detect_availability(self) -> tuple[bool, Optional[str]]:
        """Detect biometric availability and type.

        Returns:
            Tuple of (is_available, biometric_type)
        """
        if not KEYRING_AVAILABLE:
            logger.debug("Keyring not available - biometric auth disabled")
            return False, None

        # Check Android first (sys.platform is "linux" on Android)
        if _is_android:
            if _check_android_biometric_available():
                return True, "Fingerprint"
            # Android without biometric hardware - use keyring only
            return True, "Keyring"

        if sys.platform == "win32":
            if _check_windows_hello_available():
                return True, "Windows Hello"
        elif sys.platform == "darwin":
            if _check_touchid_available():
                return True, "Touch ID"
        elif sys.platform.startswith("linux"):
            # Linux has keyring but typically no standard biometric API
            # Return True for keyring-only mode (no biometric prompt)
            return True, "Keyring"

        return False, None

    @property
    def is_available(self) -> bool:
        """Check if biometric authentication is available on this platform.

        Returns True if:
        - keyring library is installed
        - Platform has biometric support (Windows Hello, Touch ID) OR
        - Platform supports secure keyring storage (Linux fallback)
        """
        if self._available is None:
            self._available, self._biometric_type = self._detect_availability()
            if self._available:
                logger.info(f"Biometric auth available: {self._biometric_type}")
            else:
                logger.info("Biometric auth not available")
        return self._available

    @property
    def biometric_type(self) -> Optional[str]:
        """Get the type of biometric authentication available."""
        if self._available is None:
            self._available, self._biometric_type = self._detect_availability()
        return self._biometric_type

    async def store_key_for_biometric(
        self,
        key: bytes,
        user_id: str,
        set_setting: Callable[[str, Any], Awaitable[None]],
    ) -> bool:
        """Store encryption key using key wrapping for biometric unlock.

        Security: Instead of storing the raw encryption key in the keyring, we:
        1. Generate a random biometric secret
        2. Store only the biometric secret in the OS keyring
        3. Wrap (encrypt) the encryption key with a key derived from the secret
        4. Store the wrapped key in the database

        This way, compromising the keyring alone doesn't reveal the encryption key.
        An attacker would need both the keyring AND the database.

        Args:
            key: The derived encryption key to protect
            user_id: Identifier for this key (e.g., "trebnic-master-key")
            set_setting: Async function to save settings to database

        Returns:
            True if stored successfully, False otherwise
        """
        if not KEYRING_AVAILABLE:
            logger.warning("Keyring not available - cannot store key")
            return False

        try:
            # Generate random biometric secret and salt
            biometric_secret = generate_biometric_secret()
            biometric_salt = generate_salt()

            # Wrap the encryption key
            wrapped_key = wrap_key_for_biometric(key, biometric_secret, biometric_salt)

            # Store biometric secret in keyring (NOT the raw key)
            secret_b64 = base64.b64encode(biometric_secret).decode('utf-8')
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: keyring.set_password(KEYRING_SERVICE, user_id, secret_b64)
            )

            # Store wrapped key and salt in database
            await set_setting(SETTING_BIOMETRIC_WRAPPED_KEY, wrapped_key)
            await set_setting(SETTING_BIOMETRIC_SALT, base64.b64encode(biometric_salt).decode('utf-8'))

            logger.info("Stored wrapped key for biometric unlock (key wrapping enabled)")
            return True

        except KeyringError as e:
            logger.error(f"Failed to store biometric secret in keyring: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing biometric data: {e}")
            return False

    async def retrieve_key_with_biometric(
        self,
        user_id: str,
        get_setting: Callable[[str, Any], Awaitable[Any]],
    ) -> Optional[bytes]:
        """Retrieve encryption key from biometric storage using key unwrapping.

        Security: The encryption key is NOT stored directly in the keyring.
        Instead, we:
        1. Retrieve the biometric secret from the OS keyring (after biometric auth)
        2. Retrieve the wrapped key and salt from the database
        3. Unwrap (decrypt) the encryption key using the secret + salt

        Args:
            user_id: Identifier for the key to retrieve
            get_setting: Async function to read settings from database

        Returns:
            The encryption key if biometric auth succeeds and unwrapping works, None otherwise
        """
        if not KEYRING_AVAILABLE:
            logger.warning("Keyring not available")
            return None

        # First, prompt for biometric authentication on supported platforms
        if _is_android and ANDROID_BIOMETRIC_AVAILABLE:
            result = await _prompt_android_biometric("Unlock Trebnic")
            if result != BiometricResult.SUCCESS:
                logger.info(f"Android biometric authentication failed: {result.value}")
                return None

        elif sys.platform == "win32" and WINDOWS_HELLO_AVAILABLE:
            result = await _prompt_windows_hello("Unlock Trebnic")
            if result != BiometricResult.SUCCESS:
                logger.info(f"Windows Hello authentication failed: {result.value}")
                return None

        elif sys.platform == "darwin" and TOUCHID_AVAILABLE:
            result = await _prompt_touchid("Unlock Trebnic")
            if result != BiometricResult.SUCCESS:
                logger.info(f"Touch ID authentication failed: {result.value}")
                return None

        # Linux: no biometric prompt, just retrieve from keyring
        # The keyring itself may prompt for authentication depending on config

        try:
            # Retrieve biometric secret from keyring
            loop = asyncio.get_event_loop()
            secret_b64 = await loop.run_in_executor(
                None,
                lambda: keyring.get_password(KEYRING_SERVICE, user_id)
            )

            if secret_b64 is None:
                logger.warning("No biometric secret found in keyring")
                return None

            biometric_secret = base64.b64decode(secret_b64)

            # Retrieve wrapped key and salt from database
            wrapped_key = await get_setting(SETTING_BIOMETRIC_WRAPPED_KEY, None)
            salt_b64 = await get_setting(SETTING_BIOMETRIC_SALT, None)

            if wrapped_key is None or salt_b64 is None:
                logger.warning("Wrapped key or salt not found in database")
                return None

            biometric_salt = base64.b64decode(salt_b64)

            # Unwrap the encryption key
            key = unwrap_key_from_biometric(wrapped_key, biometric_secret, biometric_salt)
            if key is None:
                logger.warning("Key unwrapping failed")
                return None

            logger.info("Retrieved encryption key via biometric unlock (key unwrapping)")
            return key

        except KeyringError as e:
            logger.error(f"Failed to retrieve biometric secret from keyring: {e}")
            return None
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to decode biometric data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving key: {e}")
            return None

    async def delete_stored_key(self, user_id: str) -> bool:
        """Delete stored encryption key from keychain.

        Args:
            user_id: Identifier for the key to delete

        Returns:
            True if deleted successfully or key didn't exist
        """
        if not KEYRING_AVAILABLE:
            return True  # Nothing to delete

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: keyring.delete_password(KEYRING_SERVICE, user_id)
            )
            logger.info("Deleted stored encryption key")
            return True

        except PasswordDeleteError:
            # Key didn't exist - that's fine
            logger.debug("No stored key to delete")
            return True
        except KeyringError as e:
            logger.error(f"Failed to delete key from keyring: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting key: {e}")
            return False

    async def has_stored_key(self, user_id: str) -> bool:
        """Check if a key is stored for the given user ID.

        Args:
            user_id: Identifier for the key to check

        Returns:
            True if a key exists in the keychain
        """
        if not KEYRING_AVAILABLE:
            return False

        try:
            loop = asyncio.get_event_loop()
            key_b64 = await loop.run_in_executor(
                None,
                lambda: keyring.get_password(KEYRING_SERVICE, user_id)
            )
            return key_b64 is not None

        except Exception:
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
        auth = get_auth_service(get_setting, set_setting)

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
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> "AuthService":
        """Singleton pattern with double-check locking."""
        if cls._instance is None:
            with cls._instance_lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        get_setting: Callable[[str, Any], Awaitable[Any]],
        set_setting: Callable[[str, Any], Awaitable[None]]
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
        """Check if biometric auth is available on this platform.

        Returns True if keyring is installed and either:
        - Windows Hello is available (Windows)
        - Touch ID is available (macOS)
        - Keyring backend is available (Linux)
        """
        return self._passkey.is_available

    @property
    def is_passkey_enabled(self) -> bool:
        """Check if biometric auth is enabled for this user."""
        return self._config.passkey_enabled and self._passkey.is_available

    @property
    def biometric_type(self) -> Optional[str]:
        """Get the name of the available biometric type.

        Returns:
            "Windows Hello", "Touch ID", "Keyring", or None if not available
        """
        return self._passkey.biometric_type

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

        This retrieves and unwraps the encryption key using:
        1. Biometric secret from OS keychain (after biometric verification)
        2. Wrapped key from database
        """
        if not self._passkey.is_available or not self._config.passkey_enabled:
            return False

        # Check if we have a stored biometric secret
        has_key = await self._passkey.has_stored_key(KEYRING_KEY_ID)
        if not has_key:
            logger.warning("No stored biometric secret for unlock")
            return False

        # Retrieve and unwrap key with biometric prompt
        key = await self._passkey.retrieve_key_with_biometric(
            KEYRING_KEY_ID,
            self._get_setting,
        )
        if key is None:
            return False

        # Verify the key is correct by checking against stored verification hash
        if self._config.key_verification_hash is None:
            logger.error("No key verification hash configured")
            return False

        # Set up crypto with the retrieved key
        from services.crypto import verify_key, CRYPTO_AVAILABLE
        if not verify_key(key, self._config.key_verification_hash):
            logger.warning("Retrieved key failed verification")
            return False

        # Key is valid - unlock the app
        crypto._key = key
        if CRYPTO_AVAILABLE:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            crypto._aesgcm = AESGCM(key)

        self._state = AuthState.UNLOCKED
        logger.info("Unlocked via biometric authentication")
        return True

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
            password: Master password (needed to derive and store key)

        Returns:
            True if enabled successfully

        Security: The encryption key is NOT stored directly in the keyring.
        Instead, a wrapped version is stored in the database, and only a
        biometric secret is stored in the keyring. Both are needed to
        recover the key, providing defense in depth.
        """
        if not self._passkey.is_available:
            logger.warning("Passkey not available on this platform")
            return False

        # Verify password and derive key
        if not await self.unlock_with_password(password):
            return False

        # Store wrapped key using key wrapping
        if crypto._key is None:
            logger.error("No encryption key available to store")
            return False

        success = await self._passkey.store_key_for_biometric(
            crypto._key,
            KEYRING_KEY_ID,
            self._set_setting,
        )
        if not success:
            logger.error("Failed to store wrapped key for biometric unlock")
            return False

        await self._set_setting(SETTING_PASSKEY_ENABLED, True)
        self._config.passkey_enabled = True

        logger.info(f"Biometric unlock enabled ({self._passkey.biometric_type})")
        return True

    async def disable_passkey(self) -> bool:
        """Disable biometric/passkey authentication."""
        # Delete stored biometric secret from keychain
        await self._passkey.delete_stored_key(KEYRING_KEY_ID)

        # Clear wrapped key and salt from database
        await self._set_setting(SETTING_BIOMETRIC_WRAPPED_KEY, None)
        await self._set_setting(SETTING_BIOMETRIC_SALT, None)
        await self._set_setting(SETTING_PASSKEY_ENABLED, False)
        self._config.passkey_enabled = False

        logger.info("Passkey disabled")
        return True

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance.

        Note: This method is primarily used for testing to ensure
        a fresh AuthService instance between test cases. Not typically
        called in production code.
        """
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.lock()
                cls._instance._initialized = False
                cls._instance = None


# ============================================================================
# Module-level factory (lazy initialization)
# ============================================================================


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
    return AuthService(get_setting, set_setting)
