"""Рендеринг SVG в PNG для Telegram."""
import logging
import re
import tempfile
from pathlib import Path

log = logging.getLogger("bot.renderer")


def extract_svg(text: str) -> str | None:
    """Витягує SVG з відповіді Claude."""
    match = re.search(r"(<svg[\s\S]*?</svg>)", text, re.IGNORECASE)
    return match.group(1) if match else None


def svg_to_png(svg_content: str, output_path: str) -> bool:
    """Конвертує SVG в PNG через cairosvg."""
    try:
        import cairosvg
        cairosvg.svg2png(
            bytestring=svg_content.encode("utf-8"),
            write_to=output_path,
            scale=2.0
        )
        log.info(f"PNG збережено: {output_path}")
        return True
    except ImportError:
        log.error("cairosvg не встановлено: pip install cairosvg")
        return False
    except Exception as e:
        log.error(f"Помилка конвертації SVG->PNG: {e}")
        return False


def save_svg(svg_content: str, output_path: str) -> bool:
    """Зберігає SVG файл."""
    try:
        Path(output_path).write_text(svg_content, encoding="utf-8")
        log.info(f"SVG збережено: {output_path}")
        return True
    except Exception as e:
        log.error(f"Помилка збереження SVG: {e}")
        return False


def process_ai_response(text: str, base_name: str = "samuel") -> dict:
    """
    Обробляє відповідь AI:
    - витягує SVG якщо є
    - зберігає SVG файл
    - конвертує в PNG превью
    Повертає dict з шляхами і текстом відповіді.
    """
    result = {
        "text": text,
        "svg_path": None,
        "png_path": None,
        "has_visual": False
    }

    svg = extract_svg(text)
    if not svg:
        return result

    tmp_dir = Path(tempfile.gettempdir()) / "samuel"
    tmp_dir.mkdir(exist_ok=True)

    svg_path = str(tmp_dir / f"{base_name}.svg")
    png_path = str(tmp_dir / f"{base_name}.png")

    if save_svg(svg, svg_path):
        result["svg_path"] = svg_path

    if svg_to_png(svg, png_path):
        result["png_path"] = png_path
        result["has_visual"] = True

    # Прибираємо SVG код з тексту відповіді
    clean_text = re.sub(r"```svg[\s\S]*?```", "", text)
    clean_text = re.sub(r"<svg[\s\S]*?</svg>", "", clean_text)
    clean_text = clean_text.strip()
    result["text"] = clean_text

    return result
