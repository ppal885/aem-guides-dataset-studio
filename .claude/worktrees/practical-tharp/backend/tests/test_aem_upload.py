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
    """Test AEM upload API endpoints."""
    
    def test_upload_endpoint_success(
        self, 
        client: TestClient, 
        auth_headers: dict,
        sample_job_id: str,
        sample_dataset_dir: Path,
        upload_request_data: dict,
        tmp_path
    ):
        """Test successful upload via API."""
        from app.core.auth import UserIdentity
        
        with patch('app.api.v1.routes.dataset_explorer.crud.get_job') as mock_get_job, \
             patch('app.api.v1.routes.dataset_explorer.get_storage') as mock_get_storage, \
             patch('app.api.v1.routes.dataset_explorer.get_upload_service') as mock_get_service:
            
            mock_job = Mock()
            mock_job.id = sample_job_id
            mock_job.user_id = "test-user-1"
            mock_job.name = "Test Job"
            mock_get_job.return_value = mock_job
            
            mock_storage = Mock()
            mock_storage.exists.return_value = True
            mock_storage.get_job_path.return_value = sample_dataset_dir
            mock_get_storage.return_value = mock_storage
            
            mock_service = Mock()
            mock_service.upload_dataset.return_value = {
                "success": True,
                "duration": 45.67,
                "message": "Upload completed successfully"
            }
            mock_get_service.return_value = mock_service
            
            response = client.post(
                f"/api/v1/datasets/{sample_job_id}/upload-to-aem",
                json=upload_request_data,
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["job_id"] == sample_job_id
            assert "duration" in data
    
    def test_upload_endpoint_job_not_found(
        self,
        client: TestClient,
        auth_headers: dict,
        upload_request_data: dict
    ):
        """Test upload with non-existent job."""
        with patch('app.api.v1.routes.dataset_explorer.crud.get_job') as mock_get_job:
            mock_get_job.return_value = None
            
            response = client.post(
                "/api/v1/datasets/nonexistent-job/upload-to-aem",
                json=upload_request_data,
                headers=auth_headers
            )
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
    
    def test_upload_endpoint_dataset_not_found(
        self,
        client: TestClient,
        auth_headers: dict,
        sample_job_id: str,
        upload_request_data: dict
    ):
        """Test upload when dataset doesn't exist."""
        with patch('app.api.v1.routes.dataset_explorer.crud.get_job') as mock_get_job, \
             patch('app.api.v1.routes.dataset_explorer.get_storage') as mock_get_storage:
            
            mock_job = Mock()
            mock_job.id = sample_job_id
            mock_job.user_id = "test-user-1"
            mock_get_job.return_value = mock_job
            
            mock_storage = Mock()
            mock_storage.exists.return_value = False
            mock_get_storage.return_value = mock_storage
            
            response = client.post(
                f"/api/v1/datasets/{sample_job_id}/upload-to-aem",
                json=upload_request_data,
                headers=auth_headers
            )
            
            assert response.status_code == 404
            assert "dataset not found" in response.json()["detail"].lower()
    
    def test_upload_endpoint_permission_denied(
        self,
        client: TestClient,
        auth_headers: dict,
        sample_job_id: str,
        upload_request_data: dict
    ):
        """Test upload with wrong user permissions."""
        with patch('app.api.v1.routes.dataset_explorer.crud.get_job') as mock_get_job:
            mock_job = Mock()
            mock_job.id = sample_job_id
            mock_job.user_id = "different-user-id"
            mock_get_job.return_value = mock_job
            
            response = client.post(
                f"/api/v1/datasets/{sample_job_id}/upload-to-aem",
                json=upload_request_data,
                headers=auth_headers
            )
            
            assert response.status_code == 403
            assert "denied" in response.json()["detail"].lower() or "access" in response.json()["detail"].lower()
    
    def test_upload_endpoint_upload_failure(
        self,
        client: TestClient,
        auth_headers: dict,
        sample_job_id: str,
        sample_dataset_dir: Path,
        upload_request_data: dict
    ):
        """Test upload failure handling."""
        with patch('app.api.v1.routes.dataset_explorer.crud.get_job') as mock_get_job, \
             patch('app.api.v1.routes.dataset_explorer.get_storage') as mock_get_storage, \
             patch('app.api.v1.routes.dataset_explorer.get_upload_service') as mock_get_service:
            
            mock_job = Mock()
            mock_job.id = sample_job_id
            mock_job.user_id = "test-user-1"
            mock_get_job.return_value = mock_job
            
            mock_storage = Mock()
            mock_storage.exists.return_value = True
            mock_storage.get_job_path.return_value = sample_dataset_dir
            mock_get_storage.return_value = mock_storage
            
            mock_service = Mock()
            mock_service.upload_dataset.return_value = {
                "success": False,
                "error": "Authentication failed",
                "message": "Upload failed"
            }
            mock_get_service.return_value = mock_service
            
            response = client.post(
                f"/api/v1/datasets/{sample_job_id}/upload-to-aem",
                json=upload_request_data,
                headers=auth_headers
            )
            
            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()
    
    def test_upload_endpoint_missing_fields(
        self,
        client: TestClient,
        auth_headers: dict,
        sample_job_id: str
    ):
        """Test upload with missing required fields."""
        incomplete_data = {
            "aem_base_url": "https://author-test.adobeaemcloud.com",
            "target_path": "content/dam/test/"
        }
        
        response = client.post(
            f"/api/v1/datasets/{sample_job_id}/upload-to-aem",
            json=incomplete_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422
    
    def test_upload_endpoint_service_not_available(
        self,
        client: TestClient,
        auth_headers: dict,
        sample_job_id: str,
        sample_dataset_dir: Path,
        upload_request_data: dict
    ):
        """Test when upload service is not available."""
        with patch('app.api.v1.routes.dataset_explorer.crud.get_job') as mock_get_job, \
             patch('app.api.v1.routes.dataset_explorer.get_storage') as mock_get_storage, \
             patch('app.api.v1.routes.dataset_explorer.get_upload_service') as mock_get_service:
            
            mock_job = Mock()
            mock_job.id = sample_job_id
            mock_job.user_id = "test-user-1"
            mock_get_job.return_value = mock_job
            
            mock_storage = Mock()
            mock_storage.exists.return_value = True
            mock_storage.get_job_path.return_value = sample_dataset_dir
            mock_get_storage.return_value = mock_storage
            
            mock_get_service.side_effect = FileNotFoundError("Upload script not found")
            
            response = client.post(
                f"/api/v1/datasets/{sample_job_id}/upload-to-aem",
                json=upload_request_data,
                headers=auth_headers
            )
            
            assert response.status_code == 500
            assert "not available" in response.json()["detail"].lower() or "not found" in response.json()["detail"].lower()


class TestAemUploadRequestValidation:
    """Test request validation for AEM upload."""
    
    def test_upload_request_valid_data(self, upload_request_data):
        """Test valid upload request data."""
        from app.api.v1.routes.dataset_explorer import AemUploadRequest
        
        request = AemUploadRequest(**upload_request_data)
        assert request.aem_base_url == upload_request_data["aem_base_url"]
        assert request.target_path == upload_request_data["target_path"]
        assert request.username == upload_request_data["username"]
        assert request.password == upload_request_data["password"]
        assert request.max_concurrent == upload_request_data["max_concurrent"]
        assert request.max_upload_files == upload_request_data["max_upload_files"]
    
    def test_upload_request_defaults(self):
        """Test upload request with default values."""
        from app.api.v1.routes.dataset_explorer import AemUploadRequest
        
        minimal_data = {
            "aem_base_url": "https://author-test.adobeaemcloud.com",
            "target_path": "content/dam/test/",
            "username": "testadmin",
            "password": "testadmin"
        }
        
        request = AemUploadRequest(**minimal_data)
        assert request.max_concurrent == 20
        assert request.max_upload_files == 70000
    
    def test_upload_request_validation_errors(self):
        """Test upload request validation."""
        from app.api.v1.routes.dataset_explorer import AemUploadRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            AemUploadRequest(
                aem_base_url="https://test.com",
                target_path="content/dam/test/",
                username="testadmin",
                password="testadmin",
                max_concurrent=0
            )
        
        with pytest.raises(ValidationError):
            AemUploadRequest(
                aem_base_url="https://test.com",
                target_path="content/dam/test/",
                username="testadmin",
                password="testadmin",
                max_concurrent=101
            )
