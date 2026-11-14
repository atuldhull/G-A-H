"""Trusted fixture enrollment; production startup must never enroll unknown state."""

import re
from pathlib import Path

from crocodile import services
from crocodile.gateway.budget import init_database
from crocodile.runtime_security import SecurityContext
from crocodile.security.classification import SecurityStore
from crocodile.security.integrity import HMACKeys, StateIntegrity


class Vault:
    value = None

    def get_password(self, *_):
        return self.value

    def set_password(self, _service, _name, value):
        self.value = value


def confirm(prompt):
    required = re.search(r"Type ([a-z]+ \d{2}) to approve", prompt)
    return required[1] if required else "y"


def enroll(path):
    path = Path(path)
    state = StateIntegrity(path, keys=HMACKeys(backend=Vault()))
    db = init_database(path)
    try:
        SecurityStore._schema(db)
        db.execute("CREATE TABLE grants(session TEXT, argv_json TEXT)")
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        state.initialize(db)
        db.commit()
    finally:
        db.close()
    return state


def install(state):
    services.override(
        "security_factory", lambda repo, task, **kw: SecurityContext(repo, task, integrity=state, **kw)
    )
    services.override(
        "security_resume", lambda repo, sid, **kw: SecurityContext.resume(repo, sid, integrity=state, **kw)
    )
