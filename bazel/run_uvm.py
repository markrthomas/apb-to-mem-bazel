#!/usr/bin/env python3
"""SystemVerilog UVM gate (Bazel) — analog of the pytest test_uvm.py.

Needs a UVM-capable commercial simulator (VCS / Xcelium / Questa). None is
licensed on the dev host, so — like the source Makefile — this DEGRADES
GRACEFULLY: it detects a simulator and, finding none, prints a skip and exits 0.
On a licensed host it compiles + runs the multi-file TB.

Usage: run_uvm.py <if.sv> <rtl.sv> <sva.sv> <pkg.sv> <top.sv> [--json <path>]
       (sources in uvm/Makefile MULTI_SRC order)
Select the UVM test with the UVM_TEST env var (default apb_random_test).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonout  # noqa: E402

UVM_TEST = os.environ.get("UVM_TEST", "apb_random_test")


def main() -> int:
    argv = sys.argv[1:]
    json_path = jsonout.json_arg(argv)
    sources = argv  # multi-file compile order, passed positionally

    def run(cmd) -> int:
        return subprocess.run(cmd).returncode

    if shutil.which("vcs"):
        sim, rc = "vcs", 0
        rc = run(["vcs", "-full64", "-sverilog", "-ntb_opts", "uvm-1.2",
                  "-timescale=1ns/1ps", "+incdir+.", *sources, "-o", "simv"])
        if rc == 0:
            rc = run(["./simv", f"+UVM_TESTNAME={UVM_TEST}"])
    elif shutil.which("xrun"):
        sim = "xcelium"
        rc = run(["xrun", "-64bit", "-sv", "-uvm", "-timescale", "1ns/1ps",
                  "-incdir", ".", *sources, f"+UVM_TESTNAME={UVM_TEST}"])
    elif shutil.which("qrun"):
        sim = "questa"
        rc = run(["qrun", "-64", "-sv", "-uvm", "-timescale", "1ns/1ps", "+incdir+.",
                  *sources, "-top", "apb_tb_top", f"+UVM_TESTNAME={UVM_TEST}"])
    else:
        print("[UVM] no UVM simulator (vcs/xrun/qrun) on PATH — skipping "
              "(this host has no SystemVerilog/UVM license)")
        jsonout.emit({"gate": "uvm", "status": "skipped", "reason": "no simulator"}, json_path)
        return 0

    passed = rc == 0
    jsonout.emit(
        {"gate": "uvm", "status": "pass" if passed else "fail",
         "simulator": sim, "uvm_test": UVM_TEST},
        json_path,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
