"""Focused preparation tests; exercise contents are always synthetic."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from bench.prepare import main, prepare_workspace


@pytest.fixture
def exercise(tmp_path):
    source = tmp_path / "exercise"
    source.mkdir()
    (source / "solution.py").write_text("def answer(): return 42\n", encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests" / "test_answer.py").write_text(
        "raise RuntimeError('exercise code must never execute')\n", encoding="utf-8"
    )
    (source / "empty").mkdir()
    for relative in (".meta", "tests/.meta", ".meta/nested/.meta"):
        directory = source / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "answer.txt").write_text("hidden solution", encoding="utf-8")
    return source


def snapshot(root):
    return {
        str(path.relative_to(root)): None if path.is_dir() else path.read_bytes()
        for path in root.rglob("*")
    }


def test_copies_files_and_tests_without_metadata_or_source_changes(exercise, tmp_path):
    before = snapshot(exercise)
    destination = tmp_path / "prepared"

    assert prepare_workspace(exercise, destination) == destination.resolve()

    expected = {
        name: contents
        for name, contents in before.items()
        if ".meta" not in Path(name).parts
    }
    assert snapshot(destination) == expected
    assert snapshot(exercise) == before


def test_does_not_execute_exercise_code(exercise, tmp_path):
    canary = tmp_path / "executed.txt"
    payload = (
        f"from pathlib import Path\nPath({str(canary)!r}).write_text('executed')\n"
        "raise RuntimeError('must not execute')\n"
    )
    for name in ("conftest.py", "__init__.py", "setup.py", "sitecustomize.py"):
        (exercise / name).write_text(payload, encoding="utf-8")

    prepare_workspace(exercise, tmp_path / "prepared")

    assert not canary.exists()


def test_preserves_binary_files_and_regular_file_named_meta(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "fixture.bin").write_bytes(bytes(range(256)))
    (source / ".meta").write_text("ordinary file", encoding="utf-8")

    destination = prepare_workspace(source, tmp_path / "prepared")

    assert snapshot(destination) == snapshot(source)


def test_empty_exercise(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    destination = prepare_workspace(source, tmp_path / "prepared")
    assert destination.is_dir()
    assert list(destination.iterdir()) == []


def test_rejects_metadata_directory_as_source(tmp_path):
    source = tmp_path / ".meta"
    source.mkdir()
    (source / "solution.txt").write_text("hidden solution", encoding="utf-8")

    with pytest.raises(ValueError, match="Source cannot itself be a .meta"):
        prepare_workspace(source, tmp_path / "prepared")

    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_existing_destination_is_untouched(exercise, tmp_path, kind):
    destination = tmp_path / "existing"
    if kind == "directory":
        destination.mkdir()
        sentinel = destination / "keep.txt"
    else:
        sentinel = destination
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        prepare_workspace(exercise, destination)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"


@pytest.mark.parametrize("relationship", ["same", "descendant", "ancestor"])
def test_rejects_overlapping_paths(exercise, relationship):
    destination = {
        "same": exercise,
        "descendant": exercise / "nested" / ".." / "prepared",
        "ancestor": exercise.parent,
    }[relationship]
    before = snapshot(exercise)

    with pytest.raises((ValueError, FileExistsError)):
        prepare_workspace(exercise, destination)

    assert snapshot(exercise) == before
    assert not (exercise / "prepared").exists()


def test_sibling_with_shared_name_prefix_is_allowed(exercise, tmp_path):
    destination = tmp_path / "exercise-copy"
    prepare_workspace(exercise, destination)
    assert (destination / "solution.py").is_file()


def test_relative_paths(exercise, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert prepare_workspace("exercise", "prepared") == tmp_path / "prepared"


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_invalid_source_leaves_no_destination(tmp_path, kind):
    source = tmp_path / "source"
    if kind == "file":
        source.write_text("not a directory", encoding="utf-8")
    destination = tmp_path / "prepared"

    with pytest.raises((FileNotFoundError, NotADirectoryError)):
        prepare_workspace(source, destination)

    assert not destination.exists()


def test_missing_destination_parent_is_not_created(exercise, tmp_path):
    parent = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        prepare_workspace(exercise, parent / "prepared")
    assert not parent.exists()


def make_symlink(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"Symlink creation unavailable: {error}")


@pytest.mark.parametrize("location", ["file", "directory", "dangling", "meta", "root"])
def test_rejects_symlinks(exercise, tmp_path, location):
    source = exercise
    if location == "root":
        source = tmp_path / "source-link"
        make_symlink(source, exercise, directory=True)
    elif location == "directory":
        make_symlink(exercise / "linked-tests", exercise / "tests", directory=True)
    else:
        target = exercise / ("missing" if location == "dangling" else "solution.py")
        link = exercise / (".meta/link" if location == "meta" else "link")
        make_symlink(link, target)
    destination = tmp_path / "prepared"

    with pytest.raises(ValueError, match="Links and junctions"):
        prepare_workspace(source, destination)

    assert not destination.exists()


def test_existing_dangling_destination_link_is_preserved(exercise, tmp_path):
    destination = tmp_path / "destination-link"
    make_symlink(destination, tmp_path / "missing")

    with pytest.raises(FileExistsError):
        prepare_workspace(exercise, destination)

    assert destination.is_symlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions only")
def test_rejects_windows_junction(exercise, tmp_path):
    junction = exercise / "junction"
    # This is a test-created junction to a synthetic directory, never exercise code.
    result = subprocess.run(
        [
            os.environ["COMSPEC"], "/d", "/c", "mklink", "/J",
            str(junction), str(exercise / "tests"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.skip(f"Junction creation unavailable: {result.stdout} {result.stderr}")
    try:
        with pytest.raises(ValueError, match="Links and junctions"):
            prepare_workspace(exercise, tmp_path / "prepared")
        assert not (tmp_path / "prepared").exists()
    finally:
        junction.rmdir()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation unavailable")
def test_rejects_special_files(exercise, tmp_path):
    os.mkfifo(exercise / "pipe")
    with pytest.raises(ValueError, match="ordinary files"):
        prepare_workspace(exercise, tmp_path / "prepared")
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_copy_failure_removes_destination(exercise, tmp_path, monkeypatch, error_type):
    original_copy = shutil.copyfile
    copied_files = []

    def failing_copy(source, destination, **kwargs):
        original_copy(source, destination, **kwargs)
        copied_files.append(destination)
        raise error_type("synthetic copy interruption")

    monkeypatch.setattr("bench.prepare.shutil.copyfile", failing_copy)
    before = snapshot(exercise)
    destination = tmp_path / "prepared"

    with pytest.raises(error_type, match="synthetic copy interruption"):
        prepare_workspace(exercise, destination)

    assert copied_files
    assert not destination.exists()
    assert snapshot(exercise) == before


def test_racing_destination_is_preserved(exercise, tmp_path, monkeypatch):
    destination = tmp_path / "prepared"
    original_mkdir = Path.mkdir

    def racing_mkdir(path, *args, **kwargs):
        if path == destination:
            original_mkdir(path)
            (path / "keep.txt").write_text("other creator", encoding="utf-8")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", racing_mkdir)

    with pytest.raises(FileExistsError):
        prepare_workspace(exercise, destination)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "other creator"


def test_main_reports_success(exercise, tmp_path, capsys):
    destination = tmp_path / "prepared"
    assert main(["--source", str(exercise), "--destination", str(destination)]) == 0
    assert str(destination.resolve()) in capsys.readouterr().out


def test_main_reports_failure(exercise, capsys):
    with pytest.raises(SystemExit) as error:
        main(["--source", str(exercise), "--destination", str(exercise)])
    assert error.value.code == 1
    assert "Destination already exists" in capsys.readouterr().err


def test_module_cli(exercise, tmp_path):
    destination = tmp_path / "cli-prepared"
    result = subprocess.run(
        [
            sys.executable, "-m", "bench.prepare", "--source", str(exercise),
            "--destination", str(destination),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Prepared workspace:" in result.stdout
    assert (destination / "tests" / "test_answer.py").is_file()
    assert not (destination / ".meta").exists()
