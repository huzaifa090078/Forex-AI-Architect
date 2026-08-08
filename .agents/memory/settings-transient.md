---
name: Settings service transient object
description: Why _FakeSettings is used instead of BotSettings.__new__ when no bot user exists.
---

`settings_service.py` needs to return default settings when the bot user (`bot@nexus-ai.internal`) doesn't exist in the DB yet (e.g., first run, test env).

**Problem:** `BotSettings.__new__(BotSettings)` creates an object without SQLAlchemy's `_sa_instance_state`, so calling `db.refresh(s)` on it raises `AttributeError: 'BotSettings' object has no attribute '_sa_instance_state'`.

**Fix:** Use a plain Python class `_FakeSettings` with identical attributes. The `_to_out()` function signature uses `s` (untyped) so it works with both `BotSettings` and `_FakeSettings`.

**Why:** SQLAlchemy ORM instances must be created via the proper ORM pathway (constructor or session.get) to have `_sa_instance_state`. Direct `__new__` bypasses this.
