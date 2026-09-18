"""
Scenario 5: Docker Build Failure
Adds an invalid RUN command to the Dockerfile.
CI will fail at the Docker build stage (all tests pass but the image can't be built).
The DevOps agent should read the docker build log and fix the invalid instruction.
"""
import sys
import os

TARGET = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")

BAD_LINE = "RUN apt-get install -y nonexistent-package-xyz-123\n"
ANCHOR = "COPY app/ ./app/\n"


def apply():
    with open(TARGET, "r") as f:
        content = f.read()
    if BAD_LINE in content:
        print("Already broken. Run restore first.")
        return
    new = content.replace(ANCHOR, ANCHOR + "\n" + BAD_LINE)
    if new == content:
        print("ERROR: Could not find anchor line.")
        sys.exit(1)
    with open(TARGET, "w") as f:
        f.write(new)
    print("BROKEN: Dockerfile now tries to install a non-existent package")
    print("Expected CI failure: docker build fails in the 'build' job")


if __name__ == "__main__":
    apply()
