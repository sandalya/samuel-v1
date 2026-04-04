"""AI модуль Семюеля — Anthropic з підтримкою vision."""
import logging
import base64
import anthropic
from pathlib import Path
from core.config import ANTHROPIC_KEY
from core.prompt import SAMUEL_SYSTEM_PROMPT
from core.memory import load_memory
from core.image_gen import generate_image, detect_image_intent

log = logging.getLogger("core.ai")

client = anthropic.Anthropic(
    api_key=ANTHROPIC_KEY,
    max_retries=2,
    timeout=120.0
)

MAX_HISTORY = 8
MAX_MSG_LEN = 4000


def optimize_history(history: list) -> list:
    return history[-MAX_HISTORY:]


def build_system_prompt() -> str:
    from pathlib import Path
    memory = load_memory()
    base = SAMUEL_SYSTEM_PROMPT

    # Додаємо style knowledge якщо є
    knowledge_file = Path(__file__).parent.parent / "memory" / "style_knowledge.md"
    if knowledge_file.exists():
        knowledge = knowledge_file.read_text(encoding="utf-8")
        if knowledge.strip():
            base += f"\n\n## Прийняті роботи — стиль клієнта\n{knowledge[-12000:]}"

    if memory:
        base += f"\n\n## Память з попередніх сесій\n{memory}"
    return base


def encode_image(image_path: str) -> tuple[str, str]:
    import io
    path = Path(image_path)
    try:
        from PIL import Image
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((1920, 1920), Image.LANCZOS)
        buf = io.BytesIO()
        quality = 85
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        while buf.tell() > 4 * 1024 * 1024 and quality > 30:
            quality -= 15
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        log.info(f"Зображення: {buf.tell()/1024:.0f}KB, якість {quality}")
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"
    except ImportError:
        raw = path.read_bytes()
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("PIL не встановлено і файл завеликий")
        suffix = path.suffix.lower()
        media_types = {".jpg":"image/jpeg",".jpeg":"image/jpeg",
                       ".png":"image/png",".webp":"image/webp"}
        return base64.standard_b64encode(raw).decode("utf-8"), media_types.get(suffix,"image/jpeg")


async def ask_ai(user_id: int, message: str, history: list,
                 image_path: str = None, url: str = None) -> str:
    try:
        optimized = optimize_history(history)
        content = []

        if image_path:
            try:
                data, media_type = encode_image(image_path)
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data
                    }
                })
                log.info(f"Зображення додано: {image_path}")
            except Exception as e:
                log.error(f"Помилка кодування зображення: {e}")

        from core.design_search import enrich_prompt
        design_context = enrich_prompt(message or "")

        if url:
            message = f"{message}\n\nРеференс: {url}" if message else f"Референс: {url}" 

        if message:
            if len(message) > MAX_MSG_LEN:
                message = message[:MAX_MSG_LEN] + "..."
            full_text = message + design_context
            content.append({"type": "text", "text": full_text})

        if not content:
            content.append({"type": "text", "text": "?"})

        messages = optimized + [{"role": "user", "content": content}]

        log.info(f"AI запит від {user_id}: {len(messages)} повідомлень, image={'так' if image_path else 'ні'}")

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=[
                {
                    "type": "text",
                    "text": build_system_prompt(),
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=messages
        )

        reply = response.content[0].text
        log.info(f"AI відповів: {reply[:80]}...")
        return reply

    except anthropic.APIError as e:
        log.error(f"Anthropic API помилка: {e}")
        return "Сервіс тимчасово недоступний. Спробуй за хвилину."
    except anthropic.RateLimitError:
        log.error("Rate limit")
        return "Забагато запитів, спробуй за хвилину."
    except Exception as e:
        log.error(f"AI помилка: {e}")
        return "Технічна помилка. Спробуй ще раз."


async def ask_ai_with_image_gen(user_id: int, message: str, history: list,
                                 image_path: str = None, url: str = None):
    reply = await ask_ai(user_id, message, history, image_path, url)
    if '```html' in reply:
        return reply, None
    # Claude сформував відповідь — беремо її як промпт для Gemini
    gen_prompt = reply.strip()[:800]
    gen_path, err = await generate_image(
        prompt=gen_prompt,
        reference_image_path=image_path,
        style_hint=None,
    )
    if err:
        return reply, None
    return reply, str(gen_path)

