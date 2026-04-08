"""Перевірка балансу Google AI."""
import logging
import os

log = logging.getLogger("core.balance_check")
LOW_BALANCE_THRESHOLD = 5.0

async def check_and_warn(context) -> None:
    """JobQueue callback — раз на 3 дні перевіряє витрати."""
    from core.config import OWNER_CHAT_ID
    from core.token_tracker import get_stats

    stats = get_stats(days=3)
    if not stats:
        return

    cost = stats.get("total_cost_usd", 0)
    msg_parts = [f"📊 Витрати за 3 дні: ${cost:.4f}"]

    # Перевіряємо токени Anthropic
    total_input = stats.get("total_input_tokens", 0)
    total_output = stats.get("total_output_tokens", 0)
    msg_parts.append(f"Claude: {stats.get('total_requests', 0)} запитів, {total_input}→{total_output} токенів")
    msg_parts.append(f"Gemini: {stats.get('gemini_calls', 0)} генерацій")

    if cost > 5.0:
        msg_parts.insert(0, "⚠️ Увага! Витрати за 3 дні перевищили $5")

    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text="\n".join(msg_parts)
    )
    log.info(f"Balance check відправлено: ${cost:.4f}")
