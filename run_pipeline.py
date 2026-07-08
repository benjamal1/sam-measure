"""Repo-root entry stub. Real orchestration wired in plan 05."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def run(*args, **kwargs):
    raise NotImplementedError("wired in plan 05")


if __name__ == "__main__":
    run()
