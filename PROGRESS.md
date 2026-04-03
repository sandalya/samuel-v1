# Samuel v1 — Progress Log

## Сесія 2026-04-03

### Зроблено

**Gemini image generation**
- `core/image_gen.py` — генерація через OpenRouter → `google/gemini-3.1-flash-image-preview`
- Зображення зберігаються в `memory/images/`
- `detect_image_intent()` — якщо є фото-референс, завжди іде в Gemini
- Відповідь приходить в `message['images'][0]['image_url']['url']` (base64)
- Claude формулює промпт → Gemini генерує → фото в Telegram

**Project Memory (/learn)**
- `core/learn.py` — аналіз прийнятих робіт через Claude vision
- `/learn` — toggle команда (🟢/🔴)
- Фото в learn-режимі → аналіз → `memory/style_knowledge.md`
- `style_knowledge.md` автоматично додається в системний промпт

**PID Lock**
- `core/lock.py` — запобігає 409 Conflict (два інстанси)
- `bot.pid` в .gitignore

**bot/client.py**
- `ask_ai_with_image_gen` — розумна маршрутизація SVG vs Gemini
- SVG не відправляється якщо є Gemini результат
- HTML/markdown очищається з тексту перед відправкою

### Наступна сесія

- [ ] B: SVG стабілізація — рендер 5/5 варіантів стабільно
- [ ] Протестувати /learn з реальними роботами Ксюші
- [ ] Перевірити що style_knowledge впливає на якість генерації
- [ ] Розглянути memory для активного проекту (poker_ruletka)

### Архітектурні рішення

- Stitch і 21st.dev — пропустили, не дають прямої користі в Telegram флоу
- Gemini для реалістики/3D, Claude SVG для UI компонентів
- Project Memory = база прийнятих робіт, не параметри проекту

---

## Думки для наступних сесій

### Пріоритет 1 — SVG стабілізація
wkhtmltoimage нестабільний на складному HTML. Варіанти:
- Спростити HTML який генерує Claude (менше CSS tricks)
- Або перейти на `playwright` — стабільніший рендер

### Пріоритет 2 — Перевірити /learn реально працює
Після того як Ксюша завантажить роботи — перевірити що `style_knowledge.md`
реально змінює генерацію, а не просто додається в промпт і тоне в контексті.
Можливо треба обмежити розмір або зробити summary замість сирого тексту.

### Пріоритет 3 — Per-project memory
Не глобальна пам'ять, а per-project:
- `/project poker_ruletka` → Семюель завантажує `memory/projects/poker_ruletka.md`
- Там: палітра, стиль, що вже зроблено, що прийнято
- Простіше ніж здається — просто окремий .md на проект

### Пріоритет 4 — Голос Семюеля
Системний промпт треба підтягнути. Семюель все ще іноді:
- Пише "чудово!", "з радістю"
- Дає забагато тексту там де треба просто результат
- Пропонує Midjourney/Pollinations замість генерувати сам
Рішення: зробити промпт коротшим і жорсткішим. Менше слів — більше діла.

### Технічний борг
- `image_gen.py` має debug логи які варто прибрати (RAW MESSAGE тощо)
- `.bak` файли в репо — вже в gitignore але старі треба видалити
- `install_image_gen.sh` і `fix_image_gen.sh` — видалити з репо
