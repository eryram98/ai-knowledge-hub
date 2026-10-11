"""
Upload intake service for admin-triggered ingestion requests.
Python 3.6 compatible.

This module intentionally avoids framework-specific request/response types.
A future API endpoint can call this service from Flask/FastAPI/Django/etc.
"""

import os
import uuid

from ingestion.ingestion_config_manager import IngestionConfig
from ingestion.ingestion_error_model import (
    ERROR_BATCH_LIMIT_EXCEEDED,
    ERROR_FILE_TOO_LARGE,
    ERROR_INTERNAL_FAILURE,
    ERROR_UNREADABLE_FILE,
    ERROR_UNSUPPORTED_FORMAT,
    ERROR_VALIDATION_FAILED,
    build_ingestion_error,
)
from ingestion.ingestion_metadata_contract import (
    INGESTION_SOURCE_UI,
    create_metadata_record,
)
from ingestion.ingestion_status_constants import INGESTION_STATUS_QUEUED


class UploadFileInput(object):
    """
    Minimal file input contract for ingestion upload intake.

    Expected fields:
      - original_filename: original client-side filename
      - file_size_bytes: size of file in bytes
      - upload_timestamp: UTC timestamp string, format YYYY-MM-DDTHH:MM:SSZ
      - temp_file_path: path to temporarily stored uploaded file, if available
      - source: ingestion source, defaults to UI
    """

    def __init__(
        self,
        original_filename,
        file_size_bytes,
        upload_timestamp,
        temp_file_path=None,
        source=INGESTION_SOURCE_UI,
    ):
        # type: (str, int, str, str, str) -> None
        self.original_filename = original_filename
        self.file_size_bytes = file_size_bytes
        self.upload_timestamp = upload_timestamp
        self.temp_file_path = temp_file_path
        self.source = source


