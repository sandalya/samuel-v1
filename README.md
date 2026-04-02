# Samuel v1 — Design Assistant

## Що це
Telegram бот-асистент для Ксюші (UI/UX дизайнер).
Живе на Raspberry Pi 5, керується через systemd.

## Швидкий старт після перерви
```bash
sam-status        # перевірити чи живий
sam-logs          # дивитись логи
sam-restart       # перезапустити
sam-git           # коміт і пуш
```

## Структура
```
samuel-v1/
├── core/
│   ├── ai.py           # Claude Sonnet + vision
│   ├── config.py       # .env змінні
│   ├── prompt.py       # системний промпт
│   ├── memory.py       # памʼять між сесіями
│   └── design_search.py # Antigravity Kit пошук
├── bot/
│   ├── client.py       # Telegram handlers
│   └── renderer.py     # SVG → PNG конвертація
├── design-skill/       # Antigravity Kit (ui-ux-pro-max)
├── memory/             # файли памʼяті між сесіями
├── logs/               # bot.log
├── .env                # ключі (не в git)
└── main.py
```

## Стек
- Python 3.11 + python-telegram-bot 21
- Anthropic Claude Sonnet (vision)
- cairosvg для SVG→PNG
- Antigravity Kit для дизайн-референсів

## Що вміє
- Приймає текст, фото, скріни, URL
- Генерує SVG компоненти → PNG превью (5 варіантів за замовчуванням)
- Аналізує макети і дає фідбек
- Памʼятає контекст між сесіями через memory/
- Відповідає мовою запиту (укр/англ)

## Активний проєкт
**poker_ruletka** — ігровий інтерфейс (покер/рулетка)

## Команди бота
- /start — привітання
- /clear — очистити історію сесії
- /save — зберегти памʼять

## Що ще треба зробити
- [ ] Google Stitch MCP підключити
- [ ] Nano Banana 2 MCP підключити  
- [ ] 21st.dev API інтеграція
- [ ] Покращити парсер для стабільного рендеру 5/5 варіантів

## GitHub
https://github.com/sandalya/samuel-v1

## Pi5 розташування
/home/sashok/.openclaw/workspace/samuel-v1/
