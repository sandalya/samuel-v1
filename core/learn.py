"""Режим навчання Семюеля — аналіз прийнятих робіт."""
import logging
import base64
import httpx
import os
from pathlib import Path
from datetime import datetime

log = logging.getLogger("core.learn")

BASE_DIR = Path(__file__).parent.parent
APPROVED_DIR = BASE_DIR / "memory" / "approved"
KNOWLEDGE_FILE = BASE_DIR / "memory" / "style_knowledge.md"
APPROVED_DIR.mkdir(parents=True, exist_ok=True)

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")


async def analyze_and_save(image_path: str) -> str:
    """Аналізує зображення і додає патерни в style_knowledge.md."""
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_KEY)

    # Читаємо зображення
    path = Path(image_path)
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode()
    suffix = path.suffix.lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".png": "image/png", ".webp": "image/webp"}
    media_type = media_types.get(suffix, "image/jpeg")

    # Поточна база знань для контексту
    existing = KNOWLEDGE_FILE.read_text(encoding="utf-8") if KNOWLEDGE_FILE.exists() else ""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64}
                },
                {
                    "type": "text",
                    "text": f"""Проаналізуй цю прийняту дизайн-роботу. Витягни конкретні патерни:
- Кольорова палітра (hex якщо можна визначити)
- Стиль (glassmorphism, flat, neumorphism, 3D тощо)
- Типографіка (bold/light, розміри, шрифти)
- Композиція і layout
- Що характерно для цього дизайну

Поточна база знань:
{existing[:500] if existing else 'порожня'}

Відповідай коротко, по пунктах, українською. Тільки нові спостереження яких ще немає в базі."""
                }
            ]
        }]
    )

    analysis = response.content[0].text

    # Зберігаємо зображення
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path = APPROVED_DIR / f"approved_{timestamp}{path.suffix}"
    import shutil
    shutil.copy2(image_path, saved_path)

    # Додаємо в style_knowledge.md
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n---\n### {timestamp_str}\n{analysis}"

    with open(KNOWLEDGE_FILE, "a", encoding="utf-8") as f:
        if not existing:
            f.write("# Style Knowledge — Прийняті роботи\n")
        f.write(entry)

    log.info(f"Збережено: {saved_path.name}, аналіз додано в style_knowledge.md")
    return analysis
