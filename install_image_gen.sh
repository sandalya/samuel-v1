#!/bin/bash
# Встановлює генерацію зображень в Семюеля
# Запуск: bash install_image_gen.sh

set -e
SAMUEL="/home/sashok/.openclaw/workspace/samuel-v1"
CORE="$SAMUEL/core"

echo "=== Семюель: встановлення image_gen ==="

# ── 1. Створюємо core/image_gen.py ────────────────────────────────────
echo "→ Створюю core/image_gen.py..."
cat > "$CORE/image_gen.py" << 'PYEOF'
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
IMAGE_MODEL = "google/gemini-2.5-flash-preview:thinking"

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
        "modalities": ["image", "text"],
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

        response_content = choices[0].get("message", {}).get("content", [])
        if isinstance(response_content, str):
            return None, f"Модель повернула текст: {response_content[:200]}"

        for block in response_content:
            if block.get("type") == "image_url":
                url = block["image_url"]["url"]
                if url.startswith("data:image"):
                    b64_data = url.split(",", 1)[1]
                    return _save_image(b64_data), ""
                else:
                    async with httpx.AsyncClient(timeout=30.0) as http:
                        img_resp = await http.get(url)
                        img_resp.raise_for_status()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    out_path = IMAGES_DIR / f"gen_{timestamp}.png"
                    out_path.write_bytes(img_resp.content)
                    return out_path, ""

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


def detect_image_intent(message: str) -> tuple:
    msg = message.lower()
    triggers = [
        "намалюй", "згенеруй зображення", "створи зображення", "зроби картинку",
        "generate image", "draw me", "зроби фото", "мудборд", "moodboard",
        "візуалізуй", "покажи як виглядає",
    ]
    is_image = any(t in msg for t in triggers)
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
PYEOF
echo "   ✓ core/image_gen.py створено"

# ── 2. Патч core/ai.py — додаємо імпорт і нову функцію ───────────────
echo "→ Патчу core/ai.py..."

# Бекап
cp "$CORE/ai.py" "$CORE/ai.py.bak"

# Додаємо імпорт після рядка з load_memory
python3 - << 'EOF'
import re

path = "/home/sashok/.openclaw/workspace/samuel-v1/core/ai.py"
with open(path) as f:
    src = f.read()

# Імпорт — додаємо після load_memory якщо ще немає
if "from core.image_gen import" not in src:
    src = src.replace(
        "from core.memory import load_memory",
        "from core.memory import load_memory\nfrom core.image_gen import generate_image, detect_image_intent"
    )

# Нова функція — додаємо в кінець якщо ще немає
new_func = '''

async def ask_ai_with_image_gen(user_id: int, message: str, history: list,
                                 image_path: str = None, url: str = None):
    is_image_req, style_hint = detect_image_intent(message or "")

    if is_image_req:
        text_reply = await ask_ai(user_id, message, history, image_path, url)
        gen_prompt = text_reply.split("\\n")[0][:300]
        gen_path, err = await generate_image(
            prompt=gen_prompt,
            reference_image_path=image_path,
            style_hint=style_hint,
        )
        if err:
            return text_reply + f"\\n\\n⚠️ Генерація не вдалась: {err}", None
        return text_reply, str(gen_path)

    reply = await ask_ai(user_id, message, history, image_path, url)
    return reply, None
'''

if "ask_ai_with_image_gen" not in src:
    src = src + new_func

with open(path, "w") as f:
    f.write(src)

print("   ✓ core/ai.py патч OK")
EOF

# ── 3. Патч bot/client.py — замінюємо ask_ai на ask_ai_with_image_gen ─
echo "→ Патчу bot/client.py..."

cp "$SAMUEL/bot/client.py" "$SAMUEL/bot/client.py.bak"

python3 - << 'EOF'
path = "/home/sashok/.openclaw/workspace/samuel-v1/bot/client.py"
with open(path) as f:
    src = f.read()

# Замінюємо імпорт
src = src.replace(
    "from core.ai import ask_ai",
    "from core.ai import ask_ai, ask_ai_with_image_gen"
)

# Замінюємо виклик в _process_and_reply
old_call = '''    reply = await ask_ai(
        user_id=user_id,
        message=message,
        history=history,
        image_path=image_path,
        url=url
    )'''

new_call = '''    reply, gen_image_path = await ask_ai_with_image_gen(
        user_id=user_id,
        message=message,
        history=history,
        image_path=image_path,
        url=url
    )'''

src = src.replace(old_call, new_call)

# Додаємо відправку згенерованого зображення після відправки PNG від SVG
old_send = '''    if result["text"] and not result["has_visual"]:
        text = result["text"][:4000]
        await update.message.reply_text(text)'''

new_send = '''    if gen_image_path:
        try:
            with open(gen_image_path, "rb") as f:
                await update.message.reply_photo(photo=f, caption="🎨 Згенероване зображення")
        except Exception as e:
            log.error(f"Помилка відправки gen зображення: {e}")

    if result["text"] and not result["has_visual"]:
        text = result["text"][:4000]
        await update.message.reply_text(text)'''

src = src.replace(old_send, new_send)

with open(path, "w") as f:
    f.write(src)

print("   ✓ bot/client.py патч OK")
EOF

# ── 4. Встановлюємо httpx якщо нема ───────────────────────────────────
echo "→ Перевіряю httpx..."
cd "$SAMUEL"
source venv/bin/activate
pip install httpx --quiet && echo "   ✓ httpx OK"

# ── 5. Перезапускаємо Семюеля ─────────────────────────────────────────
echo "→ Перезапускаю samuel..."
systemctl --user restart samuel 2>/dev/null || sudo systemctl restart samuel 2>/dev/null || echo "   ⚠️  Перезапусти вручну: sam-restart"

echo ""
echo "=== Готово! ==="
echo ""
echo "Тест: напиши Семюелю 'намалюй мудборд в стилі glassmorphism'"
echo "Логи: sam-logs"
echo ""
echo "Бекапи збережено:"
echo "  $CORE/ai.py.bak"
echo "  $SAMUEL/bot/client.py.bak"
