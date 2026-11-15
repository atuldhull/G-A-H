"""Execute only the packaged trusted suite and write explicit per-case verdicts."""

import argparse
import os
from pathlib import Path


def run(report):
    import pytest

    from redteam.reporting import ReportPlugin

    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    plugin = ReportPlugin(report)
    status = pytest.main(
        [
            str(Path(__file__).with_name("security_suite.py")),
            "--noconftest",
            "-p",
            "no:cacheprovider",
            "-q",
            "-ra",
        ],
        plugins=[plugin],
    )
    if status:
        return int(status)
    return 2 if any(row["status"] == "blocked" for row in plugin.results.values()) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("redteam-report.json"))
    args = parser.parse_args()
    raise SystemExit(run(args.report))


if __name__ == "__main__":
    main()
