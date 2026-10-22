"""GET /api/v1/extract/progress/{upload_id} and the X-Upload-Id header."""

from fastapi.testclient import TestClient

from app.api import extract
from app.api.deps import require_user
from app.main import create_app
from app.pipeline.progress import Progress, UploadProgress
from app.settings import Settings, get_settings
from tests.unit.api.test_extract import SIGNED_IN, unsaved_records
from tests.unit.api.uploads import Answers, make_pdf, upload

ID = "3f0c2a1e-7b9d-4c55-9a10-2d6e8f4b1c77"


class Watching(Answers):
    """Answers like Answers, and notes the progress the server shows at each call."""

    def __init__(self, progress: UploadProgress) -> None:
        super().__init__()
        self.progress = progress
        self.seen: list[Progress | None] = []

    async def extract(self, page):
        self.seen.append(self.progress.get(ID))
        return await super().extract(page)


def make_client(progress: UploadProgress, provider=None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, max_concurrency=1)
    app.dependency_overrides[extract.get_provider] = lambda: provider or Answers()
    app.dependency_overrides[extract.get_save_form] = lambda: unsaved_records
    app.dependency_overrides[require_user] = lambda: SIGNED_IN
    app.dependency_overrides[extract.get_progress] = lambda: progress
    return TestClient(app)


def test_the_upload_counts_its_pages_while_it_runs():
    progress = UploadProgress()
    provider = Watching(progress)

    response = make_client(progress, provider).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(3))), headers={"X-Upload-Id": ID}
    )

    assert response.status_code == 200
    assert provider.seen == [
        Progress(done=0, total=3),
        Progress(done=1, total=3),
        Progress(done=2, total=3),
    ]
    assert progress.get(ID) is None  # gone once the answer is sent


def test_progress_answers_while_the_upload_runs():
    progress = UploadProgress()
    progress.start(ID)
    progress.update(ID, 8, 26)

    response = make_client(progress).get(f"/api/v1/extract/progress/{ID}")

    assert response.status_code == 200
    assert response.json() == {"done": 8, "total": 26}
    assert response.headers["cache-control"] == "no-store"


def test_progress_is_404_for_an_upload_not_running():
    response = make_client(UploadProgress()).get(f"/api/v1/extract/progress/{ID}")

    assert response.status_code == 404
    assert response.json()["type"] == "upload_not_found"


def test_an_upload_without_the_header_works_as_before_and_is_not_tracked():
    progress = UploadProgress()
    provider = Watching(progress)

    response = make_client(progress, provider).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(1)))
    )

    assert response.status_code == 200
    assert provider.seen == [None]


def test_a_malformed_upload_id_is_ignored_not_refused():
    progress = UploadProgress()

    response = make_client(progress).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(1))), headers={"X-Upload-Id": "x"}
    )

    assert response.status_code == 200
    assert progress.get("x") is None


def test_progress_is_cleared_when_the_upload_is_refused():
    progress = UploadProgress()

    response = make_client(progress).post(
        "/api/v1/extract", content=b"not multipart", headers={"X-Upload-Id": ID}
    )

    assert response.status_code == 415
    assert progress.get(ID) is None


def test_two_uploads_with_the_same_id_track_only_the_first():
    progress = UploadProgress()
    progress.start(ID)  # another upload already running with this id
    progress.update(ID, 4, 9)

    response = make_client(progress).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(1))), headers={"X-Upload-Id": ID}
    )

    assert response.status_code == 200
    assert progress.get(ID) == Progress(done=4, total=9)  # the first one's, untouched
