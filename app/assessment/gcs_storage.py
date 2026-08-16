import json
import os
from datetime import datetime, timezone
from typing import Iterable

from fastapi import HTTPException
from google.api_core.exceptions import GoogleAPIError, NotFound
from google.cloud import storage

from app.config import get_settings

settings = get_settings()


class AssessmentGCSStorage:
    def __init__(self):
        if not settings.google_cloud_storage_bucket:
            raise HTTPException(
                status_code=500,
                detail="GOOGLE_CLOUD_STORAGE_BUCKET is not configured",
            )
        if settings.google_application_credentials:
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials)
        self.client = storage.Client()
        self.bucket = self.client.bucket(settings.google_cloud_storage_bucket)
        self.prefix = settings.assessment_storage_prefix.strip("/")

    def create(self, payload: dict) -> dict:
        next_id = self._next_id()
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": next_id,
            **payload,
            "created_at": now,
        }
        try:
            self._blob(next_id).upload_from_string(
                json.dumps(record, default=str),
                content_type="application/json",
            )
        except GoogleAPIError as exc:
            raise HTTPException(status_code=502, detail=f"GCS upload failed: {exc}") from exc
        return record

    def list(self) -> list[dict]:
        records: list[dict] = []
        for blob in self._blobs():
            if not blob.name.endswith(".json"):
                continue
            records.append(self._load_blob(blob))
        return records

    def get(self, assessment_id: int) -> dict | None:
        blob = self._blob(assessment_id)
        try:
            return self._load_blob(blob)
        except NotFound:
            return None

    def delete(self, assessment_id: int) -> bool:
        blob = self._blob(assessment_id)
        try:
            blob.delete()
            return True
        except NotFound:
            return False
        except GoogleAPIError as exc:
            raise HTTPException(status_code=502, detail=f"GCS delete failed: {exc}") from exc

    def _next_id(self) -> int:
        ids = [self._id_from_name(blob.name) for blob in self._blobs()]
        return max((value for value in ids if value is not None), default=0) + 1

    def _blobs(self) -> Iterable[storage.Blob]:
        try:
            return list(self.client.list_blobs(self.bucket, prefix=f"{self.prefix}/"))
        except GoogleAPIError as exc:
            raise HTTPException(status_code=502, detail=f"GCS list failed: {exc}") from exc

    def _blob(self, assessment_id: int) -> storage.Blob:
        return self.bucket.blob(f"{self.prefix}/{assessment_id}.json")

    def _load_blob(self, blob: storage.Blob) -> dict:
        try:
            return json.loads(blob.download_as_text())
        except NotFound:
            raise
        except (GoogleAPIError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"GCS read failed for {blob.name}: {exc}") from exc

    def _id_from_name(self, name: str) -> int | None:
        stem = name.rsplit("/", 1)[-1].removesuffix(".json")
        try:
            return int(stem)
        except ValueError:
            return None


def get_assessment_storage() -> AssessmentGCSStorage:
    return AssessmentGCSStorage()
