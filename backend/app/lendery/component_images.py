import os
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener


register_heif_opener()


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_EDGE = 1200


def upload_root() -> Path:
    configured = os.getenv("LIBTOOLS_UPLOAD_DIR")
    if configured:
        return Path(configured)

    railway_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_volume:
        return Path(railway_volume) / "uploads"

    return Path(__file__).resolve().parents[2] / "uploads"


def component_image_path(component_id: int) -> Path:
    return upload_root() / "lendery" / "components" / f"{component_id}.webp"


def component_image_url(component_id: int) -> str:
    return f"/lendery/components/{component_id}/image"


async def save_component_image(component_id: int, upload: UploadFile) -> Path:
    contents = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not contents:
        raise ValueError("Choose an image to upload.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise ValueError("The photo must be 10 MB or smaller.")

    try:
        with Image.open(BytesIO(contents)) as source:
            source.verify()
        with Image.open(BytesIO(contents)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("The photo dimensions are too large.")
            image = ImageOps.exif_transpose(source)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            processed = image.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(
            "Upload a valid JPEG, PNG, WebP, HEIC, or HEIF image."
        ) from exc

    destination = component_image_path(component_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    try:
        processed.save(temporary, format="WEBP", quality=84, method=6)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def delete_component_image(component_id: int) -> None:
    component_image_path(component_id).unlink(missing_ok=True)
