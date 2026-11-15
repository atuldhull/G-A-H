"""Fixed trusted entry point for all fifteen architecture exercises."""

import pytest

from crocodile import services
from redteam.cases import CASES, integrity_case, owner_case, readme_cli_case, undo_cli_case
from redteam.harness import Blocked, Exercise
from redteam.inventory import CASES as INVENTORY


@pytest.fixture
def exercise(tmp_path, monkeypatch):
    env = Exercise(tmp_path, monkeypatch)
    try:
        yield env
    finally:
        services.reset()
        assert not env.network_attempts, "synthetic exercise attempted network I/O"


@pytest.mark.parametrize("case", INVENTORY, ids=lambda case: case.pytest_id)
def test_security_case(case, exercise, capsys, request):
    try:
        if case.group in (7, 8, 13):
            owner_case(exercise, case.group, capsys)
        else:
            CASES[case.group](exercise)
    except Blocked as error:
        pytest.skip(str(error))
    finally:
        request.node.user_properties.append(("evidence", exercise.snapshot()))


@pytest.mark.parametrize(
    "flow",
    [readme_cli_case, undo_cli_case, integrity_case],
    ids=["readme-denial", "shadow-undo", "integrity-abort"],
)
def test_cli_flow(flow, exercise, request):
    try:
        flow(exercise)
    except Blocked as error:
        pytest.skip(str(error))
    finally:
        request.node.user_properties.append(("evidence", exercise.snapshot()))
