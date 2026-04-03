"""PID lock — запобігає запуску двох інстансів бота."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
PID_FILE = BASE_DIR / "bot.pid"


def _is_bot_process(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().decode(errors="replace")
        return "main.py" in cmdline
    except (FileNotFoundError, ProcessLookupError):
        return False


def acquire_lock():
    current_pid = os.getpid()
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if _is_bot_process(old_pid):
                print(f"❌ Бот вже запущений (PID {old_pid})")
                sys.exit(1)
        except ValueError:
            pass
    PID_FILE.write_text(str(current_pid))


def release_lock():
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass
