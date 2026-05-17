from __future__ import annotations

from types import SimpleNamespace

import google_drive


class _Executable:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Files:
    def __init__(self):
        self.created = False
        self.updated = False

    def list(self, **kwargs):
        return _Executable({
            "files": [
                {
                    "id": "existing-file",
                    "name": "kit.zip",
                    "webViewLink": "https://drive.google.com/file/d/existing-file/view",
                    "parents": ["folder-1"],
                }
            ]
        })

    def update(self, **kwargs):
        self.updated = True
        self.update_kwargs = kwargs
        return _Executable({
            "id": kwargs["fileId"],
            "name": "kit.zip",
            "webViewLink": "https://drive.google.com/file/d/existing-file/view",
            "parents": ["folder-1"],
        })

    def create(self, **kwargs):
        self.created = True
        self.create_kwargs = kwargs
        return _Executable({"id": "created-file", "name": "kit.zip"})


class _Service:
    def __init__(self):
        self.files_api = _Files()

    def files(self):
        return self.files_api


def test_upload_file_to_drive_replaces_existing_file(tmp_path, monkeypatch):
    source = tmp_path / "kit.zip"
    source.write_bytes(b"zip")
    service = _Service()
    monkeypatch.setattr(google_drive, "get_credentials", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(google_drive, "get_drive_service", lambda credentials: service)

    result = google_drive.upload_file_to_drive(
        str(source),
        folder_id="folder-1",
        dest_name="kit.zip",
        mime_type="application/zip",
        replace_existing=True,
    )

    assert result["id"] == "existing-file"
    assert result["syncAction"] == "updated"
    assert service.files_api.updated is True
    assert service.files_api.created is False
