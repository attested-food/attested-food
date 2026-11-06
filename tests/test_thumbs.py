import io

import pytest
from PIL import Image, ImageDraw

from backend.thumbs import thumbnail, trim


def png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def product_on(bg: tuple[int, int, int], size=(400, 400), box=(150, 175, 250, 225)) -> Image.Image:
    img = Image.new("RGB", size, bg)
    ImageDraw.Draw(img).rectangle(box, fill=(200, 30, 30))
    return img


@pytest.mark.parametrize("bg", [(255, 255, 255), (238, 238, 236), (30, 30, 30)])
def test_trims_flat_border(bg):
    out = trim(product_on(bg))
    # 101x51 product plus 3% air on each side
    assert 101 <= out.width <= 101 + 2 * 4 and 51 <= out.height <= 51 + 2 * 4


def test_keeps_photo_without_flat_border():
    img = Image.new("RGB", (200, 200))
    for x in range(200):
        ImageDraw.Draw(img).line([(x, 0), (x, 199)], fill=(x, 255 - x, 120))
    assert trim(img).size == (200, 200)


def test_keeps_product_that_fills_the_photo():
    img = product_on((255, 255, 255), box=(2, 2, 397, 397))
    assert trim(img).size[0] >= 390


def test_thumbnail_is_webp_and_resized():
    data = thumbnail(png(product_on((255, 255, 255), size=(1200, 1200), box=(100, 100, 1100, 1100))), 300)
    with Image.open(io.BytesIO(data)) as img:
        assert img.format == "WEBP" and img.width <= 300


def test_thumbnail_flattens_transparency_on_white():
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((40, 40, 60, 60), fill=(10, 120, 10, 255))
    with Image.open(io.BytesIO(thumbnail(png(img), 200))) as out:
        assert out.width < 40  # transparent margin trimmed


def test_thumbnail_rejects_non_images():
    with pytest.raises(Exception):
        thumbnail(b"not an image", 200)