class IngestionUploadService(object):
    """
    Handles initial upload intake for ingestion.

    This service does not yet perform full validation, persistence, or queueing.
    Those are covered by later subtasks:
      - 3.x async queue/status lifecycle
    """

    def __init__(self, config=None):
        # type: (IngestionConfig) -> None
        self.config = config or IngestionConfig()

    def create_upload_request(self, files):
        # type: (list) -> dict
        """
        Create an upload intake request for one or more files.

        Returns:
        {
            "upload_request_id": str,
            "status": "received"|"partial"|"failed",
            "files": [
                {
                    "status": "accepted"|"rejected",
                    "document_id": str|None,
                    "ingestion_status": "queued"|None,
                    "metadata": dict|None,
                    "temp_file_path": str|None,
                    "error": dict|None
                }
            ],
            "errors": []
        }
        """
        upload_request_id = self._new_id("upload")
        response = {
            "upload_request_id": upload_request_id,
            "status": "received",
            "files": [],
            "errors": [],
        }

        if files is None:
            response["status"] = "failed"
            response["errors"].append(
                build_ingestion_error(
                    ERROR_VALIDATION_FAILED,
                    details="files must be provided",
                    field="files",
                )
            )
            return response

        if not isinstance(files, list):
            response["status"] = "failed"
            response["errors"].append(
                build_ingestion_error(
                    ERROR_VALIDATION_FAILED,
                    details="files must be a list",
                    field="files",
                )
            )
            return response

        batch_error = self._validate_batch_size(files)
        if batch_error is not None:
            response["status"] = "failed"
            response["errors"].append(batch_error)
            return response

        for file_input in files:
            validation_error = self._validate_file_type(file_input)
            if validation_error is not None:
                response["files"].append(self._create_rejected_file_entry(file_input, validation_error))
                response["errors"].append(validation_error)
                continue

            validation_error = self._validate_file_size(file_input)
            if validation_error is not None:
                response["files"].append(self._create_rejected_file_entry(file_input, validation_error))
                response["errors"].append(validation_error)
                continue

            validation_error = self._validate_readability(file_input)
            if validation_error is not None:
                response["files"].append(self._create_rejected_file_entry(file_input, validation_error))
                response["errors"].append(validation_error)
                continue

            try:
                response["files"].append(self._create_accepted_file_entry(file_input))
            except Exception as exc:
                error = build_ingestion_error(
                    ERROR_INTERNAL_FAILURE,
                    details=str(exc),
                )
                response["files"].append(self._create_rejected_file_entry(file_input, error))
                response["errors"].append(error)

        response["status"] = self._resolve_upload_status(response["files"])
        return response

    def _resolve_upload_status(self, file_results):
        # type: (list) -> str
        if not file_results:
            return "failed"

        accepted_count = 0
        rejected_count = 0

        for file_result in file_results:
            if file_result.get("status") == "accepted":
                accepted_count += 1
            elif file_result.get("status") == "rejected":
                rejected_count += 1

        if accepted_count > 0 and rejected_count > 0:
            return "partial"
        if accepted_count > 0:
            return "received"
        return "failed"

    def _validate_batch_size(self, files):
        # type: (list) -> dict
        if len(files) > self.config.max_files_per_batch:
            return build_ingestion_error(
                ERROR_BATCH_LIMIT_EXCEEDED,
                details="Batch contains {0} files. Maximum allowed is {1}.".format(
                    len(files),
                    self.config.max_files_per_batch,
                ),
                field="files",
            )
        return None

    def _validate_file_type(self, file_input):
        # type: (UploadFileInput) -> dict
        file_name = getattr(file_input, "original_filename", None)
        extension = self._get_extension(file_name)

        if extension not in self.config.allowed_extensions:
            return build_ingestion_error(
                ERROR_UNSUPPORTED_FORMAT,
                details="File extension '{0}' is not allowed. Allowed extensions: {1}".format(
                    extension or "<none>",
                    ", ".join(self.config.allowed_extensions),
                    ),
                file_name=file_name,
                field="original_filename",
            )

        return None

    def _validate_file_size(self, file_input):
        # type: (UploadFileInput) -> dict
        file_name = getattr(file_input, "original_filename", None)
        file_size_bytes = getattr(file_input, "file_size_bytes", None)

        if not isinstance(file_size_bytes, int) or file_size_bytes < 0:
            return build_ingestion_error(
                ERROR_VALIDATION_FAILED,
                details="file_size_bytes must be a non-negative integer",
                file_name=file_name,
                field="file_size_bytes",
            )

        if file_size_bytes > self.config.max_file_size_bytes:
            return build_ingestion_error(
                ERROR_FILE_TOO_LARGE,
                details="File size is {0} bytes. Maximum allowed is {1} bytes.".format(
                    file_size_bytes,
                    self.config.max_file_size_bytes,
                ),
                file_name=file_name,
                field="file_size_bytes",
            )

        return None

    def _validate_readability(self, file_input):
        # type: (UploadFileInput) -> dict
        file_name = getattr(file_input, "original_filename", None)
        temp_file_path = getattr(file_input, "temp_file_path", None)

        # Some callers may not have stored the file yet. Deeper checks can happen
        # once a framework-specific upload handler exists.
        if not temp_file_path:
            return None

        if not os.path.exists(temp_file_path):
            return build_ingestion_error(
                ERROR_UNREADABLE_FILE,
                details="Temporary uploaded file does not exist.",
                file_name=file_name,
                field="temp_file_path",
            )

        if not os.path.isfile(temp_file_path):
            return build_ingestion_error(
                ERROR_UNREADABLE_FILE,
                details="Temporary uploaded path is not a file.",
                file_name=file_name,
                field="temp_file_path",
            )

        if not os.access(temp_file_path, os.R_OK):
            return build_ingestion_error(
                ERROR_UNREADABLE_FILE,
                details="Temporary uploaded file is not readable.",
                file_name=file_name,
                field="temp_file_path",
            )

        try:
            with open(temp_file_path, "rb") as uploaded_file:
                uploaded_file.read(1)
        except IOError as exc:
            return build_ingestion_error(
                ERROR_UNREADABLE_FILE,
                details="Temporary uploaded file could not be opened: {0}".format(str(exc)),
                file_name=file_name,
                field="temp_file_path",
            )

        return None

    def _create_accepted_file_entry(self, file_input):
        # type: (UploadFileInput) -> dict
        document_id = self._new_id("doc")
        file_type = self._get_extension(file_input.original_filename)

        metadata = create_metadata_record(
            original_filename=file_input.original_filename,
            file_type=file_type,
            file_size_bytes=file_input.file_size_bytes,
            upload_timestamp=file_input.upload_timestamp,
            ingestion_source=file_input.source,
            document_id=document_id,
        )

        return {
            "status": "accepted",
            "document_id": document_id,
            "ingestion_status": INGESTION_STATUS_QUEUED,
            "metadata": metadata,
            "temp_file_path": file_input.temp_file_path,
            "error": None,
        }

    def _create_rejected_file_entry(self, file_input, error):
        # type: (UploadFileInput, dict) -> dict
        file_name = getattr(file_input, "original_filename", None)
        temp_file_path = getattr(file_input, "temp_file_path", None)

        return {
            "status": "rejected",
            "document_id": None,
            "ingestion_status": None,
            "metadata": {
                "original_filename": file_name,
                "file_type": self._get_extension(file_name),
            },
            "temp_file_path": temp_file_path,
            "error": error,
        }

    def _get_extension(self, filename):
        # type: (str) -> str
        if not filename:
            return ""
        return os.path.splitext(filename)[1].lower()

    def _new_id(self, prefix):
        # type: (str) -> str
        return "{0}-{1}".format(prefix, uuid.uuid4().hex)
