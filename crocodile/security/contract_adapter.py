"""Accept the agreed shared Action without changing the shared owner's types.

Network fields remain a Part 3 extension. Only exact known dataclasses are
adapted; model objects cannot supply arbitrary conversion behavior.
"""


def normalize_action(action):
    from crocodile.contracts import Action as SharedAction

    from .types import Action

    if type(action) is SharedAction:
        return Action(
            kind=action.kind,
            argv=action.argv,
            diff=action.diff,
            source=action.source,
            cwd=action.cwd,
            paths=action.paths,
            replacements=action.replacements,
        )
    return action
