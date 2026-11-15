"""One gateway setting contract for runtime, init, diagnostics and legacy installs."""


def gateway_url(config):
    nested = config.get("bifrost", {})
    if not isinstance(nested, dict):
        raise ValueError("bifrost settings must be a mapping")
    current, legacy = nested.get("base_url"), config.get("bifrost_url")
    for value in (current, legacy):
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError("gateway URL must be a nonempty string")
    if current and legacy and current.rstrip("/") != legacy.rstrip("/"):
        raise ValueError("conflicting canonical and legacy gateway URLs")
    return current or legacy or "http://127.0.0.1:8080"
