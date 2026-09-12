#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repo_root"

output_dir=$(mktemp -d "${TMPDIR:-/tmp}/trialmark-demo.XXXXXX")
"${PYTHON:-python}" -m examples.demo.run_demo --output-dir "$output_dir"
# Driver source: examples/demo/run_demo.py
