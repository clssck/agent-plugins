# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

.PHONY: zip wc update-models validate-models fetch-capabilities test test-unit test-e2e copy copy-clean dev-gepa-ui build-sec-data benchmark-submit benchmark-run-local benchmark-status benchmark-report benchmark-html benchmark-setup-notify

DATE := $(shell date +%Y-%m-%d)
GIT_HASH := $(shell git rev-parse --short HEAD)
ZIP_NAME := cortex-ai-function-studio-$(DATE)-$(GIT_HASH).zip
GEPA_UI_PORT ?= 8000

zip:
	cd .. && git -C cortex-ai-function-studio ls-files | grep -v '^tests/' | grep -v '^dev/' | sed 's|^|cortex-ai-function-studio/|' | zip ../$(ZIP_NAME) -@
	@echo "Created ../$(ZIP_NAME)"

wc:
	@find . -name '*.md' -not -path './.venv/*' | sort | xargs wc -l

# Usage: make test CONNECTION=snowhouse
#        make test-unit
#        make test-e2e CONNECTION=snowhouse
CONNECTION ?= snowhouse
FETCH_CONNECTION ?= snowhouse

# Fetch latest model prices from Snowhouse, validate each with AI_COMPLETE,
# and write only passing models to src/models.json.
# Requires: SNOWHOUSE connection for fetching prices,
#           CONNECTION (default: snowhouse) for AI_COMPLETE validation.
# Usage: make update-models
#        make update-models FETCH_CONNECTION=SNOWHOUSE CONNECTION=snowhouse
#        make update-models NO_PRUNE=1
update-models:
	@python dev/models/validate_models.py \
		--fetch-connection $(FETCH_CONNECTION) \
		--validate-connection $(CONNECTION) \
		$(if $(NO_PRUNE),--no-prune,)

# Validate models already in src/models.json without re-fetching from Snowhouse.
# Usage: make validate-models
#        make validate-models CONNECTION=snowhouse NO_PRUNE=1
validate-models:
	@python dev/models/validate_models.py \
		--validate-only \
		--validate-connection $(CONNECTION) \
		$(if $(NO_PRUNE),--no-prune,)

# Fetch multimodal capabilities from corvo-config and write src/model_capabilities.json.
# Requires: gh CLI authenticated with access to snowflake-eng/corvo-config.
# Usage: make fetch-capabilities
fetch-capabilities:
	@GH_TOKEN=$$(gh auth token) python dev/models/fetch_capabilities.py

test:
	uv run --group test pytest tests/ -v --connection $(CONNECTION)

test-unit:
	uv run --group test pytest tests/ -v -m "not e2e"

test-e2e:
	uv run --group test pytest tests/ -v -m "e2e" --connection $(CONNECTION)

# Build the SEC 10-K PDF dataset for the pdf-field-extraction demo.
# One-time developer step — deps are auto-installed by the script.
# Usage: make build-sec-data
#        make build-sec-data MAX_FILINGS=40
MAX_FILINGS ?= 80

build-sec-data:
	python demos/pdf-field-extraction/build_dataset.py --max-filings $(MAX_FILINGS)

# Copy skill folder to destination using only git-tracked files, minus .skillignore
# Usage: make copy COPY_DEST=/path/to/destination
copy:
ifndef COPY_DEST
	$(error COPY_DEST is required. Usage: make copy COPY_DEST=/path/to/destination)
endif
	@mkdir -p $(COPY_DEST)
	git archive HEAD -- . $$(grep -v '^\#' .skillignore | grep -v '^$$' | sed 's|^|:!|') \
		| tar -x -C $(COPY_DEST)
	@echo "Copied to $(COPY_DEST)"

# Copy deployable skill contents only, excluding tests/dev/framework/deps via .skillignore.
# Usage: make copy-clean
#        make copy-clean COPY_DEST=/path/to/cortex-ai-function-studio-clean
COPY_DEST ?= /tmp/cortex-ai-function-studio-clean
COPY_SCRIPT := dev/scripts/copy-skill-clean.py

copy-clean:
	python $(COPY_SCRIPT) . $(COPY_DEST) --force

dev-gepa-ui:
	@cd dev/gepa-progress && python3 -m http.server $(GEPA_UI_PORT)

