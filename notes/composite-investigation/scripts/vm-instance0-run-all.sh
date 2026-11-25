#!/usr/bin/env bash
# Runs every step of this experiment copy, unattended: pull the newest engine and generator images, generate the
# combinations, prepare (data, documents, Virtuoso, client images), and run. Start it detached so it survives logout:
#   setsid nohup ./run-all.sh > output/run-all.log 2>&1 &
# Progress, one line per step with a timestamp: output/STATUS. Logs: output/prepare.log, output/run.log.
# A `jbr prepare` that is already running is waited for rather than started again; a prepare that has already
# succeeded (output/prepare.ok) is not repeated. Stops at the first failing step.
set -uo pipefail
cd "$(dirname "$0")"
source ~/.nvm/nvm.sh >/dev/null
mkdir -p output
status() { echo "$(date '+%F %T') $*" | tee -a output/STATUS; }
clean() { sed 's/\x1b\[[0-9;]*m//g' "$1"; }

status "start"

if pgrep -f "jbr prepare" >/dev/null; then
  status "a jbr prepare is already running: waiting for it (log: output/prepare.log)"
  while pgrep -f "jbr prepare" >/dev/null; do sleep 60; done
  if clean output/prepare.log | grep -q "Errored"; then
    status "FAILED: prepare (see output/prepare.log)"; exit 1
  fi
  touch output/prepare.ok
  status "prepare done"
elif [ ! -f output/prepare.ok ]; then
  status "pulling images"
  docker pull -q rubeneschauzier/comunica-query-sparql-link-traversal-solid-derived-resources:dev || { status "FAILED: pull engine"; exit 1; }
  docker pull -q rubeneschauzier/fedshop-discovery-generator:dev || { status "FAILED: pull generator"; exit 1; }
  status "generating combinations"
  npx jbr generate-combinations > output/generate-combinations.log 2>&1 || { status "FAILED: generate-combinations"; exit 1; }
  status "preparing (log: output/prepare.log)"
  npm run jbr -- prepare > output/prepare.log 2>&1
  if [ $? -ne 0 ] || clean output/prepare.log | grep -q "Errored"; then
    status "FAILED: prepare (see output/prepare.log)"; exit 1
  fi
  touch output/prepare.ok
  status "prepare done"
else
  status "prepare already done (output/prepare.ok), skipping"
fi

status "running all combinations (log: output/run.log)"
npm run jbr -- run > output/run.log 2>&1
if [ $? -ne 0 ] || clean output/run.log | grep -q "Errored"; then
  status "FAILED: run (see output/run.log)"; exit 1
fi
status "DONE: results in combinations/combination_*/output (0 = derived full, 1 = pattern-only)"
