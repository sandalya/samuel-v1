"""Рендеринг HTML в PNG для Telegram через wkhtmltoimage."""
import logging
import re
import tempfile
import subprocess
from pathlib import Path

log = logging.getLogger("bot.renderer")


def extract_all_html(text: str) -> list[tuple[str, str]]:
    results = []

    block_pattern = re.compile(r"```html\s*([\s\S]*?)(?:```|\Z)", re.IGNORECASE)

    title_pattern = re.compile(
        r"(?:"
        r"(?:#{1,4}\s*)?(?:Variant|Варіант|Option|Варіація|Вариант)\s*(\d+)"
        r"|(?:#{1,4}\s*)(\d+)[.)]\s"
        r"|\*{1,2}(?:Variant|Варіант|Option)\s*(\d+)\*{1,2}"
        r")",
        re.IGNORECASE
    )

    for i, block_match in enumerate(block_pattern.finditer(text)):
        html = block_match.group(1).strip()
        if not html:
            continue

        search_start = max(0, block_match.start() - 400)
        before_block = text[search_start:block_match.start()]

        name = f"Варіант {i + 1}"

        title_matches = list(title_pattern.finditer(before_block))
        if title_matches:
            tm = title_matches[-1]
            num = tm.group(1) or tm.group(2) or tm.group(3)
            rest = before_block[tm.end():].strip().split("\n")[0].strip()
            rest = re.sub(r"^[—\-:]\s*", "", rest)
            if rest and len(rest) < 60:
                name = f"Варіант {num} — {rest}"
            else:
                name = f"Варіант {num}"

        results.append((name, html))
        log.info(f"Знайдено блок {i+1}: '{name}' ({len(html)} символів)")

    if not results:
        log.warning("extract_all_html: жодного блоку не знайдено")

    return results


def html_to_png(html_content: str, output_path: str, width: int = 800) -> bool:
    tmp_html = output_path.replace(".png", ".html")
    try:
        if "<!DOCTYPE" not in html_content and "<html" not in html_content:
            html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ margin: 0; padding: 16px; background: #fff; font-family: sans-serif; }}
</style>
</head>
<body>{html_content}</body>
</html>"""

        Path(tmp_html).write_text(html_content, encoding="utf-8")

        result = subprocess.run([
            "wkhtmltoimage",
            "--width", str(width),
            "--quality", "95",
            "--enable-local-file-access",
            "--disable-smart-width",
            "--quiet",
            tmp_html,
            output_path
        ], capture_output=True, timeout=30)

        if result.returncode == 0 and Path(output_path).exists():
            size = Path(output_path).stat().st_size
            if size < 500:
                log.warning(f"PNG підозріло малий ({size} байт): {output_path}")
                return False
            log.info(f"PNG збережено: {output_path} ({size//1024}KB)")
            return True

        log.error(f"wkhtmltoimage помилка (код {result.returncode}): {result.stderr.decode()[:300]}")
        return False

    except subprocess.TimeoutExpired:
        log.error("wkhtmltoimage timeout (30s)")
        return False
    except Exception as e:
        log.error(f"HTML->PNG помилка: {e}")
        return False
    finally:
        try:
            Path(tmp_html).unlink(missing_ok=True)
        except Exception:
            pass


def clean_text(text: str) -> str:
    text = re.sub(r"```[\w]*[\s\S]*?```", "", text)
    text = re.sub(r"<svg[\s\S]*?</svg>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<!DOCTYPE[\s\S]*?</html>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def inject_images_base64(html: str, image_paths: list) -> str:
    """Замінює photo1.jpg, photo2.jpg тощо на реальний base64."""
    import base64
    for i, img_path in enumerate(image_paths, 1):
        try:
            path = Path(img_path)
            raw = path.read_bytes()
            suffix = path.suffix.lower()
            mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")
            b64 = base64.standard_b64encode(raw).decode()
            data_url = f"data:{mime};base64,{b64}"
            for placeholder in [f"photo{i}.jpg", f"photo{i}.png",
                                  f"image{i}.jpg", f"image{i}.png",
                                  f"img{i}.jpg", f"img{i}.png"]:
                html = html.replace(f'src="{placeholder}"', f'src="{data_url}"')
                html = html.replace(f"src='{placeholder}'", f"src='{data_url}'")
        except Exception as e:
            log.warning(f"inject_images_base64 {i}: {e}")
    return html

def process_ai_response(text: str, base_name: str = "samuel", image_paths: list = None) -> dict:
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
        log.info("Візуальних блоків не знайдено")
        return result

    log.info(f"Знайдено {len(blocks)} блоків, починаємо рендер...")

    for i, (name, html) in enumerate(blocks):
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", name)[:30]
        png_path = str(tmp_dir / f"{base_name}_{i+1}_{safe}.png")

        if image_paths:
            html = inject_images_base64(html, image_paths)

        log.info(f"HTML перед рендером (перші 300): {html[:300]}")
        if html_to_png(html, png_path):
            result["png_paths"].append((name, png_path))
            result["has_visual"] = True
        else:
            log.warning(f"Блок {i+1} '{name}' — рендер не вдався")

    log.info(f"Результат: {len(result['png_paths'])}/{len(blocks)} PNG успішно")
    return result
