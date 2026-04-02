"""Інтеграція з Antigravity design-skill пошуком."""
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("core.design_search")

SKILL_DIR = Path(__file__).parent.parent / "design-skill"
SEARCH_SCRIPT = SKILL_DIR / "src/ui-ux-pro-max/scripts/search.py"


def search_design(query: str, domain: str = None) -> str:
    """Шукає дизайн-патерни по запиту."""
    if not SEARCH_SCRIPT.exists():
        log.warning("design-skill не знайдено")
        return ""

    cmd = ["python3", str(SEARCH_SCRIPT), query]
    if domain:
        cmd += ["--domain", domain]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout:
            # Беремо тільки перший результат щоб не роздувати контекст
            output = result.stdout.strip()
            lines = output.split("\n")
            # Обрізаємо до 40 рядків
            trimmed = "\n".join(lines[:40])
            log.info(f"design_search({query!r}): {len(trimmed)} chars")
            return trimmed
        return ""
    except subprocess.TimeoutExpired:
        log.warning(f"design_search timeout для: {query}")
        return ""
    except Exception as e:
        log.error(f"design_search помилка: {e}")
        return ""


def detect_domain(message: str) -> str | None:
    """Визначає домен пошуку по тексту запиту."""
    msg = message.lower()
    if any(w in msg for w in ["color", "колір", "palette", "палітра"]):
        return "color"
    if any(w in msg for w in ["font", "шрифт", "typography", "типографік"]):
        return "typography"
    if any(w in msg for w in ["chart", "графік", "graph", "діаграм"]):
        return "chart"
    if any(w in msg for w in ["ux", "flow", "onboarding", "user"]):
        return "ux"
    if any(w in msg for w in ["landing", "hero", "cta", "секція"]):
        return "landing"
    if any(w in msg for w in ["style", "стиль", "glassmorphism", "brutalism", "minimal"]):
        return "style"
    return "style"  # default


def enrich_prompt(message: str) -> str:
    """Додає дизайн-контекст до запиту якщо релевантно."""
    # Не шукаємо для коротких або нетехнічних повідомлень
    if len(message) < 10:
        return ""
    skip_words = ["привіт", "дякую", "ok", "добре", "чкп", "гіт"]
    if any(w in message.lower() for w in skip_words):
        return ""

    domain = detect_domain(message)
    results = search_design(message, domain)
    if not results:
        return ""

    return f"\n\n---\nДизайн-референси (Antigravity Kit):\n{results}\n---"
