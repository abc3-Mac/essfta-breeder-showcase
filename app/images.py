"""Photo intake: validate, auto-orient, downscale, and store as JPEG.

Phone cameras produce huge files; we normalize every upload to a sane max
dimension and strip EXIF so the booklet stays lightweight and print-clean.
"""
import io
from pathlib import Path

from PIL import Image, ImageOps

from .config import UPLOAD_DIR
from .db import new_token

MAX_DIM = 2000  # longest edge, px — plenty for print at booklet size
JPEG_QUALITY = 88


def save_photo(raw: bytes, kennel_id: int, dog_id: int, slot: int) -> str:
    """Process raw upload bytes and return the stored filename (not full path)."""
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)          # honor camera rotation
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)

    fname = f"k{kennel_id}_d{dog_id}_p{slot}_{new_token(6)}.jpg"
    out = UPLOAD_DIR / fname
    img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return fname


def delete_photo(fname: str):
    if not fname:
        return
    p = UPLOAD_DIR / fname
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
