"""JSON export wrapper shared by every Bazel test runner.

Each runner calls ``emit(...)`` with a structured result. The payload is:

  * written to ``$TEST_UNDECLARED_OUTPUTS_DIR/result.json`` when Bazel provides
    that dir — Bazel collects it into ``<target>/test.outputs/outputs.zip`` so a
    machine-readable result travels with every test run;
  * echoed to stdout as a single ``[JSON] {...}`` line so it shows up in the log
    and in ``--test_output=all`` streams;
  * also written to any explicit path given via ``--json <path>`` (see
    ``json_arg``), for callers outside Bazel.

This is intentionally dependency-free (stdlib ``json``) so it runs under the
same system interpreter as cocotb.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Mapping, Optional


def json_arg(argv: list[str]) -> Optional[str]:
    """Pop a leading/anywhere ``--json <path>`` from argv; return the path or None."""
    if "--json" in argv:
        i = argv.index("--json")
        path = argv[i + 1]
        del argv[i : i + 2]
        return path
    return None


def emit(result: Mapping[str, Any], json_path: Optional[str] = None) -> None:
    """Export `result` as JSON to the undeclared-outputs dir, stdout, and json_path."""
    payload = json.dumps(result, indent=2, sort_keys=True)

    targets = []
    outdir = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        targets.append(os.path.join(outdir, "result.json"))
    if json_path:
        targets.append(json_path)
    for t in targets:
        with open(t, "w") as fh:
            fh.write(payload + "\n")

    # Compact one-liner for the console/log.
    sys.stdout.write("[JSON] " + json.dumps(result, sort_keys=True) + "\n")
    sys.stdout.flush()
