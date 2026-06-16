"""Tests for the local filesystem audio storage."""

from __future__ import annotations

from pathlib import Path

from app.storage.local import LocalAudioStorage


def test_save_writes_file_and_builds_public_url(tmp_path: Path) -> None:
    storage = LocalAudioStorage(
        root=str(tmp_path),
        public_base_url="http://example.com",
    )

    result = storage.save("job-1", b"\x00\x01\x02", content_type="audio/mpeg")

    assert result.url == "http://example.com/audio/job-1.mp3"
    assert Path(result.path).read_bytes() == b"\x00\x01\x02"


def test_save_picks_extension_for_known_content_types(tmp_path: Path) -> None:
    storage = LocalAudioStorage(root=str(tmp_path), public_base_url="http://x")

    wav = storage.save("a", b"x", content_type="audio/wav")
    unknown = storage.save("b", b"y", content_type="audio/foobar")

    assert wav.path.endswith(".wav")
    assert unknown.path.endswith(".bin")


def test_save_is_overwrite_safe_for_same_job_id(tmp_path: Path) -> None:
    storage = LocalAudioStorage(root=str(tmp_path), public_base_url="http://x")

    storage.save("job-1", b"first")
    storage.save("job-1", b"second")

    files = [p for p in Path(tmp_path).iterdir() if not p.name.startswith(".")]
    assert len(files) == 1
    assert files[0].read_bytes() == b"second"
