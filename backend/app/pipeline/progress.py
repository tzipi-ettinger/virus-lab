"""How far each upload has got, for "8 of 26 pages read" on the upload screen.

The page names its upload (X-Upload-Id) and asks GET /extract/progress/{id}
while it waits for the answer. Kept in this server process's memory only, like
the quota state: a restart forgets it, and the page then just stops showing
the count. Only numbers, never a file name or a value (SPEC 11.1).

Owner: A
"""

import re
from dataclasses import dataclass

# What the page sends (crypto.randomUUID()); anything else is not tracked.
UPLOAD_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
# Uploads tracked at once. Each is removed when its request ends, so this is
# reached only by someone sending many ids on purpose: those go untracked.
MAX_UPLOADS = 100


@dataclass(frozen=True)
class Progress:
    done: int  # pages read, failed ones included
    total: int  # 0 until the files are split into pages


class UploadProgress:
    def __init__(self, max_uploads: int = MAX_UPLOADS) -> None:
        self._max_uploads = max_uploads
        self._uploads: dict[str, Progress] = {}

    def start(self, upload_id: str) -> bool:
        """Track this upload. False, and not tracked, for an id that is malformed,
        already in use, or over the limit."""
        if (
            not UPLOAD_ID.fullmatch(upload_id)
            or upload_id in self._uploads
            or len(self._uploads) >= self._max_uploads
        ):
            return False
        self._uploads[upload_id] = Progress(done=0, total=0)
        return True

    def update(self, upload_id: str, done: int, total: int) -> None:
        if upload_id in self._uploads:
            self._uploads[upload_id] = Progress(done=done, total=total)

    def get(self, upload_id: str) -> Progress | None:
        return self._uploads.get(upload_id)

    def finish(self, upload_id: str) -> None:
        self._uploads.pop(upload_id, None)
