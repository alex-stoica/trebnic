# Biometric Authentication Implementation

> **Status**: Crypto primitives exist in `services/crypto.py` (`wrap_key_for_biometric`) and i18n keys
> are defined, but the UI integration is **not wired up**. This doc describes the intended architecture.

## Overview

Implemented biometric authentication in `services/auth.py` using:
- **keyring** library for cross-platform secure credential storage
- **Platform-specific biometric prompts** before key retrieval

## Architecture

### Security Flow

1. User sets up master password (derives encryption key)
2. User enables biometric unlock
3. Encryption key is stored in OS keychain (via keyring)
4. On next launch:
   - System prompts for biometric verification (Windows Hello / Touch ID)
   - Only after successful verification, key is retrieved from keychain
   - Key is verified against stored hash before use

### Platform Support

| Platform | Biometric | Keychain | Notes |
|----------|-----------|----------|-------|
| Windows | Windows Hello | Credential Manager | Requires `winrt` package for biometric prompt |
| macOS | Touch ID | Keychain | Requires `pyobjc-framework-LocalAuthentication` |
| Android | Fingerprint/Face | Android Keystore | Requires `pyjnius` + androidx.biometric |
| Linux | None | libsecret/KWallet | Keyring-only mode (no biometric prompt) |

## Key Implementation Details

### Lazy Availability Detection

```python
@property
def is_available(self) -> bool:
    if self._available is None:
        self._available, self._biometric_type = self._detect_availability()
    return self._available
```

Availability is cached on first check to avoid repeated platform API calls.

### Async Key Retrieval

All keyring operations run in thread pool executors to avoid blocking the event loop:

```python
loop = asyncio.get_event_loop()
key_b64 = await loop.run_in_executor(
    None,
    lambda: keyring.get_password(KEYRING_SERVICE, user_id)
)
```

### Windows Hello Integration

Uses `winrt` package (WinRT Python projection) to call Windows Hello APIs:

```python
import winrt.windows.security.credentials.ui as wincred_ui
result = await UserConsentVerifier.request_verification_async(reason)
```

**Note**: `winrt` must be installed separately: `pip install winrt`

### Touch ID Integration

Uses `pyobjc` with LocalAuthentication framework:

```python
from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthenticationWithBiometrics

context = LAContext.alloc().init()
context.evaluatePolicy_localizedReason_reply_(policy, reason, callback)
```

The callback-based API requires threading to bridge with asyncio properly.

### Android Biometric Integration

Uses `pyjnius` to access Android's BiometricPrompt API:

```python
from jnius import autoclass, PythonJavaClass, java_method

BiometricPrompt = autoclass("androidx.biometric.BiometricPrompt")
# ... create callback, build prompt info, authenticate
```

Android detection checks for `/system/build.prop` or `ANDROID_ROOT` env variable.

## Dependencies

Required for encryption:
```
cryptography>=41.0.0     # AES-256-GCM encryption
```

Optional dependencies for full biometric support:

```
keyring>=23.0.0          # Required for any biometric support
argon2-cffi>=23.0.0      # Better key derivation (falls back to PBKDF2)
winrt>=1.0.0             # Windows Hello (Windows only)
pyobjc-framework-LocalAuthentication>=8.0  # Touch ID (macOS only)
pyjnius                  # Android biometric (Android only, bundled with Flet)
```

## Security Considerations

1. **Key never leaves secure storage unverified**: Biometric check happens before keyring retrieval
2. **Key verification**: Retrieved key is verified against stored hash before use
3. **Graceful degradation**: Falls back to password if biometrics fail
4. **Linux limitations**: No biometric prompt on Linux - keyring access control depends on desktop environment

## Testing Notes

- Windows Hello requires actual biometric hardware or PIN configured
- Touch ID requires Mac with Touch ID sensor or Apple Silicon
- For testing without hardware, mock the `PasskeyService` class

## Future Improvements

1. **iOS support**: Would need Flet native plugin or Swift bridge
2. **Web support**: WebAuthn API for browser-based passkeys
3. **Key rotation**: When master password changes, also update stored key
