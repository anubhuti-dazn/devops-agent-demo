"""
Scenario 2: Failing Test — wrong assertion
Changes the expected HTTP status code for task creation from 201 to 200.
The app is fine; the test is wrong.
The DevOps agent should read the test failure, identify the wrong assertion, and correct it.
"""
import sys
import os

TARGET = os.path.join(os.path.dirname(__file__), "..", "tests", "test_tasks.py")

BROKEN_LINE = "    assert response.status_code == 200\n    data = response.json()\n    assert data[\"title\"] == \"Fix CI pipeline\""
ORIGINAL_LINE = "    assert response.status_code == 201\n    data = response.json()\n    assert data[\"title\"] == \"Fix CI pipeline\""


def apply():
    with open(TARGET, "r") as f:
        content = f.read()
    if BROKEN_LINE in content:
        print("Already broken. Run restore first.")
        return
    new = content.replace(ORIGINAL_LINE, BROKEN_LINE)
    if new == content:
        print("ERROR: Could not find target line to break.")
        sys.exit(1)
    with open(TARGET, "w") as f:
        f.write(new)
    print("BROKEN: test_create_task now asserts status 200 instead of 201")
    print("Expected CI failure: AssertionError in tests/test_tasks.py::test_create_task")


if __name__ == "__main__":
    apply()
