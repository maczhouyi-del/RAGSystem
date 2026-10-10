"""Read identity from actual compiled binaries; runner labels alone are insufficient."""

import argparse
import json
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--desktop", type=Path, required=True)
parser.add_argument("--assistant", type=Path, required=True)
parser.add_argument("--platform", required=True)
parser.add_argument("--architecture", required=True)
args = parser.parse_args()
for path, flag in [(args.desktop, "--build-info"), (args.assistant, "identity")]:
    result = subprocess.run([str(path.resolve()), flag], capture_output=True, text=True, check=True)
    value = json.loads(result.stdout)
    assert value["platform"] == args.platform and value["architecture"] == args.architecture
    assert value["version"] == "0.2.0"
    if flag == "--build-info":
        assert value["sourceCommit"] == os.environ["RAGAGENT_SOURCE_COMMIT"]
print("PASS: actual desktop and setup binary CPU/platform/version; immutable desktop build SHA.")
