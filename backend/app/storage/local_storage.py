"""Local file storage implementation."""
import os
from pathlib import Path
from typing import Optional, BinaryIO
import zipfile
from io import BytesIO


class LocalStorage:
    """Local file storage for datasets."""
    
    def __init__(self, base_path: Optional[str] = None):
        """Initialize local storage."""
        storage_path = base_path or os.getenv("STORAGE_PATH", "./storage")
        self.base_path = Path(storage_path)
        
        # Make path absolute if relative
        if not self.base_path.is_absolute():
            import os as os_module
            backend_dir = os_module.path.dirname(os_module.path.dirname(os_module.path.dirname(__file__)))
            self.base_path = Path(backend_dir) / self.base_path
        
        self.base_path = self.base_path.resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def get_job_path(self, job_id: str) -> Path:
        """Get the storage path for a job."""
        return self.base_path / job_id
    
    def exists(self, job_id: str) -> bool:
        """Check if job data exists."""
        job_path = self.get_job_path(job_id)
        return job_path.exists()
    
    def get_dataset_zip(self, job_id: str) -> Optional[BytesIO]:
        """Get dataset as zip file. For large datasets, use get_dataset_zip_stream instead."""
        job_path = self.get_job_path(job_id)
        if not job_path.exists():
            return None
        
        # For small datasets, create in memory
        # Count files first to decide if we should use streaming
        file_count = sum(1 for _ in job_path.rglob('*') if _.is_file())
        if file_count > 1000:
            # For large datasets, return None to force streaming
            return None
        
        # Create zip from directory
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(job_path):
                for file in files:
                    file_path = Path(root) / file
                    arc_name = file_path.relative_to(job_path)
                    zip_file.write(file_path, arc_name)
        
        zip_buffer.seek(0)
        return zip_buffer
    
    def get_dataset_zip_stream(self, job_id: str):
        """Stream dataset as zip file for large datasets. Returns a generator."""
        job_path = self.get_job_path(job_id)
        if not job_path.exists():
            return None
        
        # Use temporary file for large datasets to avoid memory issues
        import tempfile
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
                for root, dirs, files in os.walk(job_path):
                    for file in files:
                        file_path = Path(root) / file
                        arc_name = file_path.relative_to(job_path)
                        zip_file.write(file_path, arc_name)
            
            # Stream the file in chunks
            def generate():
                chunk_size = 8192 * 4
                with open(temp_zip_path, 'rb') as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
                # Cleanup temp file
                try:
                    os.unlink(temp_zip_path)
                except Exception:
                    pass
            
            return generate()
        except Exception:
            # Cleanup on error
            try:
                os.unlink(temp_zip_path)
            except Exception:
                pass
            return None
    
    def get_dataset_structure(self, job_id: str) -> Optional[dict]:
        """Get dataset structure directly from filesystem without creating ZIP."""
        job_path = self.get_job_path(job_id)
        if not job_path.exists():
            return None
        
        structure = {
            "files": [],
            "directories": [],
        }
        
        # Track directories we've seen
        seen_dirs = set()
        
        # Walk filesystem directly
        for item in job_path.rglob('*'):
            rel_path = item.relative_to(job_path)
            path_str = str(rel_path).replace('\\', '/')
            
            if item.is_file():
                try:
                    size = item.stat().st_size
                    structure["files"].append({
                        "path": path_str,
                        "size": size,
                        "compressed_size": None,  # Not available without ZIP
                    })
                except (OSError, PermissionError):
                    continue
            elif item.is_dir():
                # Add parent directories
                parts = path_str.split('/')
                for i in range(len(parts)):
                    dir_path = '/'.join(parts[:i+1])
                    if dir_path and dir_path not in seen_dirs:
                        seen_dirs.add(dir_path)
                        structure["directories"].append(dir_path)
        
        return structure
    
    def get_file(self, job_id: str, file_path: str) -> Optional[bytes]:
        """Get a specific file from the dataset."""
        full_path = self.get_job_path(job_id) / file_path
        if not full_path.exists() or not full_path.is_file():
            return None
        return full_path.read_bytes()
    
    def list_files(self, job_id: str, directory: str = "") -> list:
        """List files in a directory."""
        dir_path = self.get_job_path(job_id) / directory
        if not dir_path.exists():
            return []
        
        files = []
        for item in dir_path.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(self.get_job_path(job_id))
                files.append(str(rel_path))
        return files
    
    def save_dataset(self, job_id: str, files: dict[str, bytes]) -> None:
        """Save dataset files."""
        job_path = self.get_job_path(job_id)
        job_path.mkdir(parents=True, exist_ok=True)
        
        for file_path, content in files.items():
            file_full_path = job_path / file_path
            file_full_path.parent.mkdir(parents=True, exist_ok=True)
            file_full_path.write_bytes(content)
    
    def save_dataset_batch(self, job_id: str, files_batch: dict[str, bytes]) -> None:
        """Save a batch of dataset files. More memory-efficient for large datasets."""
        job_path = self.get_job_path(job_id)
        job_path.mkdir(parents=True, exist_ok=True)
        
        for file_path, content in files_batch.items():
            file_full_path = job_path / file_path
            file_full_path.parent.mkdir(parents=True, exist_ok=True)
            file_full_path.write_bytes(content)
    
    def delete_job_data(self, job_id: str) -> bool:
        """Delete all data for a job. Returns True if deleted, False if not found."""
        import shutil
        job_path = self.get_job_path(job_id)
        
        if not job_path.exists():
            return False
        
        try:
            if job_path.is_dir():
                shutil.rmtree(job_path)
            else:
                job_path.unlink()
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to delete job data for {job_id}: {e}", exc_info=True)
            return False


# Global storage instance
_storage_instance: Optional[LocalStorage] = None


def get_storage() -> LocalStorage:
    """Get the storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalStorage()
    return _storage_instance
