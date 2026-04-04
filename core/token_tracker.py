"""Трекер токенів і вартості для Samuel v1."""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("core.token_tracker")

LOG_FILE = Path(__file__).parent.parent / "memory" / "token_log.jsonl"

# Ціни в $ за 1 токен (Sonnet 4.5)
PRICES = {
    "input":          3.00 / 1_000_000,
    "output":        15.00 / 1_000_000,
    "cache_read":     0.30 / 1_000_000,
    "cache_creation": 3.75 / 1_000_000,
    # Gemini via OpenRouter
    "gemini_input":   0.0000005,
    "gemini_output":  0.000003,
}

def _write_entry(entry: dict):
    """Синхронний запис — викликати через run_in_executor."""
    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log.error(f"token_tracker write error: {e}")


def track(
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_created: int = 0,
    has_image: bool = False,
    result_type: str = "text_only",
    gemini_used: bool = False,
    gemini_input: int = 0,
    gemini_output: int = 0,
):
    cost_claude = (
        input_tokens * PRICES["input"] +
        output_tokens * PRICES["output"] +
        cache_read * PRICES["cache_read"] +
        cache_created * PRICES["cache_creation"]
    )
    cost_gemini = (
        gemini_input * PRICES["gemini_input"] +
        gemini_output * PRICES["gemini_output"]
    ) if gemini_used else 0.0

    # скільки б коштувало БЕЗ кешу
    cost_without_cache = (
        (input_tokens + cache_read + cache_created) * PRICES["input"] +
        output_tokens * PRICES["output"]
    )
    saved = cost_without_cache - cost_claude

    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "input": input_tokens,
        "output": output_tokens,
        "cache_read": cache_read,
        "cache_created": cache_created,
        "has_image": has_image,
        "result_type": result_type,
        "gemini_used": gemini_used,
        "gemini_input": gemini_input,
        "gemini_output": gemini_output,
        "cost_claude": round(cost_claude, 6),
        "cost_gemini": round(cost_gemini, 6),
        "cost_total": round(cost_claude + cost_gemini, 6),
        "cache_saved": round(saved, 6),
    }

    import threading
    threading.Thread(target=_write_entry, args=(entry,), daemon=True).start()
    return entry


def get_stats(days: int = 7) -> dict:
    if not LOG_FILE.exists():
        return {}

    cutoff = datetime.now() - timedelta(days=days)
    entries = []

    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                if datetime.fromisoformat(e["ts"]) >= cutoff:
                    entries.append(e)
            except Exception:
                continue

    if not entries:
        return {}

    total = len(entries)
    with_image = sum(1 for e in entries if e.get("has_image"))
    gemini_calls = sum(1 for e in entries if e.get("gemini_used"))
    result_types = {}
    for e in entries:
        rt = e.get("result_type", "unknown")
        result_types[rt] = result_types.get(rt, 0) + 1

    total_input = sum(e.get("input", 0) for e in entries)
    total_output = sum(e.get("output", 0) for e in entries)
    total_cache_read = sum(e.get("cache_read", 0) for e in entries)
    total_cost = sum(e.get("cost_total", 0) for e in entries)
    total_saved = sum(e.get("cache_saved", 0) for e in entries)

    useful = result_types.get("html_render", 0) + result_types.get("image_gen", 0)
    cache_hit_rate = (
        total_cache_read / (total_input + total_cache_read) * 100
        if (total_input + total_cache_read) > 0 else 0
    )

    # середня вартість
    avg_cost = total_cost / total if total else 0
    claude_costs = [e.get("cost_claude", 0) for e in entries]
    gemini_costs = [e.get("cost_gemini", 0) for e in entries if e.get("gemini_used")]
    avg_claude = sum(claude_costs) / len(claude_costs) if claude_costs else 0
    avg_gemini = sum(gemini_costs) / len(gemini_costs) if gemini_costs else 0

    return {
        "days": days,
        "total_requests": total,
        "with_image": with_image,
        "gemini_calls": gemini_calls,
        "result_types": result_types,
        "useful_results": useful,
        "efficiency_pct": round(useful / total * 100) if total else 0,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_read": total_cache_read,
        "cache_hit_rate": round(cache_hit_rate, 1),
        "total_cost_usd": round(total_cost, 4),
        "total_saved_usd": round(total_saved, 4),
        "avg_cost_usd": round(avg_cost, 5),
        "avg_claude_cost": round(avg_claude, 5),
        "avg_gemini_cost": round(avg_gemini, 5),
    }


def format_stats(days: int = 7) -> str:
    s = get_stats(days)
    if not s:
        return "📊 Даних поки немає."

    rt = s["result_types"]
    lines = [
        f"📊 Статистика за {days} днів ({s['total_requests']} запитів)",
        "",
        f"⚡ Ефективність: {s['useful_results']}/{s['total_requests']} корисних результатів ({s['efficiency_pct']}%)",
        f"   🖼 html/svg render: {rt.get('html_render', 0)}",
        f"   🎨 image gen: {rt.get('image_gen', 0)}",
        f"   💬 текст: {rt.get('text_only', 0)}",
        "",
        f"🗃 Кеш: {s['cache_hit_rate']}% hit rate",
        f"   Зекономлено: ${s['total_saved_usd']:.4f}",
        "",
        f"💰 Вартість:",
        f"   Всього: ${s['total_cost_usd']:.4f}",
        f"   Середній запит Сема: ${s['avg_claude_cost']:.5f}",
        f"   Середня картинка (Gemini): ${s['avg_gemini_cost']:.5f}",
        f"   ({s['gemini_calls']} генерацій з {s['total_requests']} запитів)",
    ]
    return "\n".join(lines)
