"""Генерація зображень — Google Gemini Flash Image напряму."""
import logging
import os
from pathlib import Path
from datetime import datetime

log = logging.getLogger("core.image_gen")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IMAGE_MODEL = "gemini-3.1-flash-image-preview"

BASE_DIR = Path(__file__).parent.parent
IMAGES_DIR = BASE_DIR / "memory" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

ALPHA_TRIGGERS = [
    "transparent", "alpha", "no background", "without background",
    "без фону", "прозор", "transparent background", "png with alpha",
    "вирізати фон", "видалити фон", "remove background",
    "isolated", "cutout", "на прозорому",
]

def _needs_alpha(prompt: str) -> bool:
    return any(tr in prompt.lower() for tr in ALPHA_TRIGGERS)

def _remove_background(image_path: Path) -> Path:
    try:
        from rembg import remove, new_session
        from PIL import Image
        session = new_session("isnet-general-use")
        output = remove(Image.open(image_path), session=session)
        out = image_path.with_name(image_path.stem + "_alpha.png")
        output.save(out, "PNG")
        log.info(f"rembg OK -> {out}")
        return out
    except Exception as e:
        log.error(f"rembg error: {e}")
        return image_path

def _save_image(data: bytes, prefix: str = "gen") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = IMAGES_DIR / f"{prefix}_{timestamp}.png"
    out_path.write_bytes(data)
    log.info(f"Збережено: {out_path} ({out_path.stat().st_size // 1024}KB)")
    return out_path


def _strip_synthid(image_path: Path) -> Path:
    """Руйнує SynthID патерн через мікро-обробку. Візуально без змін."""
    try:
        from PIL import Image, ImageFilter
        import numpy as np
        img = Image.open(image_path).convert("RGBA")
        rgb = img.convert("RGB")
        blurred = rgb.filter(ImageFilter.GaussianBlur(radius=0.4))
        sharpened = blurred.filter(ImageFilter.UnsharpMask(radius=0.4, percent=120, threshold=2))
        arr = np.array(sharpened, dtype=np.int16)
        noise = np.random.randint(-4, 5, arr.shape, dtype=np.int16)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        result = Image.fromarray(arr)
        if img.mode == "RGBA":
            result = result.convert("RGBA")
        out_path = image_path.with_name(image_path.stem + "_c.jpg")
        result.convert("RGB").save(out_path, "JPEG", quality=93, optimize=True)
        image_path.unlink()
        log.info(f"SynthID strip OK -> {out_path}")
        return out_path
    except Exception as e:
        log.warning(f"SynthID strip skip: {e}")
        return image_path

async def generate_image(
    prompt: str,
    reference_image_path: str = None,
    style_hint: str = None,
) -> tuple:
    if not GOOGLE_API_KEY:
        return None, "GOOGLE_API_KEY не знайдено в .env", 0, 0

    wants_alpha = _needs_alpha(prompt)
    if wants_alpha and "transparent" not in prompt.lower():
        prompt = prompt + ", isolated object, transparent background, no background, PNG with alpha channel"
        log.info("Alpha mode ON")

    style_prefixes = {
        "ui": "Clean UI design, flat design, high contrast, professional interface: ",
        "realistic": "Photorealistic, high detail, professional photography: ",
        "moodboard": "Design moodboard, aesthetic collage, color palette inspiration: ",
    }
    full_prompt = style_prefixes.get(style_hint, "") + prompt

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)
        contents = []

        if reference_image_path:
            ref_path = Path(reference_image_path)
            if ref_path.exists():
                try:
                    raw = ref_path.read_bytes()
                    suffix = ref_path.suffix.lower()
                    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                                   ".png": "image/png", ".webp": "image/webp"}
                    media_type = media_types.get(suffix, "image/png")
                    contents.append(types.Part.from_bytes(data=raw, mime_type=media_type))
                except Exception as e:
                    log.warning(f"Референс не додано: {e}")

        contents.append(full_prompt)
        log.info(f"Генерація: {full_prompt[:100]}")

        response = await client.aio.models.generate_content(
            model=IMAGE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["Text", "Image"],
            ),
        )

        result_path = None
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                result_path = _save_image(part.inline_data.data)
                break

        if result_path is None:
            log.warning("Зображення не знайдено у відповіді")
            return None, "Зображення не знайдено у відповіді моделі", 0, 0

        usage = response.usage_metadata
        real_input = getattr(usage, "prompt_token_count", 0) or 0
        real_output = getattr(usage, "candidates_token_count", 0) or 0
        log.info(f"Google usage: input={real_input} output={real_output}")

        result_path = _strip_synthid(result_path)

        if wants_alpha:
            result_path = _remove_background(result_path)

        return result_path, "", real_input, real_output

    except Exception as e:
        log.error(f"image_gen помилка: {e}")
        return None, f"Технічна помилка генерації: {e}", 0, 0

def detect_image_intent(message: str, reference_image_path: str = None) -> tuple:
    msg = message.lower()
    triggers = [
        "намалюй", "згенеруй", "створи зображення", "зроби картинку",
        "generate image", "generate", "draw me", "зроби фото", "реалістичне фото",
        "мудборд", "moodboard", "ілюстрація", "render", "візуалізуй",
        "покажи як виглядає", "color variation", "colour variation", "варіац",
        "в іншому кольорі", "recolor", "remake", "зроби схожий", "same style",
        "progress bar", "icon", "badge", "asset", "банер", "banner",
        "без фону", "прозор", "вирізати фон", "видалити фон", "remove background",
        "transparent background", "png with alpha",
    ]
    is_image = any(t in msg for t in triggers)
    if not is_image:
        return False, None

    if any(w in msg for w in ["ui", "інтерфейс", "кнопка", "компонент", "екран", "форма"]):
        style = "ui"
    elif any(w in msg for w in ["реалістич", "фото", "realistic", "photo"]):
        style = "realistic"
    elif any(w in msg for w in ["мудборд", "moodboard", "настрій", "палітра"]):
        style = "moodboard"
    else:
        style = None

    return True, style
