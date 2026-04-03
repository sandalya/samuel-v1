"""Генерація зображень для Семюеля — OpenRouter → Gemini Flash 2.5."""
import logging
import base64
import httpx
import os
from pathlib import Path
from datetime import datetime

log = logging.getLogger("core.image_gen")

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_MODEL = "google/gemini-3.1-flash-image-preview"

BASE_DIR = Path(__file__).parent.parent
IMAGES_DIR = BASE_DIR / "memory" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def _save_image(b64_data: str, prefix: str = "gen") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = IMAGES_DIR / f"{prefix}_{timestamp}.png"
    out_path.write_bytes(base64.b64decode(b64_data))
    log.info(f"Зображення збережено: {out_path} ({out_path.stat().st_size // 1024}KB)")
    return out_path


async def generate_image(
    prompt: str,
    reference_image_path: str = None,
    style_hint: str = None,
) -> tuple:
    if not OPENROUTER_KEY:
        return None, "OPENROUTER_API_KEY не знайдено в .env"

    style_prefixes = {
        "ui": "Clean UI design, flat design, high contrast, professional interface: ",
        "realistic": "Photorealistic, high detail, professional photography: ",
        "moodboard": "Design moodboard, aesthetic collage, color palette inspiration: ",
    }
    full_prompt = style_prefixes.get(style_hint, "") + prompt

    content = []
    if reference_image_path:
        ref_path = Path(reference_image_path)
        if ref_path.exists():
            try:
                raw = ref_path.read_bytes()
                b64 = base64.b64encode(raw).decode()
                suffix = ref_path.suffix.lower()
                media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                               ".png": "image/png", ".webp": "image/webp"}
                media_type = media_types.get(suffix, "image/png")
                content.append({"type": "image_url",
                                 "image_url": {"url": f"data:{media_type};base64,{b64}"}})
            except Exception as e:
                log.warning(f"Не вдалось додати референс: {e}")

    content.append({"type": "text", "text": full_prompt})

    payload = {
        "model": IMAGE_MODEL,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["text", "image"],
        "image_generation_config": {
            "quality": "standard",
        },
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/sandalya/samuel-v1",
        "X-Title": "Samuel Design Assistant",
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as http:
            log.info(f"Запит генерації: '{full_prompt[:60]}...'")
            resp = await http.post(OPENROUTER_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            return None, "OpenRouter повернув порожню відповідь"

        raw_message = choices[0].get("message", {})
        # Gemini через OpenRouter повертає зображення в message['images']
        images = raw_message.get("images") or []
        if images:
            for img in images:
                # формат: {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,...'}}
                if img.get("type") == "image_url":
                    url = img.get("image_url", {}).get("url", "")
                    if url.startswith("data:image"):
                        b64_data = url.split(",", 1)[1]
                        return _save_image(b64_data), ""
                    elif url:
                        async with httpx.AsyncClient(timeout=30.0) as http:
                            img_resp = await http.get(url)
                            img_resp.raise_for_status()
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        out_path = IMAGES_DIR / f"gen_{timestamp}.png"
                        out_path.write_bytes(img_resp.content)
                        return out_path, ""
        response_content = raw_message.get("content") or []
        if isinstance(response_content, str):
            return None, f"Модель повернула текст: {response_content[:200]}"
        for block in response_content:
            if block.get("type") == "image_url":
                url = block["image_url"]["url"]
                if url.startswith("data:image"):
                    return _save_image(url.split(",", 1)[1]), ""
                else:
                    async with httpx.AsyncClient(timeout=30.0) as http:
                        img_resp = await http.get(url)
                        img_resp.raise_for_status()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    out_path = IMAGES_DIR / f"gen_{timestamp}.png"
                    out_path.write_bytes(img_resp.content)
                    return out_path, ""
            if block.get("type") == "image":
                b64_data = block.get("data") or block.get("source", {}).get("data", "")
                if b64_data:
                    return _save_image(b64_data), ""
        log.warning(f"Невідомий формат: keys={list(raw_message.keys())}, images={images}")
        return None, "Зображення не знайдено у відповіді моделі"

    except httpx.HTTPStatusError as e:
        log.error(f"HTTP помилка: {e.response.status_code}")
        if e.response.status_code == 401:
            return None, "Невірний OPENROUTER_API_KEY"
        if e.response.status_code == 402:
            return None, "Недостатньо кредитів на OpenRouter"
        if e.response.status_code == 429:
            return None, "Rate limit, спробуй за хвилину"
        return None, f"Помилка сервісу ({e.response.status_code})"
    except httpx.TimeoutException:
        return None, "Таймаут генерації, спробуй простіший промпт"
    except Exception as e:
        log.error(f"image_gen помилка: {e}")
        return None, "Технічна помилка генерації"


def detect_image_intent(message: str, reference_image_path: str = None) -> tuple:
    msg = message.lower()
    triggers = [
        "намалюй", "згенеруй", "створи зображення", "зроби картинку",
        "generate image", "draw me", "зроби фото", "реалістичне фото", "реалістичн",
        "мудборд", "moodboard", "ілюстрація", "render", "візуалізуй",
        "покажи як виглядає", "color variation", "colour variation", "варіац",
        "в іншому кольорі", "recolor", "remake", "зроби схожий", "same style",
    ]
    has_reference = reference_image_path is not None
    is_image = any(t in msg for t in triggers) or has_reference
    if not is_image:
        return False, None

    if any(w in msg for w in ["ui", "інтерфейс", "кнопка", "компонент", "екран", "форма"]):
        style = "ui"
    elif any(w in msg for w in ["реалістич", "фото", "realistic", "photo"]):
        style = "realistic"
    elif any(w in msg for w in ["мудборд", "moodboard", "настрій", "палітра"]):
        style = "moodboard"
    else:
        style = None

    return True, style
