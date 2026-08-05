# CLAUDE.md

Guidance for working in this repo. Read the README for the full narrative + diagrams;
this file captures what's easy to trip over.

## What this is

APB3 byte-wide 32K memory (`rtl/apb_mem.sv`) with a self-checking pyuvm/cocotb
testbench, orchestrated by **Bazel** (custom Starlark rules) instead of a Makefile.
Derived from the sibling `uvm_review` repo: same RTL and testbench, Make targets
re-expressed as Bazel `test_suite`s + tags, every test exporting a JSON result.

## Build & test

```bash
bazel test //:ci          # everything (sim + lint + lp + coverage + uvm); the full gate
bazel test //:sim         # the three functional cocotb tests
bazel test //:sim_random_test --test_arg=--waves --test_output=all   # one test + FST waves
make help                 # optional shim: make verbs -> the bazel commands above
```

`bazel test //:ci` is the canonical "is it healthy" check — expect **7/7 pass**
(`//:uvm` passes by *skipping* when no UVM simulator is present; that's correct, not a
gap). Verified green on this host 2026-08-05.

## The one thing to understand: it is non-hermetic by design

The Starlark rules in `bazel/hdl.bzl` (`cocotb_test`, `hdl_tool_test`) generate a bash
launcher that **shells out to the system toolchain** — they do not vendor Python, cocotb,
or Icarus. This mirrors the reality the source Makefile lived in. Consequences:

- Sim targets are tagged `local` + `no-sandbox` + `no-cache` (`_SIM_TAGS` in `hdl.bzl`).
  Results are never cached because the outcome depends on the host toolchain, not just the
  declared inputs. Don't "fix" this by adding caching.
- **Toolchain pins that make it work (do not assume the `PATH` versions):**
  - Launchers exec `${APB_PYTHON:-/usr/bin/python3}`. On this host `/usr/bin/python3` is
    **Python 3.10 + cocotb 1.9.2 + pyuvm 4.0.1** — the versions the tb targets. The
    `oss-cad-suite` python3 on `PATH` is cocotb 2.x and is **not** what the tests use.
    Point elsewhere with `bazel test --test_env=APB_PYTHON=/path/to/python //...`.
  - `run_cocotb.py` pins `ICARUS_BIN_DIR=/usr/bin` so the **apt Icarus 11** is used even
    when an `oss-cad-suite` `iverilog` shadows it on `PATH`. If you change the runner,
    preserve this pin.
- One `@cocotb.test` runs per Bazel target (its own `vvp`) — that's what gives each test a
  fresh, time-0-zeroed memory. `functional_suite` in `hdl.bzl` stamps out one
  `sim_<testcase>` target per testcase.

## Layout

- `rtl/apb_mem.sv` — the DUT.
- `tb/*.py` — pyuvm testbench (`apb_test.py` is the cocotb module; bfm/components/seq).
- `bazel/hdl.bzl` — the two custom test rules + `functional_suite` macro. **Start here**
  before touching how tests are built.
- `bazel/run_*.py` — the per-gate runners (cocotb / lint / coverage / uvm); `jsonout.py`
  writes each test's `result.json`.
- `uvm/*.sv` — SystemVerilog/UVM flow + bound `apb_sva` assertions; only exercised by
  `//:uvm`, which skips without a licensed simulator (vcs/xrun/qrun).
- `lp/` — low-power UPF-emulated variant (`//:lp`). `sim/sim_main.cpp` — Verilator coverage
  harness.
- `BUILD.bazel` — the target graph; aggregate suites `check` / `regress` / `ci` map the old
  make aggregates.

## Conventions

- Every test writes `result.json` to `TEST_UNDECLARED_OUTPUTS_DIR`
  (`bazel-testlogs/<target>/test.outputs/outputs.zip`) and echoes a `[JSON] {...}` log line.
  Preserve this contract when adding/altering gates. `--config=json` additionally streams
  the whole invocation to `bazel-events.json` (BEP).
- `COV_MIN=<n> bazel test --test_env=COV_MIN //:coverage` overrides the 100% line-coverage
  floor. `UVM_TEST=<name>` (via `--test_env`) picks the UVM test.
- Verilator is optional — lint and coverage skip cleanly when it's absent.
