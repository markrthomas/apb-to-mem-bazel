# CLAUDE.md

Orientation for working in this repo. The [README](README.md) has the full narrative
and diagrams; [docs/TUTORIAL.md](docs/TUTORIAL.md) is the learn-by-doing version. This
file is the fast path + the things that are easy to trip over.

## What this is

APB3 byte-wide 32K memory (`rtl/apb_mem.sv`) with a self-checking pyuvm/cocotb
testbench, orchestrated by **Bazel** (custom Starlark rules) instead of a Makefile.
Derived from the sibling `uvm_review` repo: same RTL and testbench, Make targets
re-expressed as Bazel `test_suite`s + tags, every test exporting a JSON result.

## Commands

| Goal | Command |
|---|---|
| Full health check (7/7) | `bazel test //:ci` |
| The three functional tests | `bazel test //:sim` |
| One testcase | `bazel test //:sim_random_test` |
| See the sim log | add `--test_output=all` (Bazel is quiet on a pass) |
| Dump waves (FST) | add `--test_arg=--waves` |
| Tag selection | `bazel test //... --test_tag_filters=sim` |
| List targets | `bazel query //...` |
| Familiar verbs | `make help` (thin shim over the above) |

`bazel test //:ci` is the canonical "is it healthy" check — expect **7/7 pass**
(`//:uvm` passes by *skipping* when no UVM simulator is present; that's correct, not a
gap). Verified green on this host 2026-08-05.

## The one thing to understand: it is non-hermetic by design

The Starlark rules in `bazel/hdl.bzl` (`cocotb_test`, `hdl_tool_test`) generate a bash
launcher that **shells out to the system toolchain** — they do not vendor Python, cocotb,
or Icarus. This mirrors the reality the source Makefile lived in. Consequences:

- Sim targets are tagged `local` + `no-sandbox` + `no-cache` (`_SIM_TAGS` in `hdl.bzl`) —
  the outcome depends on the host toolchain, not just the declared inputs, so the *action*
  cache is disabled. **Don't "fix" this by adding caching.** Note the `no-cache` tag does
  **not** disable Bazel's *test-result* caching: an unchanged `bazel test` still replays a
  "(cached) PASSED". Add `--nocache_test_results` to force a real re-run (e.g. `make wave`
  does this so waves reflect fresh stimulus).
- One `@cocotb.test` runs per Bazel target (its own `vvp`) — that's what gives each test a
  fresh, time-0-zeroed memory. `functional_suite` in `hdl.bzl` stamps out one
  `sim_<testcase>` target per testcase.

### Toolchain pins (do NOT assume the `PATH` versions)

| Pin | Where | Why |
|---|---|---|
| `${APB_PYTHON:-/usr/bin/python3}` | launcher (`hdl.bzl` `DEFAULT_PY`) | `/usr/bin/python3` = Python 3.10 + **cocotb 1.9.2 + pyuvm 4.0.1** (the tb targets). The oss-cad-suite python on `PATH` is cocotb 2.x and is **not** used. |
| `ICARUS_BIN_DIR=/usr/bin` | `run_cocotb.py:39` | forces the **apt Icarus 11** even when an oss-cad-suite `iverilog` shadows it on `PATH`. Preserve this if you touch the runner. |

Override the interpreter with `bazel test --test_env=APB_PYTHON=/path/to/python //...`.

## Gates & skip behavior

| Target | Runner | Skips when… | Passing = |
|---|---|---|---|
| `//:sim_*` (3) | `run_cocotb.py` | — | cocotb reports 0 failed |
| `//:lint` | `run_lint.py` | Verilator absent → verilator part skips (iverilog still runs) | both lints clean |
| `//:coverage` | `run_coverage.py` | Verilator absent → whole gate skips (exit 0) | `line_pct ≥ COV_MIN` (default 100) |
| `//:lp` | `run_cocotb.py` (`LP_EMULATE=1`) | — | power-cycle asserts hold |
| `//:uvm` | `run_uvm.py` | no vcs/xrun/qrun → skips (exit 0) | UVM sim exits 0 |

A "skip" is a **pass** here (exit 0) — matches the source Makefile's graceful degradation.

## Where to make change X

| Task | Touch |
|---|---|
| New functional test | add a sequence (`tb/apb_seq.py`) → `uvm_test` + `@cocotb.test` (`tb/apb_test.py`) → add the name to `functional_suite.testcases` (`BUILD.bazel`) |
| One-off test w/ a define or extra source | a bare `cocotb_test(...)` in `BUILD.bazel` (see `//:lp`) |
| Change how tests are built | `bazel/hdl.bzl` (the rules) |
| Change a gate's logic | the matching `bazel/run_*.py` |
| Change the JSON payload | the runner's `jsonout.emit({...})` call |
| DUT behavior | `rtl/apb_mem.sv` (+ `uvm/` for the SV flow, `lp/` for low-power) |

## Layout

- `rtl/apb_mem.sv` — the DUT.
- `tb/*.py` — pyuvm testbench (`apb_test.py` is the cocotb module; bfm/components/seq/item).
- `bazel/hdl.bzl` — the two custom test rules + `functional_suite` macro. **Start here**
  before touching how tests are built.
- `bazel/run_*.py` — the per-gate runners; `jsonout.py` writes each test's `result.json`.
- `uvm/*.sv` — SV/UVM flow + bound `apb_sva` assertions; only `//:uvm`, skips w/o a license.
- `lp/` — low-power UPF-emulated variant (`//:lp`). `sim/sim_main.cpp` — coverage harness.
- `BUILD.bazel` — target graph; `check`/`regress`/`ci` map the old make aggregates.

## Conventions

