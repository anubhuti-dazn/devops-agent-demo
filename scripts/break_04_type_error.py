"""
Scenario 4: Runtime TypeError — wrong return type
Changes the /health endpoint to return a string instead of a dict.
The test expects a JSON object; it will get a plain string and fail on .json() parsing or assertion.
The DevOps agent should read the test output and trace the bug to health.py.
"""
import sys
import os

TARGET = os.path.join(os.path.dirname(__file__), "..", "app", "routes", "health.py")

BROKEN_RETURN = '    return "ok"\n'
ORIGINAL_RETURN = (
    '    return {\n'
    '        "status": "ok" if db_status == "ok" else "degraded",\n'
    '        "database": db_status,\n'
    '    }\n'
)


def apply():
    with open(TARGET, "r") as f:
        content = f.read()
    if BROKEN_RETURN in content:
        print("Already broken. Run restore first.")
        return
    new = content.replace(ORIGINAL_RETURN, BROKEN_RETURN)
    if new == content:
        print("ERROR: Could not find target block to replace.")
        sys.exit(1)
    with open(TARGET, "w") as f:
        f.write(new)
    print("BROKEN: /health now returns a plain string instead of a JSON dict")
    print("Expected CI failure: test_health_check assertion error on response structure")


if __name__ == "__main__":
    apply()
