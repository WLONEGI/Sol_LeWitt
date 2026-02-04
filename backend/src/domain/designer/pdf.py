import logging
from io import BytesIO
from typing import Iterable

from PIL import Image

logger = logging.getLogger(__name__)


def assemble_pdf_from_images(image_bytes_list: Iterable[bytes]) -> bytes:
    """
    Assemble a multi-page PDF from a list of image bytes.
    Each image becomes one page (1page=1slide).
    """
    images: list[Image.Image] = []
    for idx, image_bytes in enumerate(image_bytes_list, start=1):
        try:
            img = Image.open(BytesIO(image_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)
        except Exception as e:
            logger.error("Failed to load image %s for PDF: %s", idx, e)
            raise

    if not images:
        raise ValueError("No images provided for PDF assembly.")

    # Normalize size (optional) to avoid inconsistent page dimensions
    base_size = images[0].size
    normalized: list[Image.Image] = []
    for img in images:
        if img.size != base_size:
            normalized.append(img.resize(base_size, Image.LANCZOS))
        else:
            normalized.append(img)

    buffer = BytesIO()
    normalized[0].save(buffer, format="PDF", save_all=True, append_images=normalized[1:])
    buffer.seek(0)
    return buffer.read()
