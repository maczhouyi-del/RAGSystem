"""Execute actual packaged native assistant, including dependency error path."""

import os
import subprocess
import sys

binary = os.path.abspath(sys.argv[1])
result = subprocess.run([binary, "--help"], capture_output=True, text=True)
assert result.returncode == 0 and "backup" in result.stdout and "restore" in result.stdout
environment = os.environ.copy()
environment["PATH"] = ""
result = subprocess.run([binary, "check"], env=environment, capture_output=True, text=True)
assert result.returncode == 1 and "docker_missing" in result.stdout
assert "Traceback" not in result.stdout + result.stderr
print(
    "PASS: actual native assistant help and missing-Docker recovery ad"
    "vice; no developer runtime required."
)
