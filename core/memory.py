"""Управління памʼяттю між сесіями."""
import logging
from datetime import date
from core.config import MEMORY_DIR

log = logging.getLogger("core.memory")

CONTEXT_FILE = MEMORY_DIR / "context.md"

def load_memory() -> str:
    """Завантажує останній memory файл (legacy)."""
    MEMORY_DIR.mkdir(exist_ok=True)
    files = sorted([f for f in MEMORY_DIR.glob("*.md") if f.name != "context.md" and f.name != "style_knowledge.md"], reverse=True)
    if not files:
        return ""
    try:
        content = files[0].read_text(encoding="utf-8")
        log.info(f"Памʼять завантажено: {files[0].name}")
        return content
    except Exception as e:
        log.warning(f"Не вдалось прочитати памʼять: {e}")
        return ""

def save_memory(content: str):
    """Зберігає memory файл з датою (legacy)."""
    MEMORY_DIR.mkdir(exist_ok=True)
    path = MEMORY_DIR / f"{date.today()}.md"
    try:
        path.write_text(content, encoding="utf-8")
        log.info(f"Памʼять збережено: {path.name}")
    except Exception as e:
        log.error(f"Не вдалось зберегти памʼять: {e}")

def load_context() -> str:
    """Завантажує rolling context."""
    MEMORY_DIR.mkdir(exist_ok=True)
    if not CONTEXT_FILE.exists():
        return ""
    try:
        content = CONTEXT_FILE.read_text(encoding="utf-8")
        log.info("Context завантажено")
        return content
    except Exception as e:
        log.warning(f"Не вдалось прочитати context: {e}")
        return ""

def save_context(content: str):
    """Зберігає rolling context (перезаписує)."""
    MEMORY_DIR.mkdir(exist_ok=True)
    try:
        CONTEXT_FILE.write_text(content[:2000], encoding="utf-8")
        log.info("Context збережено")
    except Exception as e:
        log.error(f"Не вдалось зберегти context: {e}")
