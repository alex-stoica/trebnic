import os
from pathlib import Path
import shutil
import subprocess
import sys


def _settings_process(cwd, storage, action):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "trebnic")
    env["FLET_APP_STORAGE_DATA"] = str(storage) if storage else ""
    script = """
import asyncio
from database import db
async def main():
    await db.init_db()
    try:
        ACTION
    finally:
        await db.close()
asyncio.run(main())
""".replace("ACTION", action)
    return subprocess.run(
        [sys.executable, "-c", script], cwd=cwd, env=env,
        check=True, capture_output=True, text=True, timeout=20,
    ).stdout.strip()


def test_settings_survive_replacing_extracted_app(tmp_path):
    storage = tmp_path / "documents"
    storage.mkdir()
    extracted = tmp_path / "app"
    extracted.mkdir()
    _settings_process(extracted, storage, 'await db.set_setting("notifications_enabled", "true")')
    shutil.rmtree(extracted)
    extracted.mkdir()
    assert _settings_process(extracted, storage, 'print(await db.get_setting("notifications_enabled"))') == "true"
    assert not (extracted / "trebnic.db").exists()


def test_desktop_keeps_local_database(tmp_path):
    _settings_process(tmp_path, None, 'await db.set_setting("theme", "dark")')
    assert (tmp_path / "trebnic.db").is_file()
    assert _settings_process(tmp_path, None, 'print(await db.get_setting("theme"))') == "dark"
