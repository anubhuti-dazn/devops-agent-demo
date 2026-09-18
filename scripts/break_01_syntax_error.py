"""
Scenario 1: Syntax Error
Introduces a Python SyntaxError in app/models.py.
CI will fail at the import/lint stage.
The DevOps agent should detect the SyntaxError from the CI log and fix it.
"""
import sys
import os

TARGET = os.path.join(os.path.dirname(__file__), "..", "app", "models.py")

BROKEN_LINE = "    status: TaskStatus = TaskStatus.pending\n\n\nclass TaskUpdate(BaseModel\n"
ORIGINAL_LINE = "    status: TaskStatus = TaskStatus.pending\n\n\nclass TaskUpdate(BaseModel):\n"


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
    print("BROKEN: SyntaxError introduced in app/models.py (missing closing paren on class TaskUpdate)")
    print("Expected CI failure: SyntaxError in lint + test jobs")


if __name__ == "__main__":
    apply()
