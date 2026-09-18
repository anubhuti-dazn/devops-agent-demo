"""
Restore all files to their original (passing) state.
Run this after each DevOps agent test scenario to reset the project.
"""
import subprocess
import sys
import os

repo_root = os.path.join(os.path.dirname(__file__), "..")

result = subprocess.run(
    ["git", "checkout", "--", "app/", "tests/", "Dockerfile"],
    cwd=repo_root,
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print("All files restored to last committed state.")
else:
    print("git checkout failed:")
    print(result.stderr)
    sys.exit(1)
