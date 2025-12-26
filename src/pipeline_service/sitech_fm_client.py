"""SI-TECH Intelligent Knowledge Center universal upload/download client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin

from requests import Response, Session
from requests.exceptions import RequestException

from .config import get_settings


class FileManagementError(RuntimeError):
    """Raised when SI-TECH file management server operations fail."""


@dataclass(frozen=True)
class FileUploadResult:
    code: str
    msg: str | None
    fileid: str | None
    fileSize: str | None
    fileType: str | None
    prefix: str | None
    realname: str | None
    sysname: str | None
    filepah: str | None
    filepah2: str | None
    ico: str | None
    flage: str | None
    isEncrypted: str | None
    filePreviewUrl: str | None
    fileDownloadUrl: str | None
    raw: Mapping[str, Any]

    @property
    def succeeded(self) -> bool:
        return str(self.code) in {"success", "0", "200"}

    def to_dict(self) -> Mapping[str, Any]:
        return dict(self.raw)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "FileUploadResult":
        return cls(
            code=str(payload.get("code")),
            msg=payload.get("msg"),
            fileid=payload.get("fileid"),
            fileSize=payload.get("fileSize"),
            fileType=payload.get("fileType"),
            prefix=payload.get("prefix"),
            realname=payload.get("realname"),
            sysname=payload.get("sysname"),
            filepah=payload.get("filepah"),
            filepah2=payload.get("filepah2"),
            ico=payload.get("ico"),
            flage=payload.get("flage"),
            isEncrypted=payload.get("isEncrypted"),
            filePreviewUrl=payload.get("filePreviewUrl"),
            fileDownloadUrl=payload.get("fileDownloadUrl"),
            raw=payload,
        )


@dataclass(frozen=True)
class SitechFmConfig:
    base_url: str
    download_path: str
    upload_path: str
    attach_id_param: str
    file_field_name: str
    default_form_fields: Mapping[str, Any]
    timeout: float
    verify: bool
    headers: Mapping[str, str]

    def build_url(self, path: str) -> str:
        """Compose absolute endpoint URL from base and relative path."""
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))


class SitechFmClient:
    """Lightweight wrapper for SI-TECH knowledge center file management APIs."""

    def __init__(self, config: SitechFmConfig):
        self._config = config
        self._session = Session()
        self._session.headers.update(config.headers)
        self._session.headers.setdefault("Accept", "application/json")

    def download(
        self, attach_id: str, destination: str | Path, extra_params: Mapping[str, Any] | None = None
    ) -> Path:
        params = {self._config.attach_id_param: attach_id}
        if extra_params:
            params.update(extra_params)

        url = self._config.build_url(self._config.download_path)

        try:
            response = self._session.get(
                url, params=params, timeout=self._config.timeout, stream=True, verify=self._config.verify
            )
            self._ensure_success(response, "download")

            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with dest_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            return dest_path
        except RequestException as exc:  # noqa: BLE001
            raise FileManagementError(f"download request failed: {exc}") from exc

    def upload(
        self,
        file_path: str | Path,
        filename: str | None = None,
        extra_params: Mapping[str, Any] | None = None,
        form_fields: Mapping[str, Any] | None = None,
    ) -> FileUploadResult:
        path = Path(file_path)
        params = dict(extra_params or {})
        data = dict(self._config.default_form_fields or {})
        data.update(form_fields or {})
        upload_name = filename or path.name

        url = self._config.build_url(self._config.upload_path)

        try:
            print(
                "[sitech_fm_client] upload request",
                {
                    "url": url,
                    "params": params,
                    "form_fields": data,
                    "file_field": self._config.file_field_name,
                    "filename": upload_name,
                },
            )
            with path.open("rb") as fh:
                files = {self._config.file_field_name: (upload_name, fh)}
                response = self._session.post(
                    url,
                    params=params,
                    data=data,
                    files=files,
                    timeout=self._config.timeout,
                    verify=self._config.verify,
                )
            self._ensure_success(response, "upload")
        except RequestException as exc:  # noqa: BLE001
            print(f"[sitech_fm_client] upload request failed: {exc}")
            raise FileManagementError(f"upload request failed: {exc}") from exc

        body_text = response.text
        try:
            payload = response.json()
        except ValueError:
            payload = self._parse_json_loose(body_text, response.status_code)

        # Debug trace: print full response for troubleshooting non-standard payloads.
        print(f"[sitech_fm_client] upload response status={response.status_code}, body={body_text}")

        code = str(payload.get("code")) if payload.get("code") is not None else None
        if code not in {"success", "0", "200"}:
            raise FileManagementError(f"upload failed with code={code}: {payload}")

        return FileUploadResult.from_payload(payload)

    def upload_files(
        self,
        files: Sequence[str | Path],
        extra_params: Mapping[str, Any] | None = None,
        form_fields: Mapping[str, Any] | None = None,
    ) -> list[FileUploadResult]:
        """Upload multiple files sequentially and return individual responses."""

        results: list[FileUploadResult] = []
        for file_path in files:
            results.append(
                self.upload(
                    file_path=file_path,
                    filename=Path(file_path).name,
                    extra_params=extra_params,
                    form_fields=form_fields,
                )
            )
        return results

    def upload_directory(
        self,
        directory: str | Path,
        pattern: str = "**/*",
        extra_params: Mapping[str, Any] | None = None,
        form_fields: Mapping[str, Any] | None = None,
    ) -> list[FileUploadResult]:
        """Upload all files in a directory matching the glob pattern."""

        base = Path(directory)
        if not base.exists():
            raise FileManagementError(f"directory not found: {base}")

        paths = [p for p in base.glob(pattern) if p.is_file()]
        if not paths:
            raise FileManagementError(f"no files matched pattern '{pattern}' in {base}")

        return self.upload_files(paths, extra_params=extra_params, form_fields=form_fields)

    def _ensure_success(self, response: Response, action: str) -> None:
        if response.status_code >= 400:
            raise FileManagementError(f"{action} failed ({response.status_code}): {response.text}")

    def _parse_json_loose(self, body_text: str, status_code: int) -> dict[str, Any]:
        """Parse JSON even if the response is text/html or wrapped in extra characters."""

        trimmed = (body_text or "").strip()
        # Fast path: direct parse
        try:
            return json.loads(trimmed)
        except Exception:
            pass

        # Fallback: find first '{' and last '}' and try that slice
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start != -1 and end > start:
            snippet_body = trimmed[start : end + 1]
            try:
                return json.loads(snippet_body)
            except Exception as exc:  # noqa: BLE001
                snippet = trimmed[:200].replace("\n", " ")
                raise FileManagementError(
                    f"upload response is not valid JSON (status={status_code}, body~{snippet})"
                ) from exc

        snippet = trimmed[:200].replace("\n", " ")
        raise FileManagementError(
            f"upload response is not valid JSON (status={status_code}, body~{snippet})"
        )


@lru_cache
def get_sitech_fm_client() -> SitechFmClient:
    """Return a cached SI-TECH file management client configured from settings."""

    settings = get_settings()
    headers = dict(settings.file_manager_extra_headers or {})

    if settings.file_manager_auth_token:
        token = f"{settings.file_manager_token_prefix}{settings.file_manager_auth_token}"
        headers.setdefault(settings.file_manager_auth_header, token)

    config = SitechFmConfig(
        base_url=str(settings.file_manager_base_url),
        download_path=settings.file_manager_download_path,
        upload_path=settings.file_manager_upload_path,
        attach_id_param=settings.file_manager_attach_id_param,
        file_field_name=settings.file_manager_file_field,
        default_form_fields=settings.file_manager_default_form_fields,
        timeout=settings.file_manager_timeout_sec,
        verify=settings.file_manager_verify_tls,
        headers=headers,
    )

    return SitechFmClient(config)


# Backward compatibility exports
FileManagerConfig = SitechFmConfig
FileManagerClient = SitechFmClient
get_file_manager_client = get_sitech_fm_client
