# Encryption Implementation Learnings

## Architecture Decisions

### Field-Level vs Full-Database Encryption

We chose **field-level encryption** (AES-GCM per field) over SQLCipher because:
- Works with standard `aiosqlite` (no native dependencies)
- Allows selective encryption (only sensitive fields)
- Easier migration path (can encrypt existing data gradually)

Trade-off: Can't do encrypted SQL queries (e.g., `WHERE title LIKE '%meeting%'`).

For full protection, **SQLCipher** is still recommended for future sync features.

### Key Derivation: Argon2id vs PBKDF2

- **Argon2id** (preferred): Memory-hard, resistant to GPU attacks
- **PBKDF2** (fallback): Available everywhere, less secure against modern attacks

We use both with runtime detection via `argon2-cffi` optional dependency.

Parameters chosen per OWASP 2023 recommendations:
```python
# Argon2id
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MB
ARGON2_PARALLELISM = 4

# PBKDF2 fallback
PBKDF2_ITERATIONS = 600_000
```

## Circular Import Solution

### The Problem

```
database.py → services.crypto → services/__init__.py → services.logic → database.py
```

This creates an `ImportError` at startup.

### The Solution: Lazy Import

Despite the "no imports inside functions" rule, this is the accepted exception:

```python
# database.py
_crypto = None

def _get_crypto():
    """Lazy import to avoid circular dependency."""
    global _crypto
    if _crypto is None:
        from services.crypto import crypto
        _crypto = crypto
    return _crypto
```

**Why this is acceptable:**
- Import happens once, cached globally
- Only alternative would require restructuring the entire codebase
- Pattern is well-documented in Python community for this exact case

## Encryption Format

Encrypted fields use a versioned format for future-proofing:

```
ENC:1:<base64(nonce + ciphertext + tag)>
```

- `ENC:1:` prefix identifies encrypted data and version
- Allows checking if field is encrypted without trying to decrypt
- Version number enables future algorithm changes

## Graceful Degradation

The encryption system is designed to work in multiple states:

1. **No cryptography library**: All encryption disabled, plaintext storage
2. **Library installed, not configured**: Plaintext storage
3. **Configured but locked**: Encrypted data unreadable (shows as-is)
4. **Unlocked**: Full encryption/decryption

This is handled by `encrypt_if_unlocked()` and `decrypt_if_encrypted()` helpers.

## Remaining Work

### Passkey/Biometrics (High Priority)

Platform-specific implementation needed:

| Platform | API |
|----------|-----|
| Windows | Windows Hello / Credential Manager |
| macOS | Keychain + Touch ID |
| iOS | LocalAuthentication framework |
| Android | BiometricPrompt API |

The `PasskeyService` class has placeholder methods ready for implementation.

### Password Change with Re-encryption

Current implementation changes the password but doesn't re-encrypt existing data.
Proper implementation requires:
1. Load all encrypted data
2. Decrypt with old key
3. Generate new salt + key
4. Re-encrypt with new key
5. Atomic transaction to update all rows

### SQLCipher Integration

For cloud sync, full-database encryption is recommended:
- Replace `aiosqlite` with `sqlcipher3`
- Handle key management at connection level
- Consider per-device vs shared encryption keys
