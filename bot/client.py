"""Обробник повідомлень Семюеля."""
import logging
import os
import tempfile
from pathlib import Path
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from core.config import TELEGRAM_TOKEN, ADMIN_IDS, OWNER_CHAT_ID
from core.ai import ask_ai
from bot.renderer import process_ai_response

log = logging.getLogger("bot.client")

# Історія розмов на сесію {user_id: [messages]}
conversations: dict[int, list] = {}


def is_authorized(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == OWNER_CHAT_ID


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Немає доступу.")
        return
    await update.message.reply_text(
        "Семюель готовий.\n\n"
        "Надсилай текст, скріни або посилання — зроблю."
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Очищає історію розмови."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    conversations.pop(user.id, None)
    await update.message.reply_text("Історію очищено.")


async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Зберігає памʼять сесії."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    history = conversations.get(user.id, [])
    if not history:
        await update.message.reply_text("Нічого зберігати.")
        return
    from core.memory import save_memory
    # Формуємо memory з останніх повідомлень
    summary_lines = ["## Остання сесія"]
    for msg in history[-10:]:
        role = "Ксюша" if msg["role"] == "user" else "Семюель"
        text = str(msg.get("content", ""))[:200]
        summary_lines.append(f"**{role}:** {text}")
    save_memory("\n".join(summary_lines))
    await update.message.reply_text("Памʼять збережено.")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обробляє текстові повідомлення."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    message = update.message.text or ""

    # Визначаємо URL якщо є в тексті
    import re
    url_match = re.search(r"https?://\S+", message)
    url = url_match.group(0) if url_match else None

    await _process_and_reply(update, user.id, message, url=url)


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обробляє фото і скріни."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    caption = update.message.caption or ""

    # Завантажуємо фото
    photo = update.message.photo[-1]  # найбільший розмір
    file = await ctx.bot.get_file(photo.file_id)

    tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_in_{user.id}.jpg")
    await file.download_to_drive(tmp_path)

    await _process_and_reply(update, user.id, caption, image_path=tmp_path)


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обробляє документи (PNG/SVG надіслані як файл)."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Надсилай зображення або текст.")
        return

    caption = update.message.caption or ""
    file = await ctx.bot.get_file(doc.file_id)
    suffix = Path(doc.file_name).suffix if doc.file_name else ".png"
    tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_doc_{user.id}{suffix}")
    await file.download_to_drive(tmp_path)

    await _process_and_reply(update, user.id, caption, image_path=tmp_path)


async def _process_and_reply(update: Update, user_id: int,
                              message: str, image_path: str = None,
                              url: str = None):
    """Спільна логіка обробки і відповіді."""
    history = conversations.setdefault(user_id, [])

    # Typing indicator
    await update.message.chat.send_action("typing")

    # AI запит
    reply = await ask_ai(
        user_id=user_id,
        message=message,
        history=history,
        image_path=image_path,
        url=url
    )

    # Оновлюємо історію
    user_content = []
    if image_path:
        user_content.append({"type": "text", "text": f"[image] {message}"})
    else:
        user_content.append({"type": "text", "text": message})

    history.append({"role": "user", "content": user_content[0]["text"]})
    history.append({"role": "assistant", "content": reply})

    # Обробляємо відповідь — шукаємо SVG
    result = process_ai_response(reply, base_name=f"samuel_{user_id}")

    # Відправляємо PNG як media group якщо є кілька
    if result["has_visual"] and result["png_paths"]:
        from telegram import InputMediaPhoto
        try:
            if len(result["png_paths"]) == 1:
                name, path = result["png_paths"][0]
                with open(path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=name)
            else:
                media = []
                for i, (name, path) in enumerate(result["png_paths"]):
                    with open(path, "rb") as f:
                        media.append(InputMediaPhoto(
                            media=f.read(),
                            caption=name if i < 10 else None
                        ))
                await update.message.reply_media_group(media=media)
        except Exception as e:
            log.error(f"Помилка відправки PNG: {e}")

    # SVG відправка вимкнена — Ксюша працює з PNG

    # Відправляємо текст
    if result["text"]:
        # Telegram має ліміт 4096 символів
        text = result["text"]
        if len(text) > 4000:
            text = text[:4000] + "..."
        await update.message.reply_text(text)


def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    log.info("Handlers налаштовано")
