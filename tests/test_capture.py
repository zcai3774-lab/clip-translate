from __future__ import annotations

import io

from PIL import Image

from cliplens.capture import prepare_image


def test_small_image_stays_png() -> None:
    image = Image.new("RGB", (120, 80), "#123456")
    data, mime = prepare_image(image)

    assert mime == "image/png"
    assert data.startswith(b"\x89PNG")
    decoded = Image.open(io.BytesIO(data))
    assert decoded.size == (120, 80)
    assert decoded.mode == "RGB"


def test_large_image_is_scaled_down() -> None:
    image = Image.new("RGB", (800, 400), "#654321")
    data, mime = prepare_image(image, max_side=200)

    assert mime == "image/png"
    assert Image.open(io.BytesIO(data)).size == (200, 100)


def test_noise_image_falls_back_to_jpeg() -> None:
    image = Image.effect_noise((1800, 1800), 128).convert("RGB")
    data, mime = prepare_image(image)

    assert mime == "image/jpeg"
    assert data.startswith(b"\xff\xd8")
    assert len(data) < 4_500_000