# Benchmark — submit / poll status / render report against the
# BENCHMARK_GEPA Snowflake stored procedure.  See
# dev/benchmark/README.md for the architecture and CLI reference.
# All targets respect CONNECTION (default: snowhouse).
#
# Usage:
#   make benchmark-submit
#   make benchmark-submit SCENARIOS="sentiment,spam_detection" BUDGET=heavy PARALLELISM=2
#   make benchmark-submit BLOCK=1 JSON=1 PARALLELISM=2
#   make benchmark-submit THROUGHPUT_BENCH=1
#   make benchmark-submit THROUGHPUT_ONLY=1           # probe only, skip GEPA
#   make benchmark-run-local THROUGHPUT_ONLY=1        # ditto, in-process
#   make benchmark-submit NOTIFY=kschmaus@snowflake.com
#
#   make benchmark-status TASK=DB.SCHEMA.BENCH_TASK_<ts>
#
#   make benchmark-report
#   make benchmark-report RUN=DB.SCHEMA.BENCH_TASK_<ts>
SCENARIOS ?=
MODES ?=
PARALLELISM ?= 2
POLL_INTERVAL ?= 30
TIMEOUT_MINUTES ?= 480
BENCH_NAME ?= -1
BUDGET ?=
NOTIFY ?=

BENCH_CLI := uv run --group dev python -m snowflake_ai_optimize.bench.cli

# Hydra parses `[a b]` as a one-element list with the literal "a b" — users
# typically supply THROUGHPUT_MODELS as a space-separated string (matches the
# Makefile help text), so translate spaces → commas before splicing into the
# bracketed list literal.
empty :=
space := $(empty) $(empty)
comma := ,
THROUGHPUT_MODELS_LIST := $(subst $(space),$(comma),$(strip $(THROUGHPUT_MODELS)))

benchmark-submit:
	@$(BENCH_CLI) submit \
	  connection=$(CONNECTION) \
	  parallelism=$(PARALLELISM) \
	  timeout_minutes=$(TIMEOUT_MINUTES) \
	  poll_interval=$(POLL_INTERVAL) \
	  $(if $(SCENARIOS),scenario=$(SCENARIOS),) \
	  $(if $(BUDGET),budget=$(BUDGET),) \
	  $(if $(NOTIFY),notify=$(NOTIFY),) \
	  $(if $(BLOCK),block=true,) \
	  $(if $(JSON),json_output=true,) \
	  $(if $(THROUGHPUT_BENCH),throughput_bench=true,) \
	  $(if $(THROUGHPUT_ONLY),throughput_only=true,) \
    $(if $(THROUGHPUT_MODELS),throughput_models='[$(THROUGHPUT_MODELS_LIST)]',)

benchmark-run-local:
	@$(BENCH_CLI) run-local \
    connection=$(CONNECTION) \
    parallelism=$(PARALLELISM) \
    $(if $(SCENARIOS),scenario=$(SCENARIOS),) \
    $(if $(BUDGET),budget=$(BUDGET),) \
    $(if $(NOTIFY),notify=$(NOTIFY),) \
    $(if $(THROUGHPUT_BENCH),throughput_bench=true,) \
    $(if $(THROUGHPUT_ONLY),throughput_only=true,) \
    $(if $(THROUGHPUT_MODELS),throughput_models='[$(THROUGHPUT_MODELS_LIST)]',) \
    $(if $(MODES),modes=$(MODES),) \
    $(if $(SKIP_DEPLOY),skip_deploy=true,)

benchmark-status:
ifndef TASK
	$(error TASK is required. Usage: make benchmark-status TASK=DB.SCHEMA.BENCH_TASK_<ts>)
endif
	@$(BENCH_CLI) status \
	  connection=$(CONNECTION) \
	  task=$(TASK)

benchmark-report:
	@$(BENCH_CLI) report \
	  connection=$(CONNECTION) \
	  $(if $(RUN),run=$(RUN),)

# Fetch results + open a self-contained HTML report in the default browser.
# Passes html=true to bench report which renders the rich HTML page (Gantt
# timeline, per-iteration tracking table, CocoEvolve detail panel, Pareto
# plot) and opens it in the default browser.  Set HTML_OUTPUT=path to write
# to a file instead of opening the browser (headless / CI mode).
#
# Usage:
#   make benchmark-html CONNECTION=sfctest-udaif-bench
#   make benchmark-html CONNECTION=sfctest-udaif-bench RUN=DB.SCHEMA.BENCH_TASK_<ts>
#   make benchmark-html CONNECTION=sfctest-udaif-bench HTML_OUTPUT=report.html
HTML_OUTPUT ?=
benchmark-html:
	@$(BENCH_CLI) report \
	  connection=$(CONNECTION) \
	  $(if $(RUN),run=$(RUN),) \
	  html=true \
	  $(if $(HTML_OUTPUT),html_output=$(HTML_OUTPUT),)

# One-time per-developer setup: creates a BENCH_NOTIFY_<YOU> integration so
# `bench submit notify=you@snowflake.com` delivers email on completion/failure.
# Usage: make benchmark-setup-notify NOTIFY=you@snowflake.com
benchmark-setup-notify:
ifndef NOTIFY
	$(error NOTIFY is required. Usage: make benchmark-setup-notify NOTIFY=you@snowflake.com)
endif
	@$(BENCH_CLI) setup-notify \
	  connection=$(CONNECTION) \
	  notify=$(NOTIFY)
