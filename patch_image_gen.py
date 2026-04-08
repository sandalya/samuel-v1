"""
Патч для core/image_gen.py і core/ai.py
"""
from pathlib import Path

BASE = Path("/home/sashok/.openclaw/workspace/samuel-v1")

# ── Патч 1: image_gen.py ──────────────────────────────────────────────────
img_path = BASE / "core/image_gen.py"
img_text = img_path.read_text()

old_choices = '''        choices = data.get("choices", [])
        if not choices:
            return None, "OpenRouter повернув порожню відповідь"'''

new_choices = '''        choices = data.get("choices", [])
        if not choices:
            return None, "OpenRouter повернув порожню відповідь", 0, 0

        usage_data = data.get("usage", {})
        real_input = usage_data.get("prompt_tokens", 0)
        real_output = usage_data.get("completion_tokens", 0)
        import logging; logging.getLogger("core.image_gen").info(f"OpenRouter usage: input={real_input} output={real_output}")'''

if old_choices in img_text:
    img_text = img_text.replace(old_choices, new_choices)
    print("✅ image_gen.py: usage парсинг додано")
else:
    print("⚠️  image_gen.py: вже оновлено або текст змінився")

old_return_alpha = '''        if wants_alpha:
            result_path = _remove_background(result_path)

        return result_path, ""'''
new_return_alpha = '''        if wants_alpha:
            result_path = _remove_background(result_path)

        return result_path, "", real_input, real_output'''

if old_return_alpha in img_text:
    img_text = img_text.replace(old_return_alpha, new_return_alpha)
    print("✅ image_gen.py: return з usage оновлено")
else:
    print("⚠️  image_gen.py: return вже оновлено")

error_returns = [
    ('return None, "OPENROUTER_API_KEY не знайдено в .env"', 'return None, "OPENROUTER_API_KEY не знайдено в .env", 0, 0'),
    ('return None, "Невірний OPENROUTER_API_KEY"', 'return None, "Невірний OPENROUTER_API_KEY", 0, 0'),
    ('return None, "Недостатньо кредитів на OpenRouter"', 'return None, "Недостатньо кредитів на OpenRouter", 0, 0'),
    ('return None, "Rate limit, спробуй за хвилину"', 'return None, "Rate limit, спробуй за хвилину", 0, 0'),
    ('return None, f"Помилка сервісу ({e.response.status_code})"', 'return None, f"Помилка сервісу ({e.response.status_code})", 0, 0'),
    ('return None, "Таймаут генерації"', 'return None, "Таймаут генерації", 0, 0'),
    ('return None, "Технічна помилка генерації"', 'return None, "Технічна помилка генерації", 0, 0'),
    ('return None, f"Модель повернула текст: {response_content[:200]}"', 'return None, f"Модель повернула текст: {response_content[:200]}", 0, 0'),
    ('return None, "Зображення не знайдено у відповіді моделі"', 'return None, "Зображення не знайдено у відповіді моделі", 0, 0'),
]
for old, new in error_returns:
    if old in img_text and new not in img_text:
        img_text = img_text.replace(old, new)

img_path.write_text(img_text)
print("✅ image_gen.py збережено")

# ── Патч 2: ai.py ─────────────────────────────────────────────────────────
ai_path = BASE / "core/ai.py"
ai_text = ai_path.read_text()

old_gen_call = '''    gen_path, err = await generate_image(
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
    return reply, str(gen_path)'''

new_gen_call = '''    gen_path, err, g_input, g_output = await generate_image(
        prompt=gen_prompt,
        reference_image_path=None,
        style_hint=None,
    )
    if err:
        _track(**usage, result_type="text_only")
        return reply, None

    _track(**usage, result_type="image_gen",
           gemini_used=True,
           gemini_input=g_input,
           gemini_output=g_output)
    return reply, str(gen_path)'''

if old_gen_call in ai_text:
    ai_text = ai_text.replace(old_gen_call, new_gen_call)
    print("✅ ai.py: реальний Gemini usage підключено")
else:
    print("⚠️  ai.py: вже оновлено або текст змінився")

old_summarize = '''        result = resp.content[0].text.strip()
        log.info("Session summary готовий")
        return result'''

new_summarize = '''        result = resp.content[0].text.strip()
        log.info("Session summary готовий")
        try:
            from core.token_tracker import track as _track_sum
            su = resp.usage
            _track_sum(
                input_tokens=su.input_tokens,
                output_tokens=su.output_tokens,
                cache_read=getattr(su, "cache_read_input_tokens", 0),
                cache_created=getattr(su, "cache_creation_input_tokens", 0),
                result_type="summary",
            )
        except Exception as te:
            log.warning(f"summarize track error: {te}")
        return result'''

if old_summarize in ai_text:
    ai_text = ai_text.replace(old_summarize, new_summarize)
    print("✅ ai.py: summarize_session трекінг додано")
else:
    print("⚠️  ai.py: summarize трекінг вже є")

ai_path.write_text(ai_text)
print("✅ ai.py збережено")
print("\n🎉 Готово!")
