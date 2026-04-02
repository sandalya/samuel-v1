"""AI модуль Семюеля — Anthropic з підтримкою vision."""
import logging
import base64
import anthropic
from pathlib import Path
from core.config import ANTHROPIC_KEY
from core.prompt import SAMUEL_SYSTEM_PROMPT
from core.memory import load_memory

log = logging.getLogger("core.ai")

client = anthropic.Anthropic(
    api_key=ANTHROPIC_KEY,
    max_retries=2,
    timeout=60.0
)

MAX_HISTORY = 20
MAX_MSG_LEN = 4000


def optimize_history(history: list) -> list:
    return history[-MAX_HISTORY:]


def build_system_prompt() -> str:
    memory = load_memory()
    if memory:
        return SAMUEL_SYSTEM_PROMPT + f"\n\n## Память з попередніх сесій\n{memory}"
    return SAMUEL_SYSTEM_PROMPT


def encode_image(image_path: str) -> tuple[str, str]:
    path = Path(image_path)
    suffix = path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(suffix, "image/jpeg")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return data, media_type


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
            max_tokens=4000,
            system=build_system_prompt(),
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
