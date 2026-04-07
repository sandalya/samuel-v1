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
from core.ai import ask_ai_with_image_gen, summarize_session
import time
from core.learn import analyze_and_save
from bot.renderer import process_ai_response

log = logging.getLogger("bot.client")

conversations: dict[int, list] = {}
last_activity: dict[int, float] = {}
learn_mode: set[int] = set()


ALPHA_DIRECT_TRIGGERS = [
    "вирізати фон", "видалити фон", "без фону", "прозор",
    "remove background", "remove bg", "transparent background",
    "png with alpha", "png без фону",
]

def _is_alpha_request(text: str) -> bool:
    t = text.lower()
    return any(tr in t for tr in ALPHA_DIRECT_TRIGGERS)

async def _handle_direct_rembg(update, image_path: str):
    """Пряме видалення фону з готового зображення через rembg."""
    from core.image_gen import _remove_background
    from pathlib import Path
    await update.message.reply_text("⏳ Видаляю фон...")
    try:
        result = _remove_background(Path(image_path))
        with open(result, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="no_bg.png",
                caption="PNG з прозорим фоном"
            )
    except Exception as e:
        log.error(f"direct rembg error: {e}")
        await update.message.reply_text("Помилка видалення фону.")

buffers: dict[int, dict] = {}
BUFFER_WAIT = 3.5


