"""Обробник повідомлень Семюеля з message grouping."""
import logging
import os
import re
import tempfile
import asyncio
from pathlib import Path
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from core.config import TELEGRAM_TOKEN, ADMIN_IDS, OWNER_CHAT_ID
from core.ai import ask_ai
from bot.renderer import process_ai_response

log = logging.getLogger("bot.client")

conversations: dict[int, list] = {}

# Буфер для групування повідомлень {user_id: {text, images, timer_task}}
buffers: dict[int, dict] = {}
BUFFER_WAIT = 3.5  # секунди очікування


def is_authorized(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == OWNER_CHAT_ID


async def flush_buffer(user_id: int, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обробляє зібраний буфер після паузи."""
    await asyncio.sleep(BUFFER_WAIT)

    buf = buffers.pop(user_id, None)
    if not buf:
        return

    message = buf.get("text", "")
    image_path = buf.get("image_path")
    url_match = re.search(r"https?://\S+", message) if message else None
    url = url_match.group(0) if url_match else None

    await _process_and_reply(update, user_id, message, image_path=image_path, url=url)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Немає доступу.")
        return
    await update.message.reply_text("Семюель готовий.\n\nНадсилай текст, скріни або посилання — зроблю.")


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    conversations.pop(user.id, None)
    buffers.pop(user.id, None)
    await update.message.reply_text("Історію очищено.")


async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    history = conversations.get(user.id, [])
    if not history:
        await update.message.reply_text("Нічого зберігати.")
        return
    from core.memory import save_memory
    summary_lines = ["## Остання сесія"]
    for msg in history[-10:]:
        role = "Ксюша" if msg["role"] == "user" else "Семюель"
        text = str(msg.get("content", ""))[:200]
        summary_lines.append(f"**{role}:** {text}")
    save_memory("\n".join(summary_lines))
    await update.message.reply_text("Памʼять збережено.")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return

    text = update.message.text or ""

    # Скасовуємо попередній таймер якщо є
    if user.id in buffers and buffers[user.id].get("task"):
        buffers[user.id]["task"].cancel()

    # Додаємо текст в буфер
    buf = buffers.setdefault(user.id, {})
    buf["text"] = (buf.get("text", "") + " " + text).strip()
    buf["update"] = update

    # Запускаємо таймер
    task = asyncio.create_task(flush_buffer(user.id, update, ctx))
    buf["task"] = task


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return

    caption = update.message.caption or ""

    # Завантажуємо фото
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_in_{user.id}.jpg")
    await file.download_to_drive(tmp_path)

    # Скасовуємо попередній таймер
    if user.id in buffers and buffers[user.id].get("task"):
        buffers[user.id]["task"].cancel()

    buf = buffers.setdefault(user.id, {})
    buf["image_path"] = tmp_path
    buf["update"] = update
    if caption:
        buf["text"] = (buf.get("text", "") + " " + caption).strip()

    task = asyncio.create_task(flush_buffer(user.id, update, ctx))
    buf["task"] = task


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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

    if user.id in buffers and buffers[user.id].get("task"):
        buffers[user.id]["task"].cancel()

    buf = buffers.setdefault(user.id, {})
    buf["image_path"] = tmp_path
    buf["update"] = update
    if caption:
        buf["text"] = (buf.get("text", "") + " " + caption).strip()

    task = asyncio.create_task(flush_buffer(user.id, update, ctx))
    buf["task"] = task


async def _process_and_reply(update: Update, user_id: int,
                              message: str, image_path: str = None,
                              url: str = None):
    history = conversations.setdefault(user_id, [])

    await update.message.reply_text("Working on it...")

    reply = await ask_ai(
        user_id=user_id,
        message=message,
        history=history,
        image_path=image_path,
        url=url
    )

    history.append({"role": "user", "content": f"{'[image] ' if image_path else ''}{message}"})
    history.append({"role": "assistant", "content": reply})

    result = process_ai_response(reply, base_name=f"samuel_{user_id}")

    if result["has_visual"] and result["png_paths"]:
        try:
            if len(result["png_paths"]) == 1:
                name, path = result["png_paths"][0]
                with open(path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=name)
            else:
                media = []
                for i, (name, path) in enumerate(result["png_paths"]):
                    with open(path, "rb") as f:
                        media.append(InputMediaPhoto(media=f.read(), caption=name if i < 10 else None))
                await update.message.reply_media_group(media=media)
        except Exception as e:
            log.error(f"Помилка відправки PNG: {e}")

    if result["text"] and not result["has_visual"]:
        text = result["text"][:4000]
        await update.message.reply_text(text)


def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    log.info("Handlers налаштовано")
