"""Create or reset an admin account.

  cd backend && python -m scripts.create_admin --username prof
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import security  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True)
    a = ap.parse_args()
    pw = getpass.getpass("New password: ")
    if pw != getpass.getpass("Repeat password: "):
        print("Passwords differ.")
        return 1
    problem = security.password_problem(pw)
    if problem:
        print(problem)
        return 1
    Database(Settings.from_env().db_path).upsert_admin(a.username.strip(), security.hash_password(pw))
    print(f"Admin '{a.username}' saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
