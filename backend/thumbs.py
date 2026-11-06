"""Product photo thumbnails: trim the flat border a photo comes with, then resize.

Shop and Open Food Facts photos often sit in a wide white (or grey) margin, so a pack looks
small in one tile and huge in the next. Trimming the margin makes every product fill its frame.
"""
import io

from PIL import Image, ImageChops, ImageOps, ImageStat

TOLERANCE = 30  # max per-channel distance from the background colour that still counts as background
CORNER = 6  # px sampled at each corner to find the background colour
MARGIN = 0.03  # keep a little air around the trimmed product, as a share of its longer side


def _background(img: Image.Image) -> tuple[int, int, int] | None:
    """The border colour if all four corners agree on one, else None (photo has no flat border)."""
    w, h = img.size
    c = min(CORNER, w // 4, h // 4) or 1
    boxes = [(0, 0, c, c), (w - c, 0, w, c), (0, h - c, c, h), (w - c, h - c, w, h)]
    means = [tuple(int(v) for v in ImageStat.Stat(img.crop(b)).mean[:3]) for b in boxes]
    ref = means[0]
    if all(max(abs(a - b) for a, b in zip(m, ref)) <= TOLERANCE for m in means[1:]):
        return tuple(sum(m[i] for m in means) // 4 for i in range(3))  # type: ignore[return-value]
    return None


def trim(img: Image.Image) -> Image.Image:
    """Crop away a flat border around the product. Returns the image unchanged if there is none."""
    bg = _background(img)
    if bg is None:
        return img
    diff = ImageChops.difference(img, Image.new("RGB", img.size, bg)).convert("L")
    mask = diff.point(lambda v: 255 if v > TOLERANCE else 0)
    box = mask.getbbox()
    if not box:
        return img
    left, top, right, bottom = box
    pad = int(max(right - left, bottom - top) * MARGIN)
    box = (max(0, left - pad), max(0, top - pad), min(img.width, right + pad), min(img.height, bottom + pad))
    # A crop this small is a speck of noise, not a product.
    if box[2] - box[0] < 12 or box[3] - box[1] < 12:
        return img
    return img.crop(box)


def thumbnail(data: bytes, width: int) -> bytes:
    """Trimmed, resized WebP of an image file. Raises PIL errors for files that aren't images."""
    with Image.open(io.BytesIO(data)) as src:
        src = ImageOps.exif_transpose(src)
        if src.mode in ("RGBA", "LA", "P"):
            rgba = src.convert("RGBA")
            img = Image.new("RGB", rgba.size, (255, 255, 255))
            img.paste(rgba, mask=rgba.split()[-1])
        else:
            img = src.convert("RGB")
    img = trim(img)
    img.thumbnail((width, width * 2))
    out = io.BytesIO()
    img.save(out, "WEBP", quality=82, method=4)
    return out.getvalue()
