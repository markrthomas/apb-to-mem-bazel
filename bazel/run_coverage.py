#!/usr/bin/env python3
"""Verilator C++ coverage gate (Bazel) — analog of the pytest test_coverage.py.

Ports the source Makefile's coverage recipe: a Verilator --coverage build of the
RTL, linked against sim/sim_main.cpp, run to emit coverage.dat, converted to
lcov, and gated on a line-coverage floor (COV_MIN env, default 100%). Skips
cleanly (exit 0) when Verilator is not installed.

Usage: run_coverage.py <rtl.sv> <sim_main.cpp> [--json <path>]
Build artifacts go under $TEST_TMPDIR. Exports a JSON result.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonout  # noqa: E402

COV_MIN = float(os.environ.get("COV_MIN", "100"))


def _verilator_include() -> Path:
    vbin = Path(shutil.which("verilator")).resolve()
    return (vbin.parent / ".." / "share" / "verilator" / "include").resolve()


def _run(cmd, **kw) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(map(str, cmd))}\n{r.stdout}\n{r.stderr}")


def _line_pct(info: Path) -> float:
    found = hit = 0
    for line in info.read_text().splitlines():
        if line.startswith("DA:"):
            found += 1
            if int(line[3:].split(",", 1)[1]) > 0:
                hit += 1
    return (100.0 * hit / found) if found else 0.0


def main() -> int:
    argv = sys.argv[1:]
    json_path = jsonout.json_arg(argv)
    rtl = str(Path(argv[0]).resolve())
    sim_main = str(Path(argv[1]).resolve())

    if shutil.which("verilator") is None:
        print("[COVERAGE] verilator not on PATH — skipping")
        jsonout.emit({"gate": "coverage", "status": "skipped", "reason": "no verilator"}, json_path)
        return 0

    tmp = os.environ.get("TEST_TMPDIR", os.getcwd())
    cov_dir = Path(tmp) / "obj_dir_cov"
    if cov_dir.exists():
        shutil.rmtree(cov_dir)
    cov_info = Path(tmp) / "coverage.info"
    vinc = _verilator_include()

    try:
        _run(["verilator", "--coverage", "-cc", rtl, "--top-module", "apb_mem",
              "--Mdir", str(cov_dir), "-Wall", "-Wno-DECLFILENAME"])
        _run(["make", "-C", str(cov_dir), "-f", "Vapb_mem.mk"])
        sim_cov = cov_dir / "sim_cov"
        _run(["g++", "-DVM_COVERAGE=1", "-o", str(sim_cov), sim_main,
              str(cov_dir / "Vapb_mem__ALL.a"),
              f"-I{cov_dir}", f"-I{vinc}", f"-I{vinc / 'vltstd'}",
              str(vinc / "verilated.cpp"), str(vinc / "verilated_cov.cpp"),
              str(vinc / "verilated_threads.cpp"), "-pthread", "-lm"])
        _run(["./sim_cov"], cwd=cov_dir)
        if shutil.which("verilator_coverage") is None:
            print("[COVERAGE] verilator_coverage absent — coverage.dat produced but not scored")
            jsonout.emit({"gate": "coverage", "status": "skipped", "reason": "no verilator_coverage"}, json_path)
            return 0
        _run(["verilator_coverage", "--write-info", str(cov_info), str(cov_dir / "coverage.dat")])
    except RuntimeError as e:
        print(e, file=sys.stderr)
        jsonout.emit({"gate": "coverage", "status": "fail", "error": str(e).splitlines()[0]}, json_path)
        return 1

    pct = _line_pct(cov_info)
    passed = pct >= COV_MIN
    print(f"[COVERAGE] line coverage {pct:.1f}% (floor {COV_MIN:.0f}%)")
    jsonout.emit(
        {"gate": "coverage", "status": "pass" if passed else "fail",
         "line_pct": round(pct, 1), "floor": COV_MIN},
        json_path,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
