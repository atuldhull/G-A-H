"""Independent grading tests using tiny synthetic exercises only."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from bench.grade import CONFIG_NAMES, grade_exercise, main
from bench.prepare import prepare_workspace


def write(root, relative, contents):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


@pytest.fixture
def exercise(tmp_path):
    original = tmp_path / "original-input"
    original.mkdir()
    write(original, "solution.py", "def answer(): return 0\n")
    write(original, "test_solution.py", (
        "from solution import answer\n"
        "def test_answer(expected):\n    assert answer() == expected\n"
    ))
    write(original, "conftest.py", (
        "import pytest\n@pytest.fixture\ndef expected(): return 42\n"
    ))
    write(original, "pytest.ini", "[pytest]\n")
    final = prepare_workspace(original, tmp_path / "agent-final")
    return original, final


def grade(exercise, tmp_path, **kwargs):
    return grade_exercise(
        *exercise, tmp_path / "artifacts", task_id="synthetic-answer", **kwargs
    )


def test_correct_fix_runs_only_in_fresh_copy_and_records_artifacts(exercise, tmp_path):
    original, final = exercise
    write(final, "solution.py", "def answer(): return 42\n")
    write(original, "test_cwd.py", (
        "from pathlib import Path\n"
        "def test_cwd():\n"
        "    Path('execution-cwd.txt').write_text(str(Path.cwd()))\n"
    ))
    # Match the added original oracle in the final tree before measuring edits.
    write(final, "test_cwd.py", (original / "test_cwd.py").read_text(encoding="utf-8"))
    before = snapshot(original), snapshot(final)

    result = grade(exercise, tmp_path)

    assert result["solved"] is True
    assert result["pytest_exit_code"] == 0
    assert result["timeout_seconds"] == 180
    assert result["timed_out"] is False
    assert result["error"] is None
    assert result["test_edit"] is False
    assert result["task_id"] == "synthetic-answer"
    assert result["command"] == [sys.executable, "-m", "pytest", "-q"]
    workspace = Path(result["workspace_path"])
    assert workspace != final and workspace != original
    assert (workspace / "execution-cwd.txt").read_text() == str(workspace)
    assert "2 passed" in Path(result["stdout_path"]).read_text(encoding="utf-8")
    assert Path(result["stderr_path"]).is_file()
    assert json.loads((tmp_path / "artifacts/result.json").read_text()) == result
    assert (snapshot(original), snapshot(final)) == before


def test_failing_solution_is_not_solved(exercise, tmp_path):
    result = grade(exercise, tmp_path)
    assert result["solved"] is False
    assert result["pytest_exit_code"] == 1
    assert result["test_edit"] is False
    assert "FAILED" in Path(result["stdout_path"]).read_text(encoding="utf-8")


def test_changed_and_removed_tests_and_added_hooks_are_recorded(exercise, tmp_path):
    original, final = exercise
    write(original, "tests/removed_test.py", "def test_original(): assert True\n")
    write(final, "test_solution.py", "def test_fake(): assert True\n")
    write(final, "conftest.py", "raise RuntimeError('agent hook must not execute')\n")
    write(final, "tests/test_added.py", "raise RuntimeError('added test must not execute')\n")
    write(final, "pytest.ini", "[pytest]\naddopts = --ignore=test_solution.py\n")
    before = snapshot(original), snapshot(final)

    result = grade(exercise, tmp_path)

    assert result["test_edit"] is True
    assert result["test_changes"] == {
        "added": ["tests/test_added.py"],
        "removed": ["tests/removed_test.py"],
        "changed": ["conftest.py", "pytest.ini", "test_solution.py"],
    }
    assert result["solved"] is False
    assert result["pytest_exit_code"] == 1
    workspace = Path(result["workspace_path"])
    assert not (workspace / "tests/test_added.py").exists()
    for name in ("test_solution.py", "conftest.py", "pytest.ini", "tests/removed_test.py"):
        assert (workspace / name).read_bytes() == (original / name).read_bytes()
    assert (snapshot(original), snapshot(final)) == before


def test_test_edit_flag_is_independent_of_restored_oracle_success(exercise, tmp_path):
    _, final = exercise
    write(final, "solution.py", "def answer(): return 42\n")
    (final / "test_solution.py").unlink()

    result = grade(exercise, tmp_path)

    assert result["solved"] is True
    assert result["test_edit"] is True
    assert result["test_changes"]["removed"] == ["test_solution.py"]


def test_all_config_formats_are_restored_as_whole_files(exercise, tmp_path):
    original, final = exercise
    write(final, "solution.py", "def answer(): return 42\n")
    for name in CONFIG_NAMES:
        if name == "setup.cfg":
            section = "[tool:pytest]\n"
        elif name == "pyproject.toml":
            section = "[tool.pytest.ini_options]\n"
        else:
            section = "[pytest]\n"
        write(original, name, section)
        write(final, name, "not valid configuration\n")

    result = grade(exercise, tmp_path)

    assert result["solved"] is True
    assert result["test_changes"]["changed"] == sorted(CONFIG_NAMES)
    for name in CONFIG_NAMES:
        assert (Path(result["workspace_path"]) / name).read_bytes() == (
            original / name
        ).read_bytes()


def test_added_config_and_runtime_shadow_modules_are_removed(exercise, tmp_path):
    _, final = exercise
    write(final, "solution.py", "def answer(): return 42\n")
    additions = {
        ".pytest.toml": "not valid TOML\n",
        "pytest.py": "raise RuntimeError('fake pytest')\n",
        "sitecustomize.py": "raise RuntimeError('agent startup')\n",
    }
    for name, contents in additions.items():
        write(final, name, contents)

    result = grade(exercise, tmp_path)

    assert result["solved"] is True
    assert result["test_changes"]["added"] == sorted(additions)
    assert all(not (Path(result["workspace_path"]) / name).exists() for name in additions)


def test_config_name_case_variants_are_protected(exercise, tmp_path):
    original, final = exercise
    (original / "pytest.ini").unlink()
    (final / "pytest.ini").unlink()
    write(final, "PYTEST.INI", "[pytest]\naddopts = --invalid-agent-option\n")
    write(final, "solution.py", "def answer(): return 42\n")

    result = grade(exercise, tmp_path)

    assert result["solved"] is True
    assert result["test_changes"]["added"] == ["PYTEST.INI"]
    assert not (Path(result["workspace_path"]) / "PYTEST.INI").exists()


def test_test_directories_protect_helpers_data_and_file_type_changes(exercise, tmp_path):
    original, final = exercise
    write(original, "tests/data.txt", "original fixture\n")
    write(original, "tests/helper.py", "VALUE = 42\n")
    write(final, "tests/data.txt/added.txt", "agent replacement directory\n")
    write(final, "tests/helper.py", "VALUE = 0\n")
    write(final, "solution.py", "def answer(): return 42\n")
    write(final, "__pycache__/test_solution.cpython-314.pyc", "untrusted bytecode")

    result = grade(exercise, tmp_path)

    assert result["solved"] is True
    assert result["test_changes"] == {
        "added": ["tests/data.txt/added.txt"],
        "removed": ["tests/data.txt"],
        "changed": ["tests/helper.py"],
    }
    workspace = Path(result["workspace_path"])
    assert (workspace / "tests/data.txt").read_text() == "original fixture\n"
    assert not (workspace / "__pycache__").exists()


def test_explicit_nonstandard_test_and_fixture_paths(exercise, tmp_path):
    original, final = exercise
    (original / "test_solution.py").unlink()
    (final / "test_solution.py").unlink()
    write(original, "pytest.ini", "[pytest]\npython_files = check_*.py\n")
    write(final, "pytest.ini", "[pytest]\npython_files = check_*.py\n")
    write(original, "check_answer.py", (
        "from pathlib import Path\nfrom solution import answer\n"
        "def test_answer():\n"
        "    assert answer() == int(Path('oracle_data/value.txt').read_text())\n"
    ))
    write(original, "oracle_data/value.txt", "42")
    write(final, "oracle_data/value.txt", "0")
    write(final, "solution.py", "def answer(): return 42\n")

    result = grade(exercise, tmp_path, test_paths=["check_answer.py", "oracle_data"])

    assert result["solved"] is True
    assert result["test_changes"]["removed"] == ["check_answer.py"]
    assert result["test_changes"]["changed"] == ["oracle_data/value.txt"]


def test_timeout_is_recorded_and_never_solved(exercise, tmp_path):
    original, _ = exercise
    write(original, "test_solution.py", (
        "import time\ndef test_timeout():\n    time.sleep(30)\n"
    ))

    result = grade(exercise, tmp_path, timeout=1)

    assert result["timed_out"] is True
    assert result["timeout_seconds"] == 1
    assert result["pytest_exit_code"] is None
    assert result["solved"] is False
    assert result["error"] is None
    assert Path(result["stdout_path"]).exists()
    assert json.loads((tmp_path / "artifacts/result.json").read_text())["timed_out"]


def test_execution_error_is_recorded_and_never_solved(exercise, tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("synthetic interpreter launch failure")

    monkeypatch.setattr("bench.grade.subprocess.run", unavailable)
    result = grade(exercise, tmp_path)

    assert result["solved"] is False
    assert result["pytest_exit_code"] is None
    assert result["timed_out"] is False
    assert "synthetic interpreter launch failure" in result["error"]
    assert json.loads((tmp_path / "artifacts/result.json").read_text()) == result


def test_no_original_tests_is_not_solved(exercise, tmp_path):
    original, _ = exercise
    (original / "test_solution.py").unlink()
    result = grade(exercise, tmp_path)
    assert result["pytest_exit_code"] == 5
    assert result["solved"] is False


def test_parent_config_and_caller_options_do_not_control_grading(
    exercise, tmp_path, monkeypatch,
):
    original, final = exercise
    (original / "pytest.ini").unlink()
    (final / "pytest.ini").unlink()
    write(final, "solution.py", "def answer(): return 42\n")
    write(tmp_path, "pytest.ini", "[pytest]\naddopts = --invalid-parent-option\n")
    write(tmp_path, "conftest.py", "raise RuntimeError('parent conftest imported')\n")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--invalid-caller-option")
    monkeypatch.setenv("PYTEST_PLUGINS", "missing_caller_plugin")
    monkeypatch.setenv("PYTHONPATH", str(original))

    result = grade(exercise, tmp_path)

    assert result["solved"] is True
    assert result["test_edit"] is False


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout_creates_no_artifacts(exercise, tmp_path, timeout):
    with pytest.raises(ValueError, match="timeout"):
        grade(exercise, tmp_path, timeout=timeout)
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize("path", ["../escape", ".", ".meta/answer.py"])
def test_invalid_extra_path_creates_no_artifacts(exercise, tmp_path, path):
    with pytest.raises(ValueError, match="relative inside"):
        grade(exercise, tmp_path, test_paths=[path])
    assert not (tmp_path / "artifacts").exists()


def test_missing_explicit_oracle_path_records_setup_error(exercise, tmp_path):
    result = grade(exercise, tmp_path, test_paths=["missing"])
    assert result["solved"] is False
    assert result["pytest_exit_code"] is None
    assert "absent from the original" in result["error"]


def test_existing_output_is_preserved(exercise, tmp_path):
    output = tmp_path / "artifacts"
    output.mkdir()
    write(output, "keep.txt", "existing artifact")
    with pytest.raises(FileExistsError):
        grade(exercise, tmp_path)
    assert snapshot(output) == {"keep.txt": b"existing artifact"}


@pytest.mark.parametrize("which", [0, 1])
def test_output_inside_input_is_rejected(exercise, which):
    output = exercise[which] / "artifacts"
    with pytest.raises(ValueError, match="overlap"):
        grade_exercise(*exercise, output, task_id="overlap")
    assert not output.exists()


def test_main_setup_error_is_nonzero(exercise, capsys):
    original, final = exercise
    with pytest.raises(SystemExit) as error:
        main([
            "--original", str(original), "--final", str(final),
            "--output", str(original), "--task-id", "cli-error",
        ])
    assert error.value.code == 2
    assert "Grading setup failed" in capsys.readouterr().err


def test_module_cli_records_explicit_task_and_returns_unsolved(exercise, tmp_path):
    original, final = exercise
    output = tmp_path / "cli-artifacts"
    completed = subprocess.run(
        [
            sys.executable, "-m", "bench.grade", "--original", str(original),
            "--final", str(final), "--output", str(output), "--task-id", "cli-task",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert completed.returncode == 1, completed.stderr
    result = json.loads(completed.stdout)
    assert result["task_id"] == "cli-task"
    assert result["solved"] is False
    assert json.loads((output / "result.json").read_text()) == result
