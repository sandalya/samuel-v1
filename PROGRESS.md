# Samuel v1 — Progress Log

## Сесія 2026-04-04

### Зроблено

**Пам'ять і контекст**
- Збільшено knowledge[:3000] → knowledge[-12000:] — Сем бачить всі свіжі аналізи Ксюші
- MAX_HISTORY знижено з 20 до 8 — менше зайвих токенів
- /learn протестовано — працює ✅ Ксюша завантажила ~30 банерів, style_knowledge.md = 63KB

**Рендер і вивід**
- Всі варіанти тепер в одному HTML блоці — один PNG замість N окремих
- Прибрано caption під PNG
- Прибрано текст відповіді коли є картинки (окрім коротких < 200 символів)
- Fallback regex для незакритих ```html блоків (\Z як альтернатива закриваючому ```)
- max_tokens збільшено з 8000 до 16000
- Заборонено Сему писати аналіз референсу перед кодом

**Image generation (Gemini via OpenRouter)**
- Прибрано has_reference з тригерів — OpenRouter не запускається на кожне фото
- Нова логіка маршрутизації: є ```html → wkhtmltoimage, немає → Gemini
- Claude формує детальний image gen промпт сам (не сирий message користувача)
- Промпт для Gemini не відображається в чаті
- Grid інструкція в промпті: N rows × M columns для варіантів з фазами
- Результат: progress bar 5 варіантів × 3 фази генерується коректно ✅

### Наступна сесія

- [ ] Per-project memory (/project poker_ruletka)
- [ ] Підтягнути голос Семюеля в промпті — іноді пише зайве
- [ ] /scale команда для якості PNG
- [ ] Auto-switch Haiku/Sonnet
- [ ] Веб-інтерфейс резерв (якщо TG відпаде)

### Архітектурні рішення

- Gemini для реалістики/3D assets, Claude HTML/SVG для UI компонентів
- style_knowledge.md — останні 12000 символів в промпті (найсвіжіші аналізи)
- Project Memory = база прийнятих робіт, не параметри проекту

---

## Думки для наступних сесій

### Пріоритет 1 — Per-project memory
- `/project poker_ruletka` → Сем завантажує `memory/projects/poker_ruletka.md`
- Там: палітра, стиль, що вже зроблено, що прийнято
- Простіше ніж здається — просто окремий .md на проект

### Пріоритет 2 — Голос Семюеля
Системний промпт треба підтягнути. Семюель все ще іноді:
- Пише зайві вступи перед промптом для Gemini
- Дає забагато тексту там де треба просто результат
Рішення: зробити промпт коротшим і жорсткішим.

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
- Gemini 3.1 Flash Image через OpenRouter (google/gemini-3.1-flash-image-preview)
- wkhtmltoimage (HTML → PNG рендер)
- Systemd сервіс: samuel-v1.service

Середовище:
- Pi5 path: /home/sashok/.openclaw/workspace/samuel-v1/
- SSH доступ є, команди через SSH — ок

Що працює:
- Telegram bot (polling, buffer 3.5s для групування повідомлень)
- Claude HTML/SVG → PNG через wkhtmltoimage (всі варіанти в одному блоці)
- Gemini image generation через OpenRouter
- /learn режим — аналіз прийнятих робіт → memory/style_knowledge.md (63KB, ~30 банерів)
- PID lock (немає 409 конфліктів)
- Маршрутизація: є ```html в відповіді → wkhtmltoimage, немає → Gemini

Що треба зробити (в порядку пріоритету):
1. Per-project memory (/project poker_ruletka)
2. Підтягнути голос Семюеля в промпті
3. /scale команда для якості PNG
4. Auto-switch Haiku/Sonnet

Ключові файли:
- core/ai.py — Claude клієнт, ask_ai_with_image_gen, MAX_HISTORY=8, max_tokens=16000
- core/image_gen.py — Gemini генерація
- core/learn.py — /learn режим
- core/prompt.py — системний промпт
- bot/client.py — Telegram handlers
- bot/renderer.py — HTML → PNG, fallback regex для незакритих блоків
- memory/style_knowledge.md — база прийнятих стилів (останні 12000 символів в промпті)
