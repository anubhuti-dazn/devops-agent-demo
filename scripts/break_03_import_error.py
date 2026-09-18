"""
Scenario 3: ImportError — missing module
Adds an import for a non-existent module in app/main.py.
CI will fail when pytest tries to collect tests (import error).
The DevOps agent should spot the ModuleNotFoundError and remove the bad import.
"""
import sys
import os

TARGET = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")

BAD_IMPORT = "from app.middleware.auth import require_auth  # noqa\n"
ANCHOR = "from fastapi import FastAPI\n"


def apply():
    with open(TARGET, "r") as f:
        content = f.read()
    if BAD_IMPORT in content:
        print("Already broken. Run restore first.")
        return
    new = content.replace(ANCHOR, ANCHOR + BAD_IMPORT)
    if new == content:
        print("ERROR: Could not find anchor line.")
        sys.exit(1)
    with open(TARGET, "w") as f:
        f.write(new)
    print("BROKEN: app/main.py now imports non-existent app.middleware.auth")
    print("Expected CI failure: ModuleNotFoundError during test collection")


if __name__ == "__main__":
    apply()
