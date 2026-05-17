from __future__ import annotations
import argparse
import json
import mimetypes
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DEFAULT_MIME_TYPE = "text/markdown"


def get_oauth_credentials(
    client_secrets_path: Path, token_path: Optional[Path] = None
) -> oauth_credentials.Credentials:
    token_path = token_path or Path("token.json")
    creds: Optional[oauth_credentials.Credentials] = None

    if token_path.exists():
        creds = oauth_credentials.Credentials.from_authorized_user_file(
            str(token_path), scopes=SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_path), scopes=SCOPES
            )
            creds = flow.run_local_server(port=0)

        with token_path.open("w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds


def get_credentials(
    credential_path: Optional[Path] = None,
    oauth_client_secrets: Optional[Path] = None,
    token_path: Optional[Path] = None,
):
    if oauth_client_secrets is not None:
        if not oauth_client_secrets.exists() or not oauth_client_secrets.is_file():
            raise FileNotFoundError(
                f"OAuth client secrets file not found or invalid: {oauth_client_secrets}"
            )
        return get_oauth_credentials(oauth_client_secrets, token_path)

    if credential_path is None:
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not env_path:
            raise FileNotFoundError(
                "Google credential file not found. Set GOOGLE_APPLICATION_CREDENTIALS or pass --credentials."
            )
        credential_path = Path(env_path)

    if not credential_path.exists() or not credential_path.is_file():
        raise FileNotFoundError(
            f"Google credential file not found or invalid: {credential_path}"
        )
    return service_account.Credentials.from_service_account_file(
        str(credential_path), scopes=SCOPES
    )


def get_drive_service(credentials) -> object:
    return build("drive", "v3", credentials=credentials)


def _escape_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_child_folder(service, parent_id: str, name: str) -> Optional[dict]:
    safe_name = _escape_query_value(name)
    safe_parent = _escape_query_value(parent_id)
    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{safe_name}' "
        f"and '{safe_parent}' in parents "
        "and trashed = false"
    )
    response = service.files().list(
        q=query,
        fields="files(id,name,webViewLink,parents)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = response.get("files", [])
    return files[0] if files else None


def create_child_folder(service, parent_id: str, name: str) -> dict:
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    return service.files().create(
        body=metadata,
        fields="id,name,webViewLink,parents",
        supportsAllDrives=True,
    ).execute()


def ensure_drive_folder_path(
    root_folder_id: str,
    folder_names: list[str],
    credential_path: Optional[str] = None,
    oauth_client_secrets: Optional[str] = None,
    token_path: Optional[str] = None,
) -> dict:
    credentials = get_credentials(
        Path(credential_path) if credential_path else None,
        Path(oauth_client_secrets) if oauth_client_secrets else None,
        Path(token_path) if token_path else None,
    )
    service = get_drive_service(credentials)
    parent_id = root_folder_id
    folders = []
    for name in folder_names:
        folder = find_child_folder(service, parent_id, name)
        if folder is None:
            folder = create_child_folder(service, parent_id, name)
        folders.append(folder)
        parent_id = folder["id"]
    return {"folder_id": parent_id, "folders": folders}


def upload_file_to_drive(
    source_path: str,
    folder_id: Optional[str] = None,
    dest_name: Optional[str] = None,
    mime_type: Optional[str] = None,
    credential_path: Optional[str] = None,
    oauth_client_secrets: Optional[str] = None,
    token_path: Optional[str] = None,
) -> dict:
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    if mime_type is None:
        mime_type = mimetypes.guess_type(path.name)[0] or DEFAULT_MIME_TYPE

    credentials = get_credentials(
        Path(credential_path) if credential_path else None,
        Path(oauth_client_secrets) if oauth_client_secrets else None,
        Path(token_path) if token_path else None,
    )
    service = get_drive_service(credentials)

    file_metadata: dict[str, object] = {"name": dest_name or path.name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
    request = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id,name,webViewLink,webContentLink,parents",
        supportsAllDrives=True,
    )
    created_file = request.execute()
    return created_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a file to Google Drive using a service account.")
    parser.add_argument("source", help="Path to the local file to upload.")
    parser.add_argument("--folder-id", help="Drive folder ID to upload into.")
    parser.add_argument("--name", help="Destination file name in Drive.")
    parser.add_argument(
        "--credentials",
        help="Path to service account JSON file. If omitted, uses GOOGLE_APPLICATION_CREDENTIALS.",
    )
    parser.add_argument(
        "--mime-type",
        help="Optional MIME type for the upload. Defaults to detected type or text/markdown.",
    )
    parser.add_argument(
        "--oauth-client-secrets",
        help="Path to OAuth client secrets JSON file for personal account login.",
    )
    parser.add_argument(
        "--token-file",
        help="Path to store OAuth token cache. Defaults to token.json.",
    )
    args = parser.parse_args()

    result = upload_file_to_drive(
        source_path=args.source,
        folder_id=args.folder_id,
        dest_name=args.name,
        mime_type=args.mime_type,
        credential_path=args.credentials,
        oauth_client_secrets=args.oauth_client_secrets,
        token_path=args.token_file,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
