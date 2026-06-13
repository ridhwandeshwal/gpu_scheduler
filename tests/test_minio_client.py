import pytest
from unittest.mock import patch, MagicMock
from app.services.minio_client import _client, _public_client, presign_download
from app.config import get_settings

@pytest.fixture
def mock_settings():
    settings = get_settings()
    original_public = settings.minio_public_endpoint
    original_endpoint = settings.minio_endpoint
    settings.minio_endpoint = "http://minio:9000"
    settings.minio_public_endpoint = None
    yield settings
    settings.minio_endpoint = original_endpoint
    settings.minio_public_endpoint = original_public

@patch("app.services.minio_client.Minio")
def test_public_client_fallback(mock_minio_cls, mock_settings):
    """Test that _public_client falls back to internal endpoint if public is not set."""
    _public_client()
    mock_minio_cls.assert_called_with(
        "minio:9000",
        access_key=mock_settings.minio_access_key,
        secret_key=mock_settings.minio_secret_key,
        secure=False,
    )

@patch("app.services.minio_client.Minio")
def test_public_client_with_https_endpoint(mock_minio_cls, mock_settings):
    """Test that _public_client uses public endpoint when set."""
    mock_settings.minio_public_endpoint = "https://minio.quda.aimsdtu.in"
    _public_client()
    mock_minio_cls.assert_called_with(
        "minio.quda.aimsdtu.in",
        access_key=mock_settings.minio_access_key,
        secret_key=mock_settings.minio_secret_key,
        secure=True,
    )

@patch("app.services.minio_client._public_client")
def test_presign_download_uses_public_client(mock_get_client):
    """Test that presign_download calls the public client."""
    mock_instance = MagicMock()
    mock_get_client.return_value = mock_instance
    mock_instance.presigned_get_object.return_value = "https://example.com/test.txt"
    
    url = presign_download("test.txt", expires_in=100)
    
    assert url == "https://example.com/test.txt"
    mock_instance.presigned_get_object.assert_called_once()
