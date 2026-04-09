"""Abby — дизайн-асистент Ксюші."""
import logging
from core.lock import acquire_lock, release_lock
import sys
import asyncio
from pathlib import Path
from telegram.ext import Application
from core.config import TELEGRAM_TOKEN, LOGS_DIR

LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("main")


async def error_handler(update: object, context):
    log.error(f"Помилка: {context.error}")


def main():
    acquire_lock()
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_TOKEN не встановлено")
        sys.exit(1)

    from bot.client import setup_handlers

    log.info("Abby стартує...")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    setup_handlers(app)
    app.add_error_handler(error_handler)

    # Перевірка витрат раз на 3 дні


    log.info("Polling запущено")
    app.run_polling(
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=20
    )


    release_lock()

if __name__ == "__main__":
    main()
