import math
import os
import shutil
from pathlib import Path
from uuid import uuid4


UPLOAD_ROOT = Path("shared/uploads")


def save_upload(upload_file, folder: str = "") -> str | None:
    if not upload_file or not getattr(upload_file, "filename", ""):
        return None

    target_dir = UPLOAD_ROOT / folder if folder else UPLOAD_ROOT
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload_file.filename).suffix
    safe_name = f"{uuid4().hex}{suffix}"
    target_path = target_dir / safe_name

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    relative_parts = ["uploads"]
    if folder:
        relative_parts.append(folder.strip("/\\"))
    relative_parts.append(safe_name)
    return "/" + "/".join(relative_parts)


def upload_path_to_disk(public_path: str | None) -> str | None:
    if not public_path:
        return None
    return str(Path("shared") / public_path.lstrip("/"))


def distance_in_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius * c
