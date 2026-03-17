"""Service for uploading datasets to AEM using Node.js script."""
import json
import subprocess
import os
from pathlib import Path
from typing import Dict, Optional
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


class AemUploadService:
    """Service to handle AEM uploads via Node.js script."""
    
    def __init__(self):
        """Initialize the upload service."""
        backend_dir = Path(__file__).parent.parent.parent
        self.backend_dir = backend_dir
        self.script_path = backend_dir / "scripts" / "aem_upload.js"
        self.package_json_path = backend_dir / "package.json"
        self.node_modules_path = backend_dir / "node_modules"
        
        if not self.script_path.exists():
            raise FileNotFoundError(f"Upload script not found at {self.script_path}")
        
        self._ensure_dependencies_installed()
    
    def _check_node_available(self) -> bool:
        """Check if Node.js is available in the system."""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _ensure_dependencies_installed(self):
        """Ensure Node.js dependencies are installed."""
        if not self.node_modules_path.exists() or not (self.node_modules_path / "@adobe" / "aem-upload").exists():
            if not self._check_node_available():
                logger.warning_structured(
                    "Node.js not available, skipping dependency installation",
                    extra_fields={}
                )
                return
            
            if not self.package_json_path.exists():
                logger.warning_structured(
                    "package.json not found, skipping dependency installation",
                    extra_fields={"package_json_path": str(self.package_json_path)}
                )
                return
            
            logger.info_structured(
                "Installing Node.js dependencies",
                extra_fields={"backend_dir": str(self.backend_dir)}
            )
            
            try:
                result = subprocess.run(
                    ["npm", "install"],
                    cwd=str(self.backend_dir),
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False
                )
                
                if result.returncode != 0:
                    logger.error_structured(
                        "Failed to install Node.js dependencies",
                        extra_fields={
                            "stderr": result.stderr[:500] if result.stderr else None,
                            "stdout": result.stdout[:500] if result.stdout else None
                        }
                    )
                else:
                    logger.info_structured(
                        "Node.js dependencies installed successfully",
                        extra_fields={}
                    )
            except subprocess.TimeoutExpired:
                logger.error_structured(
                    "npm install timed out",
                    extra_fields={}
                )
            except Exception as e:
                logger.error_structured(
                    "Error installing Node.js dependencies",
                    extra_fields={"error": str(e)},
                    exc_info=True
                )
    
    def _detect_content_dam_prefix(self, source_path: str) -> Optional[str]:
        """
        Detect if source directory starts with content/dam/{subfolder}/ structure.
        
        Args:
            source_path: Path to the source directory
            
        Returns:
            The prefix to strip (e.g., 'content/dam/test/') or None if not found
        """
        try:
            source_dir = Path(source_path)
            if not source_dir.exists() or not source_dir.is_dir():
                return None
            
            content_dir = source_dir / "content"
            if not content_dir.exists() or not content_dir.is_dir():
                logger.debug_structured(
                    "No 'content' directory found in source",
                    extra_fields={"source_path": source_path}
                )
                return None
            
            dam_dir = content_dir / "dam"
            if not dam_dir.exists() or not dam_dir.is_dir():
                logger.debug_structured(
                    "No 'dam' directory found in content",
                    extra_fields={"source_path": source_path}
                )
                return None
            
            subfolders = [item for item in dam_dir.iterdir() if item.is_dir()]
            if not subfolders:
                logger.debug_structured(
                    "No subfolders found in content/dam",
                    extra_fields={"source_path": source_path}
                )
                return None
            
            first_subfolder = subfolders[0].name
            prefix = f"content/dam/{first_subfolder}/"
            
            logger.info_structured(
                "Detected content/dam prefix in source directory",
                extra_fields={
                    "source_path": source_path,
                    "detected_prefix": prefix,
                    "subfolder": first_subfolder
                }
            )
            
            return prefix
            
        except Exception as e:
            logger.warning_structured(
                "Error detecting content/dam prefix",
                extra_fields={
                    "source_path": source_path,
                    "error": str(e)
                },
                exc_info=True
            )
            return None
    
    def _get_upload_source_path(
        self, 
        source_path: str, 
        detected_prefix: Optional[str]
    ) -> str:
        """
        Get the optimized upload source path by pointing directly to subdirectory after prefix.
        
        This avoids copying files - we simply point the upload to the subdirectory,
        which is much more efficient for large datasets.
        
        Args:
            source_path: Path to the source directory
            detected_prefix: Prefix to strip (e.g., 'content/dam/test/') or None
            
        Returns:
            Path to use for upload (points to subdirectory after prefix if detected)
        """
        if not detected_prefix:
            logger.debug_structured(
                "No prefix detected, using source directory as-is",
                extra_fields={"source_path": source_path}
            )
            return source_path
        
        try:
            source_dir = Path(source_path)
            prefix_normalized = detected_prefix.rstrip('/')
            prefix_path = source_dir / prefix_normalized
            
            if not prefix_path.exists() or not prefix_path.is_dir():
                logger.warning_structured(
                    "Detected prefix path does not exist, using source directory as-is",
                    extra_fields={
                        "source_path": source_path,
                        "detected_prefix": detected_prefix,
                        "prefix_path": str(prefix_path)
                    }
                )
                return source_path
            
            upload_path = str(prefix_path.resolve())
            
            logger.info_structured(
                "Using optimized upload path (no file copying required)",
                extra_fields={
                    "source_path": source_path,
                    "detected_prefix": detected_prefix,
                    "upload_path": upload_path,
                    "optimization": "zero_copy"
                }
            )
            
            return upload_path
            
        except Exception as e:
            logger.warning_structured(
                "Error determining upload path, falling back to source directory",
                extra_fields={
                    "source_path": source_path,
                    "detected_prefix": detected_prefix,
                    "error": str(e)
                },
                exc_info=True
            )
            return source_path
    
    def upload_dataset(
        self,
        source_path: str,
        aem_base_url: str,
        target_path: str,
        username: str,
        password: str,
        max_concurrent: int = 20,
        max_upload_files: int = 70000
    ) -> Dict:
        """
        Upload dataset to AEM instance.
        
        Args:
            source_path: Path to the dataset directory
            aem_base_url: AEM instance base URL
            target_path: Target path in AEM (e.g., 'content/dam/Priyanka_Perf/')
            username: AEM username
            password: AEM password
            max_concurrent: Maximum concurrent uploads (default: 20)
            max_upload_files: Maximum files to upload (default: 70000)
        
        Returns:
            Dict with upload status and results
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source path does not exist: {source_path}")
        
        if not os.path.isdir(source_path):
            raise ValueError(f"Source path is not a directory: {source_path}")
        
        detected_prefix = self._detect_content_dam_prefix(source_path)
        upload_path = self._get_upload_source_path(source_path, detected_prefix)
        
        logger.info_structured(
            "Starting AEM upload",
            extra_fields={
                "source_path": source_path,
                "upload_path": upload_path,
                "detected_prefix": detected_prefix,
                "optimized": upload_path != source_path,
                "aem_base_url": aem_base_url,
                "target_path": target_path,
                "max_concurrent": max_concurrent,
                "max_upload_files": max_upload_files
            }
        )
        
        try:
            config = {
                "sourcePath": str(Path(upload_path).resolve()),
                "aemBaseUrl": aem_base_url.rstrip('/'),
                "targetPath": target_path.lstrip('/'),
                "username": username,
                "password": password,
                "maxConcurrent": max_concurrent,
                "maxUploadFiles": max_upload_files
            }
            
            config_json = json.dumps(config)
            script_path_str = str(self.script_path)
            
            node_command = ["node", script_path_str, config_json]
            
            logger.info_structured(
                "Executing Node.js upload script",
                extra_fields={
                    "script_path": script_path_str,
                    "source_path": source_path
                }
            )
            
            result = subprocess.run(
                node_command,
                capture_output=True,
                text=True,
                timeout=3600,
                check=False,
                cwd=str(self.backend_dir)
            )
            
            output = result.stdout.strip() if result.stdout else ""
            error_output = result.stderr.strip() if result.stderr else ""
            
            if result.returncode != 0:
                logger.error_structured(
                    "AEM upload script failed",
                    extra_fields={
                        "returncode": result.returncode,
                        "stderr": error_output[:500] if error_output else None,
                        "stdout": output[:500] if output else None
                    }
                )
                
                error_text = output or error_output or "Unknown error"
                try:
                    error_result = json.loads(error_text)
                    return error_result
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": error_text[:500],
                        "message": "Upload failed"
                    }
            
            if not output:
                logger.error_structured(
                    "AEM upload script returned no output",
                    extra_fields={
                        "returncode": result.returncode,
                        "stderr": error_output[:500] if error_output else None
                    }
                )
                return {
                    "success": False,
                    "error": error_output[:500] if error_output else "No output from upload script",
                    "message": "Upload failed"
                }
            
            # Clean output - remove any non-JSON lines (library logs)
            # Find the last line that looks like JSON (starts with { and ends with })
            output_lines = output.strip().split('\n')
            json_output = None
            
            # Try to find JSON in the output (usually the last line)
            for line in reversed(output_lines):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        json_output = line
                        break
                    except Exception:
                        continue
            
            # If no JSON found, try parsing the entire output
            if json_output is None:
                json_output = output.strip()
            
            try:
                upload_result = json.loads(json_output)
                if upload_result.get("success"):
                    logger.info_structured(
                        "AEM upload completed successfully",
                        extra_fields={
                            "duration": upload_result.get("duration"),
                            "source_path": source_path,
                            "upload_path": upload_path,
                            "detected_prefix": detected_prefix,
                            "optimized": upload_path != source_path
                        }
                    )
                else:
                    logger.warning_structured(
                        "AEM upload completed with errors",
                        extra_fields={
                            "error": upload_result.get("error"),
                            "source_path": source_path,
                            "upload_path": upload_path,
                            "detected_prefix": detected_prefix
                        }
                    )
                
                return upload_result
            except json.JSONDecodeError as e:
                logger.error_structured(
                    "Failed to parse upload script output",
                    extra_fields={
                        "stdout": output[:500],
                        "stderr": error_output[:500] if error_output else None,
                        "error": str(e)
                    }
                )
                return {
                    "success": False,
                    "error": f"Failed to parse script output: {str(e)}. Output: {output[:200]}",
                    "message": "Upload failed"
                }
        
        except subprocess.TimeoutExpired:
            logger.error_structured(
                "AEM upload timed out",
                extra_fields={
                    "source_path": source_path,
                    "upload_path": upload_path,
                    "detected_prefix": detected_prefix
                }
            )
            return {
                "success": False,
                "error": "Upload timed out after 1 hour",
                "message": "Upload failed"
            }
        
        except FileNotFoundError:
            logger.error_structured(
                "Node.js not found",
                extra_fields={"script_path": str(self.script_path)}
            )
            return {
                "success": False,
                "error": "Node.js runtime not found. Please ensure Node.js is installed.",
                "message": "Upload failed"
            }
        
        except Exception as e:
            logger.error_structured(
                "AEM upload service error",
                extra_fields={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "source_path": source_path,
                    "upload_path": upload_path,
                    "detected_prefix": detected_prefix
                },
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Upload failed"
            }


def get_upload_service() -> AemUploadService:
    """Get the AEM upload service instance."""
    return AemUploadService()
