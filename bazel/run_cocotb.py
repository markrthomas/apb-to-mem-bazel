#!/usr/bin/env python3
"""Bazel test entry point for a single cocotb testcase.

This is the Bazel analog of the pytest repo's ``tests/_sim.py`` — same cocotb
Python-runner logic, but exposed as a standalone CLI so a Bazel ``sh_test`` can
drive it. Running exactly one ``@cocotb.test`` per Bazel target (its own ``vvp``
process) reproduces the source Makefile's "fresh, time-0-zeroed memory per test"
property, just as the pytest layer did.

The build/run happen non-hermetically: the system ``iverilog`` (pinned to the
apt build via ICARUS_BIN_DIR) and the interpreter that already carries cocotb +
pyuvm. Bazel supplies the target graph and the sources (as runfiles); it does
not sandbox the toolchain (targets are tagged ``local``/``no-sandbox``).

Usage:
  run_cocotb.py --toplevel apb_mem --module apb_test --module-dir tb \\
      --testcase write_read_test --source rtl/apb_mem.sv [--define K=V] [--waves]

Paths are resolved to absolute up front (the cocotb runner cd's into its build
dir, so relative runfiles paths would otherwise break). Build output goes to
TEST_TMPDIR when Bazel provides it.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonout  # noqa: E402  (sibling helper in bazel/)


def _env_shim() -> None:
    """Replicate the pytest conftest env pinning (see that repo's conftest.py)."""
    os.environ.setdefault("ICARUS_BIN_DIR", "/usr/bin")
    os.environ.pop("VIRTUAL_ENV", None)
    os.environ.pop("PYTHONHOME", None)
    os.environ["PYGPI_PYTHON_BIN"] = sys.executable
    os.environ["PYTHON_BIN"] = sys.executable


@contextlib.contextmanager
def _pinned_icarus_on_path() -> Iterator[None]:
    """Front-load ICARUS_BIN_DIR on PATH only around the runner calls.

    The cocotb Python runner invokes a bare ``iverilog``/``vvp`` from PATH and
    ignores ICARUS_BIN_DIR (that is a Makefile-flow variable). Scope the change
    so it does not shadow the PATH-default Verilator used by the coverage gate.
    """
    icarus_dir = os.environ.get("ICARUS_BIN_DIR")
    old_path = os.environ.get("PATH", "")
    if icarus_dir and os.path.isdir(icarus_dir):
        os.environ["PATH"] = icarus_dir + os.pathsep + old_path
    try:
        yield
    finally:
        os.environ["PATH"] = old_path


def main() -> int:
    argv = sys.argv[1:]
    json_path = jsonout.json_arg(argv)

    p = argparse.ArgumentParser(description="run one cocotb testcase under Bazel")
    p.add_argument("--toplevel", required=True, help="HDL top module")
    p.add_argument("--module", required=True, help="cocotb test module (e.g. apb_test)")
    p.add_argument("--module-dir", required=True, help="dir holding the test module")
    p.add_argument("--testcase", required=True, help="the @cocotb.test to run")
    p.add_argument("--source", action="append", default=[], help="Verilog source (repeatable)")
    p.add_argument("--define", action="append", default=[], help="K or K=V define (repeatable)")
    p.add_argument("--waves", action="store_true", help="dump an FST waveform")
    args = p.parse_args(argv)

    _env_shim()

    # Absolute paths: the runner cd's into the build dir, so relative runfiles
    # paths would not resolve there.
    sources = [str(Path(s).resolve()) for s in args.source]
    module_dir = str(Path(args.module_dir).resolve())
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)  # the runner rebuilds child PYTHONPATH from sys.path

    defines = {}
    for d in args.define:
        k, _, v = d.partition("=")
        defines[k] = v if v else 1

    build_dir = os.path.join(os.environ.get("TEST_TMPDIR", os.getcwd()), "sim_build")

    # Import after the experimental-warning-emitting module so -W flags apply cleanly.
    from cocotb.runner import get_results, get_runner

    timescale = ("1ns", "1ps")  # apt Icarus defaults to 1s precision otherwise
    runner = get_runner("icarus")
    with _pinned_icarus_on_path():
        runner.build(
            verilog_sources=sources,
            hdl_toplevel=args.toplevel,
            build_args=["-g2012"],
            defines=defines,
            build_dir=build_dir,
            always=True,
            waves=args.waves,
            timescale=timescale,
        )
        results_xml = runner.test(
            test_module=args.module,
            hdl_toplevel=args.toplevel,
            hdl_toplevel_lang="verilog",
            testcase=args.testcase,
            plusargs=(["-fst"] if args.waves else []),
            build_dir=build_dir,
            test_dir=build_dir,
            timescale=timescale,
            extra_env={"PYGPI_PYTHON_BIN": sys.executable, "PYTHON_BIN": sys.executable},
        )

    total, failed = get_results(Path(results_xml))
    passed = failed == 0
    jsonout.emit(
        {
            "gate": "sim",
            "testcase": args.testcase,
            "toplevel": args.toplevel,
            "status": "pass" if passed else "fail",
            "tests": total,
            "failed": failed,
        },
        json_path,
    )
    if not passed:
        print(f"[FAIL] {args.testcase}: {failed}/{total} cocotb test(s) failed", file=sys.stderr)
        return 1
    print(f"[PASS] {args.testcase}: {total} cocotb test(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
