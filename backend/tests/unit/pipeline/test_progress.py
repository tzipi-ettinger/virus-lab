from app.pipeline.progress import Progress, UploadProgress

ID = "3f0c2a1e-7b9d-4c55-9a10-2d6e8f4b1c77"


def test_an_upload_is_tracked_from_start_to_finish():
    progress = UploadProgress()

    assert progress.start(ID)
    assert progress.get(ID) == Progress(done=0, total=0)
    progress.update(ID, 3, 26)
    assert progress.get(ID) == Progress(done=3, total=26)
    progress.finish(ID)
    assert progress.get(ID) is None


def test_a_malformed_id_is_not_tracked():
    progress = UploadProgress()

    for upload_id in ["short", "x" * 65, "has space-123", "../../etc/passwd", "שלום-עולם-1"]:
        assert not progress.start(upload_id)
        assert progress.get(upload_id) is None


def test_an_id_already_running_is_not_taken_over():
    progress = UploadProgress()
    progress.start(ID)
    progress.update(ID, 5, 10)

    assert not progress.start(ID)
    assert progress.get(ID) == Progress(done=5, total=10)


def test_over_the_limit_new_uploads_go_untracked():
    progress = UploadProgress(max_uploads=2)

    assert progress.start("upload-0001")
    assert progress.start("upload-0002")
    assert not progress.start("upload-0003")
    progress.finish("upload-0001")
    assert progress.start("upload-0003")


def test_update_and_finish_ignore_an_upload_not_tracked():
    progress = UploadProgress()

    progress.update(ID, 1, 2)
    progress.finish(ID)

    assert progress.get(ID) is None
