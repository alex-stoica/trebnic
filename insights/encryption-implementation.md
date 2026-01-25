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
3. **Configured but locked**: Shows `[Locked]` placeholder instead of encrypted gibberish
4. **Unlocked**: Full encryption/decryption

This is handled by `encrypt_if_unlocked()` and `decrypt_if_encrypted()` helpers.

When the app is locked, `decrypt_if_encrypted()` returns `LOCKED_PLACEHOLDER` ("[Locked]") instead of the raw `ENC:1:...` base64 string. This provides a clean UI experience.

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

### Password Change with Re-encryption ✅ IMPLEMENTED

Re-encryption is now implemented in `AuthService.change_master_password()`:

1. Verify old password and keep reference to old key/AESGCM
2. Create `decrypt_with_old_key` closure that uses the old key
3. Derive new key from new password
4. Create `encrypt_with_new_key` function using new key
5. Call `db.reencrypt_all_data(decrypt_fn, encrypt_fn)` which:
   - Loads all tasks and projects
   - For each encrypted field, decrypts with old key, re-encrypts with new key
   - Updates all rows in a single transaction
6. On failure, rolls back to old key

**Key insight**: The old key must be captured *before* deriving the new key, since `crypto` is a singleton and `derive_key_from_password()` overwrites `crypto._key`.

### SQLCipher Integration

For cloud sync, full-database encryption is recommended:
- Replace `aiosqlite` with `sqlcipher3`
- Handle key management at connection level
- Consider per-device vs shared encryption keys
