"""scripts/export_openapi: writes the contract, and --check fails when it is stale (CI)."""

import json

import pytest

from scripts import export_openapi


@pytest.fixture
def contract(tmp_path, monkeypatch):
    path = tmp_path / "openapi.json"
    monkeypatch.setattr(export_openapi, "OPENAPI_PATH", path)
    return path


def test_writes_the_contract_from_the_app(contract, capsys):
    assert export_openapi.main([]) == 0

    written = json.loads(contract.read_text(encoding="utf-8"))
    assert "/api/v1/records" in written["paths"]
    assert "Wrote openapi.json" in capsys.readouterr().out


def test_check_passes_when_the_file_matches(contract):
    export_openapi.main([])

    assert export_openapi.main(["--check"]) == 0


def test_check_ignores_windows_line_endings(contract):
    contract.write_bytes(export_openapi.render().replace("\n", "\r\n").encode("utf-8"))

    assert export_openapi.main(["--check"]) == 0


def test_check_fails_when_the_file_is_stale(contract, capsys):
    contract.write_text("{}\n", encoding="utf-8")

    assert export_openapi.main(["--check"]) == 1
    assert "stale" in capsys.readouterr().out


def test_check_fails_when_the_file_is_missing(contract):
    assert export_openapi.main(["--check"]) == 1
    assert not contract.exists()  # --check never writes
