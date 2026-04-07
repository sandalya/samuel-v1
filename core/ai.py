"""AI модуль Семюеля — Anthropic з підтримкою vision."""
import logging
import base64
import anthropic
from pathlib import Path
from core.config import ANTHROPIC_KEY
from core.prompt import SAMUEL_SYSTEM_PROMPT
from core.memory import load_memory, load_context
from core.image_gen import generate_image, detect_image_intent

log = logging.getLogger("core.ai")

client = anthropic.Anthropic(
    api_key=ANTHROPIC_KEY,
    max_retries=2,
    timeout=120.0
)

MAX_HISTORY = 8
MAX_MSG_LEN = 4000
MAX_HISTORY_TOKENS = 6000


def optimize_history(history: list) -> list:
    """Обрізає історію по токенах, не по кількості повідомлень."""
    result = []
    total = 0
    for msg in reversed(history):
        content = msg.get("content", "")
        # груба оцінка: 1 токен ≈ 4 символи
        size = len(str(content)) // 4
        if total + size > MAX_HISTORY_TOKENS:
            break
        result.insert(0, msg)
        total += size
    # мінімум 2 повідомлення (1 пара) щоб не втратити контекст
    if not result and history:
        result = history[-2:]
    log.debug(f"History: {len(result)} повідомлень, ~{total} токенів")
    return result


def build_system_blocks() -> list:
    """Повертає список блоків для system= з cache_control на статичних частинах."""
    from pathlib import Path
    blocks = []

    # Блок 1: базовий промпт — завжди статичний, кешуємо
    blocks.append({
        "type": "text",
        "text": SAMUEL_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    })

    # Блок 2: style knowledge — змінюється тільки після /learn, кешуємо
    knowledge_file = Path(__file__).parent.parent / "memory" / "style_knowledge.md"
    if knowledge_file.exists():
        knowledge = knowledge_file.read_text(encoding="utf-8")
        if knowledge.strip():
            blocks.append({
                "type": "text",
                "text": f"## Прийняті роботи — стиль клієнта\n{knowledge[-8000:]}",
                "cache_control": {"type": "ephemeral"}
            })

    # Блок 3: контекст сесії — динамічний, НЕ кешуємо
    context = load_context()
    if context:
        blocks.append({
            "type": "text",
            "text": f"## Контекст роботи з Ксюшею\n{context}"
        })

    return blocks


def encode_image(image_path: str) -> tuple[str, str]:
    import io
    path = Path(image_path)
    try:
        from PIL import Image
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((1568, 1568), Image.LANCZOS)
        buf = io.BytesIO()
        quality = 82
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        while buf.tell() > 1.5 * 1024 * 1024 and quality > 30:
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
            system=build_system_blocks(),
            messages=messages
        )

        reply = response.content[0].text
        u = response.usage
        cache_read = getattr(u, "cache_read_input_tokens", 0)
        cache_created = getattr(u, "cache_creation_input_tokens", 0)
        log.info(f"AI відповів: {reply[:80]}...")
        log.info(f"Токени: in={u.input_tokens} out={u.output_tokens} cache_read={cache_read} cache_created={cache_created}")
        return reply, {
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read": cache_read,
            "cache_created": cache_created,
            "has_image": bool(image_path),
        }

    except anthropic.APIError as e:
        log.error(f"Anthropic API помилка: {e}")
        return "Сервіс тимчасово недоступний. Спробуй за хвилину.", {}
    except anthropic.RateLimitError:
        log.error("Rate limit")
        return "Забагато запитів, спробуй за хвилину.", {}
    except Exception as e:
        log.error(f"AI помилка: {e}")
        return "Технічна помилка. Спробуй ще раз.", {}


async def summarize_session(history: list, current_context: str) -> str:
    """Робить rolling summary сесії і повертає оновлений context."""
    if not history:
        return current_context
    history_text = "\n".join([
        f"{m['role'].upper()}: {m['content'][:200]}"
        for m in history[-20:]
    ])
    prompt = f"""Ти оновлюєш rolling context для дизайн-асистента Семюеля.

Поточний context:
{current_context or "(порожній)"}

Діалог цієї сесії:
{history_text}

Перепиши context.md — максимум 1500 символів. Структура:
## Ксюша
(хто вона, як працює, ключові деталі)

## Активний проєкт
(що зараз робимо, статус, важливі деталі)

## Патерни роботи
(що приймає, що відхиляє, типові запити, стиль спілкування)

## Остання сесія
(коротко що робили, що вийшло)

Зберігай важливе, викидай застаріле. Тільки факти, без води."""

    try:
        from anthropic import AsyncAnthropic
        from core.config import ANTHROPIC_KEY
        client = AsyncAnthropic(api_key=ANTHROPIC_KEY)
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        result = resp.content[0].text.strip()
        log.info("Session summary готовий")
        return result
    except Exception as e:
        log.error(f"summarize_session помилка: {e}")
        return current_context

async def ask_ai_with_image_gen(user_id: int, message: str, history: list,
                                 image_path: str = None, url: str = None):
    from core.token_tracker import track as _track
    reply, usage = await ask_ai(user_id, message, history, image_path, url)

    if '```html' in reply:
        log.info("track: html_render")
        try:
            _track(**usage, result_type="html_render")
        except Exception as e:
            log.error(f"track error: {e}")
        log.info("track: done")
        return reply, None

    # Очищаємо промпт від можливих префіксів які Claude може написати
    log.info(f"DEBUG reply start: {reply[:200]}")
    gen_prompt = reply.strip()
    # Прибираємо markdown якщо Claude раптом загорнув
    if gen_prompt.startswith("```"):
        lines = gen_prompt.split("\n")
        gen_prompt = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    gen_prompt = gen_prompt[:2000]  # збільшено з 800 до 2000
    log.info(f"FULL_PROMPT: {gen_prompt}")
    # Не передаємо референс якщо Claude вже описав стиль в промпті
    # (щоб Gemini не копіював композицію, а створював оригінальну)
    gen_path, err = await generate_image(
        prompt=gen_prompt,
        reference_image_path=None,
        style_hint=None,
    )
    if err:
        _track(**usage, result_type="text_only")
        return reply, None

    _track(**usage, result_type="image_gen",
           gemini_used=True,
           gemini_input=len(gen_prompt) // 4,
           gemini_output=1000)
    return reply, str(gen_path)

