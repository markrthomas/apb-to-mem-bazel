"""Starlark rules + macros for the APB-mem DV flow under Bazel.

These are the Bazel analog of the pytest repo's test functions. Two custom
rules generate non-hermetic test launchers that shell out to the system Python
(which carries cocotb + pyuvm) and the system Icarus/Verilator — the same
toolchain the pytest flow used. Bazel owns the target graph, runfiles, and the
pass/fail contract; it deliberately does not sandbox the toolchain (targets are
tagged ``local`` + ``no-sandbox``).

  * cocotb_test    — run one @cocotb.test in its own simulation (fresh memory)
  * hdl_tool_test  — run a gate script (lint / coverage / uvm) over some sources

The `functional_suite` macro stamps out one cocotb_test per testcase and groups
them in a test_suite, the way the pytest file parametrizes over the three tests.
"""

DEFAULT_PY = "/usr/bin/python3"

# Non-hermetic HW-sim tests: run locally, no sandbox, and never cache the result
# (the outcome depends on the host toolchain, not just declared inputs).
_SIM_TAGS = ["local", "no-sandbox", "no-cache"]

def _py(ctx):
    """The interpreter token: the `python` attr, overridable at run time via $APB_PYTHON."""
    return '"${APB_PYTHON:-%s}"' % ctx.attr.python

def _launcher(ctx, argv):
    """Write an executable bash launcher that execs `argv` (a list of shell words)."""
    out = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(
        output = out,
        is_executable = True,
        content = "#!/usr/bin/env bash\nset -euo pipefail\nexec {}\n".format(
            " ".join(argv),
        ),
    )
    return out

def _cocotb_test_impl(ctx):
    argv = [
        _py(ctx),
        "'%s'" % ctx.file.runner.short_path,
        "--toplevel", "'%s'" % ctx.attr.toplevel,
        "--module", "'%s'" % ctx.attr.module,
        "--module-dir", "'%s'" % ctx.attr.module_dir,
        "--testcase", "'%s'" % ctx.attr.testcase,
    ]
    for src in ctx.files.sources:
        argv += ["--source", "'%s'" % src.short_path]
    for d in ctx.attr.defines:
        argv += ["--define", "'%s'" % d]
    argv.append('"$@"')  # forward `--test_arg=...` (e.g. --waves) to the runner

    launcher = _launcher(ctx, argv)
    runfiles = ctx.runfiles(
        files = [ctx.file.runner, ctx.file._jsonout] +
                ctx.files.sources + ctx.files.module_srcs,
    )
    return [DefaultInfo(executable = launcher, runfiles = runfiles)]

cocotb_test = rule(
    implementation = _cocotb_test_impl,
    test = True,
    doc = "Run a single cocotb testcase under Icarus (one sim = fresh memory).",
    attrs = {
        "toplevel": attr.string(mandatory = True, doc = "HDL top module"),
        "module": attr.string(mandatory = True, doc = "cocotb test module (e.g. apb_test)"),
        "module_dir": attr.string(mandatory = True, doc = "runfiles dir holding the module"),
        "testcase": attr.string(mandatory = True, doc = "the @cocotb.test name"),
        "sources": attr.label_list(allow_files = [".sv", ".v"], doc = "Verilog DUT sources"),
        "module_srcs": attr.label_list(allow_files = [".py"], doc = "testbench python files"),
        "defines": attr.string_list(doc = "Verilog defines, 'K' or 'K=V'"),
        "runner": attr.label(
            default = Label("//bazel:run_cocotb.py"),
            allow_single_file = True,
        ),
        "_jsonout": attr.label(
            default = Label("//bazel:jsonout.py"),
            allow_single_file = True,
        ),
        "python": attr.string(default = DEFAULT_PY),
    },
)

def _hdl_tool_test_impl(ctx):
    argv = [_py(ctx), "'%s'" % ctx.file.script.short_path]
    for src in ctx.files.sources:
        argv.append("'%s'" % src.short_path)
    for a in ctx.attr.extra_args:
        argv.append("'%s'" % a)
    argv.append('"$@"')

    launcher = _launcher(ctx, argv)
    runfiles = ctx.runfiles(
        files = [ctx.file.script, ctx.file._jsonout] + ctx.files.sources + ctx.files.data,
    )
    return [DefaultInfo(executable = launcher, runfiles = runfiles)]

hdl_tool_test = rule(
    implementation = _hdl_tool_test_impl,
    test = True,
    doc = "Run a gate script (lint/coverage/uvm) with sources passed positionally.",
    attrs = {
        "script": attr.label(mandatory = True, allow_single_file = [".py"]),
        "sources": attr.label_list(allow_files = True, doc = "positional args to the script"),
        "data": attr.label_list(allow_files = True, doc = "extra runfiles the script needs"),
        "extra_args": attr.string_list(doc = "literal args appended after sources"),
        "_jsonout": attr.label(
            default = Label("//bazel:jsonout.py"),
            allow_single_file = True,
        ),
        "python": attr.string(default = DEFAULT_PY),
    },
)

def functional_suite(name, testcases, toplevel, module, module_dir, sources, module_srcs):
    """One cocotb_test per testcase + a test_suite grouping them (marker: sim)."""
    tests = []
    for tc in testcases:
        tname = "sim_" + tc
        cocotb_test(
            name = tname,
            toplevel = toplevel,
            module = module,
            module_dir = module_dir,
            testcase = tc,
            sources = sources,
            module_srcs = module_srcs,
            tags = _SIM_TAGS + ["sim"],
            size = "medium",
        )
        tests.append(":" + tname)
    native.test_suite(name = name, tests = tests, tags = ["sim"])

# Re-exported so BUILD files can tag the single-target gates consistently.
SIM_TAGS = _SIM_TAGS
