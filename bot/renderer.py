"""Рендеринг HTML в PNG для Telegram через wkhtmltoimage."""
import logging
import re
import tempfile
import subprocess
from pathlib import Path

log = logging.getLogger("bot.renderer")


def extract_all_html(text):
    """Витягує всі HTML блоки з відповіді."""
    results = []
    pattern = re.compile(r"(?:Variant|variant|\u0412\u0430\u0440\u0456\u0430\u043d\u0442)\s*(\d+)\s*[\u2014\-]?\s*([^\n]*)\n.*?```html\s*([\s\S]*?)```", re.IGNORECASE)
    for match in pattern.finditer(text):
        num = match.group(1)
        name = match.group(2).strip() or f"variant_{num}"
        html = match.group(3).strip()
        results.append((name, html))

    if not results:
        for i, match in enumerate(re.finditer(r"```html\s*([\s\S]*?)```", text)):
            results.append((f"variant_{i+1}", match.group(1).strip()))

    return results


def html_to_png(html_content: str, output_path: str, width: int = 600) -> bool:
    """Конвертує HTML в PNG через wkhtmltoimage."""
    tmp_html = output_path.replace(".png", ".html")
    try:
        Path(tmp_html).write_text(html_content, encoding="utf-8")
        result = subprocess.run([
            "wkhtmltoimage",
            "--width", str(width),
            "--quality", "95",
            "--enable-local-file-access",
            "--crop-h", "200",
            "--quiet",
            tmp_html,
            output_path
        ], capture_output=True, timeout=30)
        if result.returncode == 0 and Path(output_path).exists():
            log.info(f"PNG збережено: {output_path}")
            return True
        log.error(f"wkhtmltoimage помилка: {result.stderr.decode()}")
        return False
    except subprocess.TimeoutExpired:
        log.error("wkhtmltoimage timeout")
        return False
    except Exception as e:
        log.error(f"HTML->PNG помилка: {e}")
        return False
    finally:
        try:
            Path(tmp_html).unlink()
        except Exception:
            pass


def clean_text(text):
    import re as _re
    text = _re.sub("```html[\\s\\S]*?```", "", text)
    text = _re.sub("\\*\\*([^*]+)\\*\\*", "\\1", text)
    text = _re.sub("\\n{3,}", "\\n\\n", text)
    return text.strip()


def process_ai_response(text: str, base_name: str = "samuel") -> dict:
    """Обробляє відповідь AI — витягує HTML блоки і конвертує в PNG."""
    result = {
        "text": clean_text(text),
        "svg_paths": [],
        "png_paths": [],
        "has_visual": False
    }

    tmp_dir = Path(tempfile.gettempdir()) / "samuel"
    tmp_dir.mkdir(exist_ok=True)

    blocks = extract_all_html(text)

    if not blocks:
        return result

    for i, (name, html) in enumerate(blocks):
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", name)[:30]
        png_path = str(tmp_dir / f"{base_name}_{i+1}_{safe}.png")

        if html_to_png(html, png_path):
            result["png_paths"].append((name, png_path))
            result["has_visual"] = True

    log.info(f"Оброблено {len(blocks)} HTML блоків, {len(result['png_paths'])} PNG")
    return result
