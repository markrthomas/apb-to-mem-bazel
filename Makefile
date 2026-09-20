# =============================================================================
# apb-to-mem-bazel — OPTIONAL convenience wrapper.
#
# The canonical interface is Bazel (see README). This Makefile is a thin, opt-in
# shim that maps the familiar `make` verbs from the source uvm_review repo onto
# the equivalent `bazel test` invocations — it does no work of its own.
#
#   BAZEL   bazel/bazelisk launcher (default: bazel)
#   TEST    single functional testcase for test-one (e.g. TEST=random_test)
#   ARGS    extra flags appended to the bazel command (e.g. ARGS=--config=json)
# =============================================================================

BAZEL ?= bazel

.PHONY: default help \
	test test-all cocotb test-write-read test-random test-walking test-one wave \
	lp lint coverage uvm check regress ci sim clean

default: help

help:
	@echo "apb-to-mem-bazel — optional make wrapper (delegates to bazel)"
	@echo ""
	@echo "  Tests (cocotb / pyuvm):"
	@echo "    make test / test-all     # bazel test //:sim  (all three functional tests)"
	@echo "    make cocotb              # alias for test-all (cross-repo DV_STANDARDS.md name)"
	@echo "    make test-write-read     # bazel test //:sim_write_read_test"
	@echo "    make test-random         # bazel test //:sim_random_test"
	@echo "    make test-walking        # bazel test //:sim_walking_test"
	@echo "    make test-one TEST=<name># bazel test //:sim_<name>"
	@echo ""
	@echo "  Waves (FST):"
	@echo "    make wave                # dump + extract waves to waves/ for //:sim_random_test (override TEST=<name>)"
	@echo ""
	@echo "  Other gates:"
	@echo "    make lp                  # bazel test //:lp"
	@echo "    make lint                # bazel test //:lint"
	@echo "    make coverage            # bazel test //:coverage"
	@echo "    make uvm                 # bazel test //:uvm  (skips w/o a UVM sim)"
	@echo ""
	@echo "  Aggregates:"
	@echo "    make check               # bazel test //:check    (lint + functional)"
	@echo "    make regress             # bazel test //:regress  (lint + functional + lp)"
	@echo "    make ci                  # bazel test //:ci       (everything; uvm skips)"
	@echo "    make sim                 # bazel test //... --test_tag_filters=sim"
	@echo ""
	@echo "    make clean               # bazel clean"
	@echo ""
	@echo "  Vars: BAZEL=$(BAZEL)  TEST=<testcase>  ARGS=<extra bazel flags>"

# --- functional --------------------------------------------------------------

test: test-all

test-all:
	$(BAZEL) test //:sim $(ARGS)

# Cross-repo DV_STANDARDS.md alias for the functional/cocotb tier.
cocotb: test-all

test-write-read:
	$(BAZEL) test //:sim_write_read_test $(ARGS)

test-random:
	$(BAZEL) test //:sim_random_test $(ARGS)

test-walking:
	$(BAZEL) test //:sim_walking_test $(ARGS)

test-one:
	@if [ -z "$(TEST)" ]; then echo "usage: make test-one TEST=<testcase>"; exit 2; fi
	$(BAZEL) test //:sim_$(TEST) $(ARGS)

# Dump an FST waveform and extract it to $(WAVE_DIR)/ ready to open. Defaults to
# the random read/write test; override with TEST=<name> (e.g. TEST=walking_test).
# --nocache_test_results forces a fresh run (test-result caching is otherwise on,
# despite the no-cache tag) so the waves reflect the current stimulus.
WAVE_TEST = $(if $(TEST),$(TEST),random_test)
WAVE_DIR ?= waves
wave:
	$(BAZEL) test //:sim_$(WAVE_TEST) --test_arg=--waves --nocache_test_results --test_output=all $(ARGS)
	@mkdir -p $(WAVE_DIR)
	@unzip -o "$$($(BAZEL) info bazel-testlogs)/sim_$(WAVE_TEST)/test.outputs/outputs.zip" '*.fst' -d $(WAVE_DIR) >/dev/null
	@echo ""
	@echo "  Waveform: $$(ls $(WAVE_DIR)/*.fst)"
	@echo "  open with: gtkwave $(WAVE_DIR)/*.fst tb/apb_mem.gtkw"

# --- other gates -------------------------------------------------------------

lp:
	$(BAZEL) test //:lp $(ARGS)

lint:
	$(BAZEL) test //:lint $(ARGS)

coverage:
	$(BAZEL) test //:coverage $(ARGS)

uvm:
	$(BAZEL) test //:uvm $(ARGS)

# --- aggregates --------------------------------------------------------------

check:
	$(BAZEL) test //:check $(ARGS)

regress:
	$(BAZEL) test //:regress $(ARGS)

ci:
	$(BAZEL) test //:ci $(ARGS)

# Tag-filtered selection (the `pytest -m sim` analog).
sim:
	$(BAZEL) test //... --test_tag_filters=sim $(ARGS)

# --- clean -------------------------------------------------------------------

clean:
	$(BAZEL) clean
