"""Legacy gateway fixtures now explicitly enroll real HMAC state before use."""

import pytest


@pytest.fixture(autouse=True)
def signed_budget_fixtures(monkeypatch):
    from security_support import enroll

    from crocodile.gateway.budget import BudgetManager

    original = BudgetManager.__init__
    states = {}

    def initialized(self, db_path, price_table, *args, **kwargs):
        from pathlib import Path

        path = Path(db_path).absolute()
        if kwargs.get("state_integrity") is None:
            if path not in states:
                if path.exists():
                    raise AssertionError("fixture must enroll before creating state")
                states[path] = enroll(path)
            kwargs["state_integrity"] = states[path]
        original(self, path, price_table, *args, **kwargs)

    monkeypatch.setattr(BudgetManager, "__init__", initialized)
