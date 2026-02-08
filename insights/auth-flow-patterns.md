# Authentication Flow Patterns

## State Machine

The auth system uses a simple three-state machine:

```
NOT_CONFIGURED ──[setup password]──► LOCKED ◄──[lock]─┐
                                       │               │
                                       └──[unlock]──► UNLOCKED
```

### State Transitions

| From | To | Trigger |
|------|-----|---------|
| NOT_CONFIGURED | UNLOCKED | `setup_master_password()` |
| LOCKED | UNLOCKED | `unlock_with_password()` or `unlock_with_passkey()` |
| UNLOCKED | LOCKED | `lock()` or app goes to background |
| Any | NOT_CONFIGURED | `disable_encryption()` |

## Async Initialization Pattern

Auth initialization is async but Flet's `TrebnicApp.__init__` is sync. Solution:

```python
def __init__(self, page: ft.Page):
    # ... sync initialization ...

    # Schedule async auth init after UI is built
    self.page.run_task(self._init_auth)

async def _init_auth(self):
    await self.auth_ctrl.initialize()
    if self.auth_ctrl.needs_unlock:
        self.auth_ctrl.show_unlock_dialog()
```

This ensures:
1. UI is fully built before auth dialog appears
2. Auth state is loaded from database
3. Unlock callback can trigger data reload

## Dialog Callback Patterns

### Async callbacks in dialogs

Flet dialogs need to handle async operations (like password verification):

```python
async def handle_unlock(password: str) -> bool:
    success = await auth.unlock_with_password(password)
    return success

# In dialog, wrap with page.run_task:
on_click=lambda e: page.run_task(handle_unlock)
```

### Chained dialogs

For flows like "Settings → Change Password":
```python
def show_encryption_settings(self):
    open_encryption_settings_dialog(
        # Pass callables that close current dialog and open next
        on_change_password=lambda: self.show_change_password_dialog(),
    )
```

The settings dialog calls `page.pop_dialog()` before invoking the callback.

## Key Never Stored

Critical security principle: the encryption key exists **only in memory**.

Stored in database:
- `encryption_salt` (random bytes, base64)
- `encryption_key_hash` (verification hash, not the key)
- `encryption_enabled` (boolean)

On unlock:
1. User enters password
2. Derive key: `key = argon2(password, salt)`
3. Verify: `hmac(key, "context") == stored_hash`
4. If valid, keep `key` in `CryptoService._key`

On lock:
1. Clear `CryptoService._key = None`
2. Encrypted data becomes unreadable until next unlock

## Reload Pattern After Unlock

When app unlocks, encrypted data in memory is still in encrypted form.
The `reload_state()` method re-fetches everything from database:

```python
async def on_unlocked():
    self.service.reload_state()  # Decrypts via database helpers
    self.tasks_view.refresh()
    self.page.update()
```

This updates the in-memory state object while preserving references.

## Settings Storage

Auth settings use the existing `settings` table with JSON values:

| Key | Value |
|-----|-------|
| `encryption_enabled` | `true` |
| `encryption_salt` | `"base64..."` |
| `encryption_key_hash` | `"base64..."` |
| `passkey_enabled` | `false` |
| `encryption_kdf_method` | `"argon2"` |

This avoids schema changes and leverages existing `db.get_setting()`/`db.set_setting()`.
