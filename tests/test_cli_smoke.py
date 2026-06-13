import subprocess
import sys

from xianyu_crawler import cli


def test_cli_main_callable():
    assert callable(cli.main)


def test_cli_run_help_exits_zero():
    r = subprocess.run(
        [sys.executable, "-m", "xianyu_crawler.cli", "run", "--help"],
        capture_output=True,
    )
    assert r.returncode == 0
