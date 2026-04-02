"""Рендеринг SVG в PNG для Telegram."""
import logging
import re
import tempfile
from pathlib import Path

log = logging.getLogger("bot.renderer")


def extract_all_svgs(text):
    results = []
    pattern = re.compile(r"Variant|variant|\u0412\u0430\u0440\u0456\u0430\u043d\u0442")
    blocks = re.split(r"\n(?=(?:Variant|\u0412\u0430\u0440\u0456\u0430\u043d\u0442)\s*\d+)", text)
    
    for block in blocks:
        name_match = re.match(r"(?:Variant|\u0412\u0430\u0440\u0456\u0430\u043d\u0442)\s*\d+\s*[\u2014\-]?\s*([^\n]*)", block)
        name = name_match.group(1).strip() if name_match else "design"
        
        svg_match = re.search(r"```svg\s*(<svg[\s\S]*?</svg>)\s*```", block)
        if not svg_match:
            svg_match = re.search(r"(<svg[\s\S]*?</svg>)", block)
        
        if svg_match:
            results.append((name, svg_match.group(1)))
    
    if not results:
        for match in re.finditer(r"(<svg[\s\S]*?</svg>)", text):
            results.append(("design", match.group(1)))
    
    return results


def svg_to_png(svg_content, output_path):
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg_content.encode("utf-8"), write_to=output_path, scale=2.0)
        return True
    except Exception as e:
        log.error(f"SVG->PNG: {e}")
        return False


def save_svg(svg_content, output_path):
    try:
        Path(output_path).write_text(svg_content, encoding="utf-8")
        return True
    except Exception as e:
        log.error(f"Save SVG: {e}")
        return False


def clean_text(text):
    text = re.sub(r"```svg[\s\S]*?```", "", text)
    text = re.sub(r"<svg[\s\S]*?</svg>", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def process_ai_response(text, base_name="samuel"):
    result = {"text": clean_text(text), "svg_paths": [], "png_paths": [], "has_visual": False}
    tmp_dir = Path(tempfile.gettempdir()) / "samuel"
    tmp_dir.mkdir(exist_ok=True)
    svgs = extract_all_svgs(text)
    if not svgs:
        return result
    for i, (name, svg) in enumerate(svgs):
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", name)[:30]
        svg_path = str(tmp_dir / f"{base_name}_{i+1}_{safe}.svg")
        png_path = str(tmp_dir / f"{base_name}_{i+1}_{safe}.png")
        if save_svg(svg, svg_path):
            result["svg_paths"].append((name, svg_path))
        if svg_to_png(svg, png_path):
            result["png_paths"].append((name, png_path))
            result["has_visual"] = True
    log.info(f"Оброблено {len(svgs)} SVG, {len(result['png_paths'])} PNG")
    return result