- Every test writes `result.json` to `TEST_UNDECLARED_OUTPUTS_DIR`
  (`bazel-testlogs/<target>/test.outputs/outputs.zip`) and echoes a `[JSON] {...}` log line.
  **Preserve this contract** when adding/altering gates. `--config=json` additionally streams
  the whole invocation to `bazel-events.json` (BEP).
- `COV_MIN=<n> bazel test --test_env=COV_MIN //:coverage` overrides the 100% line-coverage
  floor. `UVM_TEST=<name>` (via `--test_env`) picks the UVM test.
- Only the BFM (`tb/apb_bfm.py`) touches DUT pins; keep pyuvm components simulator-agnostic.

## UVM on open-source Verilator (`uvm/vlt`)

License-free way to run this repo's UVM env under **Verilator 5.050** (no
VCS/Xcelium/Questa), added 2026-08-28. **Passing** in CI
(`.github/workflows/verilator-uvm.yml`; builds Verilator from source + installs
**z3** for `randomize()` + `ccache`; lint + `--binary` `write_read` smoke).

Local (lint RAM-safe; `--binary` wants big-RAM/CI):
```sh
V=~/verilator/bin/verilator ; U=~/verilator/test_regress/t/uvm
( unset VERILATOR_ROOT; make -C uvm/vlt lint   VERILATOR=$V UVM_HOME=$U )
( unset VERILATOR_ROOT; make -C uvm/vlt write_read VERILATOR=$V UVM_HOME=$U )
```
Details: `uvm/vlt/README.md`.

## Agent swarms (repo notes)
The swarm itself is the shared kit described in the block below; this repo's profile is `.claude/swarm.env`
(envs: `sim cocotb uvm`; gate: `make check`; RTL in `rtl/`; no cross-check target). There is no random regression yet:
`RR_STATUS=bootstrap`, so the first Swarm B run builds `make rr-build/rr/rr-triage/rr-replay` under `tb/random/`
(rr-bootstrap skill) and opens a PR for it.

<!-- swarm-kit:begin (managed by markrthomas/dv-swarm-kit sync.sh — edit the kit, not this block) -->
## Agent swarms, run targets and tokens (swarm-kit)

This repo carries the shared **DV swarm kit** (`markrthomas/dv-swarm-kit`, version in `.claude/swarm-kit.version`).
Its repo-specific settings are **`.claude/swarm.env`** (`make swarm-profile` prints them); everything else in the
kit is identical across repos — change it in the kit and re-sync, never fork it here.

- **Swarm A** — end-to-end re-verification: `make swarm` (`docker/swarm-task.md`; swarm-manager + one
  dv-env-tester per `DV_ENVS` entry + infra-agent + dv-runner).
- **Swarm B** — random regression: `make swarm-rr` (`docker/rr-swarm-task.md`; rr-manager + rr-runner / rr-triage /
  rr-debugger / rr-test-author). With `RR_STATUS=bootstrap` it first builds `make rr-build/rr/rr-triage/rr-replay`
  (the `rr-bootstrap` skill), then flips the flag to `present`.
- **Plan-driven swarm** — write `docs/SWARM_PLAN.md` with front-matter `status: ready` and push it to `main`
  (`.github/workflows/plan-swarm.yml` runs `docker/plan-swarm-task.md`; reset to `status: draft` after it lands).
- Model provider: `SWARM_MODEL_PROVIDER=anthropic` (default) or `kimi` (`docker/provider-env.sh`; kimi sends repo
  contents to Moonshot - never for proprietary IP). One-off headless task: `docker/entrypoint.sh agent "<task>"`.
- Status board: `make board`; workers report via `python3 tools/swarm/board.py` (the `board-report` skill).
- Heavy targets (`HEAVY_TARGETS`) run one at a time: `make heavy T=<target>`. Headless Bash is limited to
  `.claude/settings.json`. `make swarm-dry` shows what a swarm run would execute; `make swarm-kit-check` checks drift.

Doctrine (all agents): verify every claim against a real artifact ("no artifact = not verified"); never weaken or skip
a checker to get green; a skip is "not run", not a pass; keep the RTL assertion-free; DUT behaviour changes are the
owner's call (write them up, don't merge them); branches `swarm/<date>-<topic>`; never push to `main`, never force-push.
Return findings as verdict + evidence (file:line / command + 3-10 line excerpt) + next step — no log dumps.

**Where it runs** (same image everywhere: the Dockerfile `tools` stage, plus the repo for `full`):
| where | how | credentials |
|---|---|---|
| GitHub Actions | Actions → **swarm** → Run workflow (task: Swarm A or B) | repo secret `CLAUDE_CODE_OAUTH_TOKEN` |
| Codespaces | open a Codespace (`.devcontainer/`), then `make swarm`, `make swarm-rr` or `make batch` | Codespaces secret `CLAUDE_CODE_OAUTH_TOKEN`; `GITHUB_TOKEN` is injected |
| Railway | batch service built from `railway.toml` (on demand: Redeploy, or a non-docs push); swarm service: start command `docker/entrypoint.sh swarm [--task docker/rr-swarm-task.md]` | service variables `CLAUDE_CODE_OAUTH_TOKEN` (swarm only) and `GITHUB_TOKEN` (fine-grained PAT: this repo, Contents read+write) |

Batch results go to the `metrics-data` branch (`runs/<UTC>-<sha>/`), never to `main`: automatically on Railway
(when `GITHUB_TOKEN` is set), elsewhere only with `PUBLISH_METRICS=1`. Tokens live only in
GitHub/Codespaces/Railway secret stores — never in the repo, the image, a log or a chat.
<!-- swarm-kit:end -->
