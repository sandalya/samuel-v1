"""Управління памʼяттю між сесіями."""
import logging
from datetime import date
from core.config import MEMORY_DIR

log = logging.getLogger("core.memory")

def load_memory() -> str:
    """Завантажує останній memory файл."""
    MEMORY_DIR.mkdir(exist_ok=True)
    files = sorted(MEMORY_DIR.glob("*.md"), reverse=True)
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
    """Зберігає memory файл з датою."""
    MEMORY_DIR.mkdir(exist_ok=True)
    path = MEMORY_DIR / f"{date.today()}.md"
    try:
        path.write_text(content, encoding="utf-8")
        log.info(f"Памʼять збережено: {path.name}")
    except Exception as e:
        log.error(f"Не вдалось зберегти памʼять: {e}")
