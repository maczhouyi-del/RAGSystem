"Execute actual packaged native assistant, including dependency error path."

import os
import platform
import re
import subprocess
import sys

binary = os.path.abspath(sys.argv[1])
result = subprocess.run([binary, "--help"], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0 and "backup" in result.stdout and "restore" in result.stdout
environment = os.environ.copy()
environment["PATH"] = ""
result = subprocess.run(
    [binary, "check"], env=environment, capture_output=True, text=True, encoding="utf-8"
)
assert result.returncode == 1 and "docker_missing" in result.stdout
assert "Traceback" not in result.stdout + result.stderr
print(
    "PASS: actual native assistant help and missing-Docker recovery ad"
    "vice; no developer runtime required."
)

if platform.system() == "Windows":
    result = subprocess.run(
        [binary, "--gui-smoke"], capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    if result.returncode != 0:
        # Do not echo child output. Surface only fixed exception classes/codes
        # so native failures cannot be mistaken for a successful build.
        classes = sorted(
            set(
                re.findall(
                    r"(?m)^(AssertionError|TclError|ImportError|ModuleNotFoundError)\b",
                    result.stderr,
                )
            )
        )
        codes = [code for code in ("gui_unavailable", "deployment_failed") if code in result.stdout]
        print(
            f"ERROR: packaged_gui_smoke_failed exit={result.returncode} "
            f"types={classes} codes={codes}"
        )
    assert result.returncode == 0 and "native GUI five pages rendered" in result.stdout
    print(
        "PASS: actual Windows packaged GUI startup (automated runner,"
        " not Windows11 human acceptance)."
    )
