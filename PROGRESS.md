# Samuel v1 — Progress Log

## Сесія 2026-04-04

### Зроблено

**Пам'ять і контекст**
- Збільшено knowledge[:3000] → knowledge[-8000:] — Сем бачить свіжі аналізи Ксюші
- MAX_HISTORY знижено з 20 до 8 — менше зайвих токенів
- /learn протестовано — працює ✅ Ксюша завантажила ~30 банерів, style_knowledge.md = 63KB
- Rolling context: `memory/context.md` замість session memory — фіксований розмір ~1500 символів
- Auto-summary: якщо history повний (8) + пауза > 1год → Claude робить summary → переписує context.md → скидає history
- `build_system_prompt` тепер читає context.md замість старих dated .md файлів

**Рендер і вивід**
- Всі варіанти в одному HTML блоці — один PNG замість N окремих
- Прибрано caption під PNG
- Прибрано текст відповіді коли є картинки (окрім коротких < 200 символів)
- Fallback regex для незакритих ```html блоків
- max_tokens збільшено з 8000 до 16000
- Заборонено Сему писати аналіз референсу перед кодом

**Image generation (Gemini via OpenRouter)**
- Нова логіка маршрутизації: є ```html → wkhtmltoimage, немає → Gemini
- Claude формує детальний image gen промпт сам
- Grid інструкція: N rows × M columns для варіантів з фазами
- Результат: progress bar 5 варіантів × 3 фази генерується коректно ✅

**Reply на зображення**
- Ксюша робить reply на будь-яке зображення в чаті → Сем підхоплює його як референс
- `_get_reply_image()` в client.py — витягує фото з reply_to_message автоматично

### Наступна сесія

- [ ] Per-project memory (/project poker_ruletka)
- [ ] Підтягнути голос Семюеля — іноді пише зайві вступи
- [ ] /scale команда для якості PNG
- [ ] Auto-switch Haiku/Sonnet
- [ ] Веб-інтерфейс резерв

### Архітектурні рішення

- Gemini для реалістики/3D assets, Claude HTML для UI компонентів
- style_knowledge.md — останні 8000 символів в промпті
- context.md — rolling summary, max 1500 символів, переписується автоматично
- Reply на зображення = найнатуральніший спосіб уточнювати варіанти

---

## Думки для наступних сесій

### Пріоритет 1 — Per-project memory
- `/project poker_ruletka` → Сем завантажує `memory/projects/poker_ruletka.md`
- Там: палітра, стиль, що вже зроблено, що прийнято
- Простіше ніж здається — просто окремий .md на проект

### Пріоритет 2 — Голос Семюеля
- Іноді пише зайві вступи перед промптом для Gemini
- Промпт треба зробити коротшим і жорсткішим

### Технічний борг
- `image_gen.py` має debug логи які варто прибрати
- `.bak` файли в репо — старі треба видалити
- `install_image_gen.sh` і `fix_image_gen.sh` — видалити з репо

---

## Передати Claude на початку наступної сесії

Продовжуємо розробку Samuel v1 — Telegram бот-асистент для UI/UX дизайнера Ксюші.
Працює на Raspberry Pi 5, Python, systemd.
Репо: https://github.com/sandalya/samuel-v1
Прочитай PROGRESS.md для повного контексту.

Стек:
- python-telegram-bot 21
- Anthropic Claude Sonnet (основний AI + vision)
- Gemini Flash через OpenRouter (google/gemini-3.1-flash-image-preview)
- wkhtmltoimage (HTML → PNG рендер)
- Systemd сервіс: samuel-v1.service

Середовище:
- Pi5 path: /home/sashok/.openclaw/workspace/samuel-v1/
- SSH доступ є, команди через SSH — ок

Що працює:
- Telegram bot (polling, buffer 3.5s)
- Claude HTML → PNG через wkhtmltoimage (всі варіанти в одному блоці)
- Gemini image generation через OpenRouter
- /learn режим → memory/style_knowledge.md (63KB, ~30 банерів)
- Rolling context: memory/context.md (auto-summary після 1год паузи + повний history)
- Reply на зображення — Ксюша робить reply → Сем бере як референс
- PID lock (немає 409 конфліктів)
- Маршрутизація: є ```html → wkhtmltoimage, немає → Gemini

Що треба зробити (в порядку пріоритету):
1. Per-project memory (/project poker_ruletka)
2. Підтягнути голос Семюеля в промпті
3. /scale команда для якості PNG
4. Auto-switch Haiku/Sonnet

Ключові файли:
- core/ai.py — Claude клієнт, ask_ai_with_image_gen, summarize_session, MAX_HISTORY=8, max_tokens=16000
- core/image_gen.py — Gemini генерація
- core/learn.py — /learn режим
- core/prompt.py — системний промпт
- core/memory.py — load_context/save_context + legacy load_memory
- bot/client.py — Telegram handlers, _get_reply_image, _maybe_summarize, last_activity
- bot/renderer.py — HTML → PNG, fallback regex
- memory/context.md — rolling context про Ксюшу (auto-updated)
- memory/style_knowledge.md — база прийнятих стилів (останні 8000 символів в промпті)

---

## Сесія 2026-04-07

### Зроблено

**Typing indicator**
- Прибрано "Working on it..." — замінено на Telegram typing action
- `_keep_typing()` loop кожні 4с поки бот думає
- Передано `ctx` в `_process_and_reply`

**Image generation — композиція**
- `gen_prompt` збільшено з 800 до 3500 символів
- Референс більше не передається в Gemini — Claude описує стиль текстом, Gemini створює оригінальну композицію
- Заборона тексту/логотипів в промпті (no text, no signs, no logos)
- Стандартний розмір 1920x1080px якщо не вказано інше
- Промпт записується в /tmp/last_gen_prompt.txt для дебагу
- Системний промпт: дизайнерська воля замість жорстких правил композиції

### Результат
- Композиції стали різноманітнішими і не копіюють референс
- Typing indicator працює
- Текст більше не з'являється в зображеннях
