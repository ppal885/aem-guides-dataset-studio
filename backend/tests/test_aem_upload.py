"""Tests for AEM upload functionality."""
import pytest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from app.services.aem_upload_service import AemUploadService, get_upload_service
from app.storage import get_storage


@pytest.fixture
def sample_job_id():
    """Create a sample job ID."""
    return "test-job-123"


@pytest.fixture
def sample_dataset_dir(tmp_path, sample_job_id):
    """Create a sample dataset directory."""
    dataset_dir = tmp_path / sample_job_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    
    test_file = dataset_dir / "test_file.dita"
    test_file.write_text("<?xml version='1.0'?><topic id='test'><title>Test</title></topic>")
    
    subdir = dataset_dir / "subdir"
    subdir.mkdir()
    subdir_file = subdir / "subdir_file.dita"
    subdir_file.write_text("<?xml version='1.0'?><topic id='test2'><title>Test 2</title></topic>")
    
    return dataset_dir


@pytest.fixture
def mock_upload_service(sample_dataset_dir):
    """Create a mock upload service."""
    service = Mock(spec=AemUploadService)
    service.script_path = Path(__file__).parent.parent / "scripts" / "aem_upload.js"
    return service


@pytest.fixture
def upload_request_data():
    """Sample upload request data."""
    return {
        "aem_base_url": "https://author-test.adobeaemcloud.com",
        "target_path": "content/dam/test/",
        "username": "testadmin",
        "password": "testadmin",
        "max_concurrent": 20,
        "max_upload_files": 70000
    }


class TestAemUploadService:
    """Test AEM upload service."""
    
    def test_service_initialization(self, tmp_path):
        """Test that service initializes correctly."""
        with patch('app.services.aem_upload_service.Path') as mock_path:
            mock_script = tmp_path / "scripts" / "aem_upload.js"
            mock_script.parent.mkdir(parents=True)
            mock_script.write_text("test script")
            
            mock_path.return_value.parent.parent.parent = tmp_path
            
            service = AemUploadService()
            assert service.script_path.exists() or str(service.script_path) == str(mock_script)
    
    def test_service_initialization_script_not_found(self, tmp_path):
        """Test that service raises error when script not found."""
        with patch('app.services.aem_upload_service.Path') as mock_path:
            mock_path.return_value.parent.parent.parent = tmp_path
            
            with pytest.raises(FileNotFoundError):
                AemUploadService()
    
    def test_upload_dataset_success(self, tmp_path, sample_dataset_dir):
        """Test successful upload."""
        with patch('app.services.aem_upload_service.subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({
                "success": True,
                "duration": 45.67,
                "message": "Upload completed successfully"
            })
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            
            with patch.object(AemUploadService, '__init__', lambda self: None):
                service = AemUploadService()
                service.script_path = tmp_path / "scripts" / "aem_upload.js"
                service.backend_dir = tmp_path
                result = service.upload_dataset(
                    source_path=str(sample_dataset_dir),
                    aem_base_url="https://author-test.adobeaemcloud.com",
                    target_path="content/dam/test/",
                    username="testadmin",
                    password="testadmin"
                )
                
                assert result["success"] is True
                assert result["duration"] == 45.67
                assert "message" in result
    
    def test_upload_dataset_failure(self, tmp_path, sample_dataset_dir):
        """Test upload failure."""
        with patch('app.services.aem_upload_service.subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stdout = json.dumps({
                "success": False,
                "error": "Authentication failed",
                "message": "Upload failed"
            })
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            
            with patch.object(AemUploadService, '__init__', lambda self: None):
                service = AemUploadService()
                service.script_path = tmp_path / "scripts" / "aem_upload.js"
                service.backend_dir = tmp_path
                result = service.upload_dataset(
                    source_path=str(sample_dataset_dir),
                    aem_base_url="https://author-test.adobeaemcloud.com",
                    target_path="content/dam/test/",
                    username="testadmin",
                    password="wrongpassword"
                )
                
                assert result["success"] is False
                assert "error" in result
    
    def test_upload_dataset_source_not_found(self, tmp_path):
        """Test upload with non-existent source path."""
        with patch.object(AemUploadService, '__init__', lambda self: None):
            service = AemUploadService()
            service.script_path = tmp_path / "scripts" / "aem_upload.js"
            service.backend_dir = tmp_path
            with pytest.raises(FileNotFoundError):
                service.upload_dataset(
                    source_path="/nonexistent/path",
                    aem_base_url="https://author-test.adobeaemcloud.com",
                    target_path="content/dam/test/",
                    username="testadmin",
                    password="testadmin"
                )
    
    def test_upload_dataset_timeout(self, tmp_path, sample_dataset_dir):
        """Test upload timeout."""
        from subprocess import TimeoutExpired
        
        with patch('app.services.aem_upload_service.subprocess.run') as mock_run:
            mock_run.side_effect = TimeoutExpired(["node"], 3600)
            
            with patch.object(AemUploadService, '__init__', lambda self: None):
                service = AemUploadService()
                service.script_path = tmp_path / "scripts" / "aem_upload.js"
                service.backend_dir = tmp_path
                result = service.upload_dataset(
                    source_path=str(sample_dataset_dir),
                    aem_base_url="https://author-test.adobeaemcloud.com",
                    target_path="content/dam/test/",
                    username="testadmin",
                    password="testadmin"
                )
                
                assert result["success"] is False
                assert "timed out" in result["error"].lower()
    
    def test_upload_dataset_node_not_found(self, tmp_path, sample_dataset_dir):
        """Test when Node.js is not found."""
        with patch('app.services.aem_upload_service.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("node: command not found")
            
            with patch.object(AemUploadService, '__init__', lambda self: None):
                service = AemUploadService()
                service.script_path = tmp_path / "scripts" / "aem_upload.js"
                service.backend_dir = tmp_path
                result = service.upload_dataset(
                    source_path=str(sample_dataset_dir),
                    aem_base_url="https://author-test.adobeaemcloud.com",
                    target_path="content/dam/test/",
                    username="testadmin",
                    password="testadmin"
                )
                
                assert result["success"] is False
                assert "node.js" in result["error"].lower() or "not found" in result["error"].lower()
    
    def test_upload_dataset_invalid_json_output(self, tmp_path, sample_dataset_dir):
        """Test handling of invalid JSON output."""
        with patch('app.services.aem_upload_service.subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Not valid JSON"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            
            with patch.object(AemUploadService, '__init__', lambda self: None):
                service = AemUploadService()
                service.script_path = tmp_path / "scripts" / "aem_upload.js"
                service.backend_dir = tmp_path
                result = service.upload_dataset(
                    source_path=str(sample_dataset_dir),
                    aem_base_url="https://author-test.adobeaemcloud.com",
                    target_path="content/dam/test/",
                    username="testadmin",
                    password="testadmin"
                )
                
                assert result["success"] is False
                assert "parse" in result["error"].lower()


class TestAemUploadAPI:
    """Public AEM upload API was removed from the product."""

    def test_upload_endpoint_returns_gone(
        self,
        client: TestClient,
        auth_headers: dict,
        sample_job_id: str,
        upload_request_data: dict,
    ):
        response = client.post(
            f"/api/v1/datasets/{sample_job_id}/upload-to-aem",
            json=upload_request_data,
            headers=auth_headers,
        )
        assert response.status_code == 410
        assert "no longer available" in response.json()["detail"].lower()