def is_authorized(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == OWNER_CHAT_ID


async def flush_buffer(user_id: int, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(BUFFER_WAIT)
    buf = buffers.pop(user_id, None)
    if not buf:
        return
    message = buf.get("text", "")
    image_path = buf.get("image_path")
    url_match = re.search(r"https?://\S+", message) if message else None
    url = url_match.group(0) if url_match else None
    # Пряме видалення фону якщо є зображення + alpha trigger
    if image_path and _is_alpha_request(message or ""):
        await _handle_direct_rembg(update, image_path)
        return
    await _process_and_reply(update, ctx, user_id, message, image_path=image_path, url=url)


def _cancel_buffer(user_id: int):
    if user_id in buffers and buffers[user_id].get("task"):
        buffers[user_id]["task"].cancel()


async def _add_to_buffer_and_schedule(user_id: int, update: Update,
                                       ctx: ContextTypes.DEFAULT_TYPE,
                                       text: str = "", image_path: str = None):
    _cancel_buffer(user_id)
    buf = buffers.setdefault(user_id, {})
    if text:
        buf["text"] = (buf.get("text", "") + " " + text).strip()
    if image_path:
        buf["image_path"] = image_path
    buf["update"] = update
    task = asyncio.create_task(flush_buffer(user_id, update, ctx))
    buf["task"] = task


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("Немає доступу.")
        return
    await update.message.reply_text("Еббі готова.\n\nНадсилай текст, скріни або посилання — зроблю.")


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


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    from core.token_tracker import format_stats
    text = format_stats(days=7)
    await update.message.reply_text(text)


async def cmd_learn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    if user.id in learn_mode:
        learn_mode.discard(user.id)
        await update.message.reply_text("🔴 Режим навчання вимкнено.")
    else:
        learn_mode.add(user.id)
        await update.message.reply_text("🟢 Режим навчання увімкнено. Скидай прийняті роботи — аналізую і запамʼятовую стиль.")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    text = update.message.text or update.message.caption or ""
    # Якщо форвард — додаємо контекст звідки
    forward_info = _get_forward_context(update)
    if forward_info:
        text = f"{forward_info}\n{text}".strip()
    reply_image = await _get_reply_image(update, ctx, user.id)
    await _add_to_buffer_and_schedule(user.id, update, ctx, text=text, image_path=reply_image)


async def _get_reply_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> str | None:
    """Витягує зображення з reply_to_message якщо є."""
    reply = update.message.reply_to_message
    if not reply:
        return None
    # reply на фото
    if reply.photo:
        photo = reply.photo[-1]
        file = await ctx.bot.get_file(photo.file_id)
        tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_reply_{user_id}.jpg")
        await file.download_to_drive(tmp_path)
        log.info(f"Reply image завантажено: {tmp_path}")
        return tmp_path
    # reply на документ-зображення
    if reply.document and reply.document.mime_type and reply.document.mime_type.startswith("image/"):
        file = await ctx.bot.get_file(reply.document.file_id)
        suffix = Path(reply.document.file_name).suffix if reply.document.file_name else ".png"
        tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_reply_{user_id}{suffix}")
        await file.download_to_drive(tmp_path)
        log.info(f"Reply document image завантажено: {tmp_path}")
        return tmp_path
    return None

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return

    caption = update.message.caption or ""
    forward_info = _get_forward_context(update)
    if forward_info:
        caption = f"{forward_info}\n{caption}".strip()

    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_in_{user.id}.jpg")
    await file.download_to_drive(tmp_path)

    if user.id in learn_mode:
        _cancel_buffer(user.id)
        buffers.pop(user.id, None)
        await update.message.reply_text("⏳ Аналізую...")
        try:
            analysis = await analyze_and_save(tmp_path)
            await update.message.reply_text(f"✅ Збережено.\n\n{analysis[:1000]}")
        except Exception as e:
            log.error(f"learn помилка: {e}")
            await update.message.reply_text("❌ Помилка аналізу.")
        return

    reply_image = await _get_reply_image(update, ctx, user.id)
    final_image = reply_image or tmp_path
    await _add_to_buffer_and_schedule(user.id, update, ctx, text=caption, image_path=final_image)


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return

    doc = update.message.document
    caption = update.message.caption or ""
    forward_info = _get_forward_context(update)
    if forward_info:
        caption = f"{forward_info}\n{caption}".strip()

    # Приймаємо зображення і PDF
    if doc.mime_type and doc.mime_type.startswith("image/"):
        file = await ctx.bot.get_file(doc.file_id)
        suffix = Path(doc.file_name).suffix if doc.file_name else ".png"
        tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_doc_{user.id}{suffix}")
        await file.download_to_drive(tmp_path)
        reply_image = await _get_reply_image(update, ctx, user.id)
        final_image = reply_image or tmp_path
        await _add_to_buffer_and_schedule(user.id, update, ctx, text=caption, image_path=final_image)
    else:
        # Не-зображення — передаємо як текст з описом
        file_desc = f"[Файл: {doc.file_name or 'без назви'}, тип: {doc.mime_type or 'невідомий'}]"
        text = f"{file_desc}\n{caption}".strip()
        await _add_to_buffer_and_schedule(user.id, update, ctx, text=text)


async def handle_sticker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Стікери — конвертуємо в зображення."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    sticker = update.message.sticker
    file = await ctx.bot.get_file(sticker.file_id)
    suffix = ".webp"
    tmp_path = os.path.join(tempfile.gettempdir(), f"samuel_sticker_{user.id}{suffix}")
    await file.download_to_drive(tmp_path)
    # Конвертуємо webp → jpg для Claude
    try:
        from PIL import Image
        img = Image.open(tmp_path).convert("RGB")
        jpg_path = tmp_path.replace(".webp", ".jpg")
        img.save(jpg_path, "JPEG", quality=90)
        tmp_path = jpg_path
    except Exception:
        pass
    await _add_to_buffer_and_schedule(user.id, update, ctx,
                                       text="[Стікер]", image_path=tmp_path)


async def handle_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Відео — поки тільки повідомляємо."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    caption = update.message.caption or ""
    text = f"[Відео]{(' — ' + caption) if caption else ''}"
    await _add_to_buffer_and_schedule(user.id, update, ctx, text=text)


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Голосові — поки не підтримуємо."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    await update.message.reply_text("Голосові поки не підтримуються.")


def _get_forward_context(update: Update) -> str:
    """Витягує контекст форварду якщо є."""
    msg = update.message
    if not msg:
        return ""
    origin = getattr(msg, "forward_origin", None)
    if not origin:
        return ""
    origin_type = getattr(origin, "type", "")
    if origin_type == "channel":
        chat = getattr(origin, "chat", None)
        title = getattr(chat, "title", "") if chat else ""
        return f"[Форвард з каналу: {title}]" if title else "[Форвард з каналу]"
    elif origin_type == "user":
        fwd_user = getattr(origin, "sender_user", None)
        name = getattr(fwd_user, "full_name", "") if fwd_user else ""
        return f"[Форвард від: {name}]" if name else "[Форвард]"
    elif origin_type == "hidden_user":
        name = getattr(origin, "sender_user_name", "")
        return f"[Форвард від: {name}]" if name else "[Форвард]"
    return "[Форвард]"


async def _maybe_summarize(user_id: int):
    """Якщо сесія завершена (history повний + пауза > 1год) — робимо summary і clear."""
    history = conversations.get(user_id, [])
    last = last_activity.get(user_id, 0)
    if len(history) >= 8 and (time.time() - last) > 3600:
        from core.memory import load_context, save_context
        log.info(f"Auto-summary для {user_id}")
        current = load_context()
        new_context = await summarize_session(history, current)
        save_context(new_context)
        conversations.pop(user_id, None)
        log.info(f"History скинуто після summary")

async def _process_and_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user_id: int,
                              message: str, image_path: str = None,
                              url: str = None):
    await _maybe_summarize(user_id)
    last_activity[user_id] = time.time()
    history = conversations.setdefault(user_id, [])
    stop_typing = [False]
    async def _keep_typing():
        while not stop_typing[0]:
            try:
                await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
                log.info("typing sent")
            except Exception as e:
                log.error(f"typing error: {e}")
            await asyncio.sleep(4)
    typing_task = asyncio.create_task(_keep_typing())
    try:
        reply, gen_image_path = await ask_ai_with_image_gen(
            user_id=user_id,
            message=message,
            history=history,
            image_path=image_path,
            url=url
        )
    finally:
        stop_typing[0] = True
        typing_task.cancel()

    history.append({"role": "user", "content": f"{'[image] ' if image_path else ''}{message}"})
    history.append({"role": "assistant", "content": reply})

    result = process_ai_response(reply, base_name=f"samuel_{user_id}")

    if result["has_visual"] and result["png_paths"] and not gen_image_path:
        try:
            if len(result["png_paths"]) == 1:
                name, path = result["png_paths"][0]
                with open(path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=None)
            else:
                media = []
                for i, (name, path) in enumerate(result["png_paths"]):
                    with open(path, "rb") as f:
                        media.append(InputMediaPhoto(media=f.read(), caption=None))
                await update.message.reply_media_group(media=media)
        except Exception as e:
            log.error(f"Помилка відправки PNG: {e}")

    if gen_image_path:
        try:
            import re as _re
            clean = _re.sub(r'!\[.*?\]\(.*?\)', '', result["text"]).strip()
            if clean and not result["png_paths"] and len(clean) < 200:
                await update.message.reply_text(clean[:4000])
            with open(gen_image_path, "rb") as f:
                await update.message.reply_photo(photo=f, caption="🎨 Згенероване зображення")
        except Exception as e:
            log.error(f"Помилка відправки gen зображення: {e}")
    elif result["text"] and not result["has_visual"]:
        await update.message.reply_text(result["text"][:4000])


def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(CommandHandler("learn", cmd_learn))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    log.info("Handlers налаштовано")
