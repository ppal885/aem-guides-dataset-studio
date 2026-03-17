"""Dataset packager - create ZIP from bundle."""
import zipfile
from pathlib import Path
from uuid import uuid4

from app.storage import get_storage
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def package_bundle(bundle_dir: Path, jira_id: str, run_id: str) -> Path:
    """
    Package bundle directory into ZIP.
    Output: {storage}/zips/{jira_id}/{run_id}/{jira_id}_bundle.zip
    """
    storage = get_storage()
    zip_parent = storage.base_path / "zips" / jira_id / run_id
    zip_parent.mkdir(parents=True, exist_ok=True)

    zip_name = f"{jira_id}_bundle.zip"
    zip_path = zip_parent / zip_name

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        bundle_path = Path(bundle_dir)
        for f in bundle_path.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(bundle_path)
                zf.write(f, str(arcname).replace("\\", "/"))

    return zip_path.resolve()
