#!/usr/bin/env python3
"""RTL lint gate (Bazel) — the analog of the pytest test_lint.py.

  * iverilog -g2012 -Wall compile check (hard failure on error)
  * verilator --lint-only (skips cleanly when Verilator is absent)

Usage: run_lint.py <rtl.sv> [--json <path>]
Exports a JSON result via the shared jsonout wrapper.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonout  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    json_path = jsonout.json_arg(argv)
    rtl = argv[0]

    iverilog = os.path.join(os.environ.get("ICARUS_BIN_DIR", "/usr/bin"), "iverilog")
    if not os.path.exists(iverilog):
        iverilog = shutil.which("iverilog") or "iverilog"

    result = {"gate": "lint", "iverilog": None, "verilator": None, "status": "pass"}

    r = subprocess.run([iverilog, "-g2012", "-Wall", "-o", os.devnull, rtl])
    result["iverilog"] = "pass" if r.returncode == 0 else "fail"
    if r.returncode != 0:
        result["status"] = "fail"
        jsonout.emit(result, json_path)
        return 1

    if shutil.which("verilator"):
        r = subprocess.run(["verilator", "--lint-only", "-Wall", "-Wno-DECLFILENAME", rtl])
        result["verilator"] = "pass" if r.returncode == 0 else "fail"
        if r.returncode != 0:
            result["status"] = "fail"
            jsonout.emit(result, json_path)
            return 1
    else:
        print("[LINT] verilator not on PATH — skipping RTL lint")
        result["verilator"] = "skipped"

    print("[LINT] passed")
    jsonout.emit(result, json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
