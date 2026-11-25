#!/usr/bin/env bash
# Full run on instance 0 (2026-11-25): derived full, pattern-only, and derived full + extended blocks + bound composites
# (combinations 0, 1, 2), all with the same code mounted (additionalBinds in jbr-experiment.json.template): the
# N-Triples fix, the SteMs join with the claim-filter fix (fb70fb3190), and the star-first partition and
# composite-source actors of ce1376f. Combination 2 sets DERIVED_EXTEND_BLOCKS=1 and DERIVED_BOUND_COMPOSITES=1 in its
# Dockerfile. The previous run's outputs are kept in previous-run-2026-11-24/.
# Start detached: setsid nohup ./run-2026-11-25.sh > output/run-2026-11-25.log 2>&1 &
# Progress: output/STATUS. Logs: output/generate-combinations.log, output/prepare-<n>.log, output/run-<n>.log.
set -uo pipefail
cd "$(dirname "$0")"
source ~/.nvm/nvm.sh >/dev/null
mkdir -p output
status() { echo "$(date '+%F %T') $*" | tee -a output/STATUS; }
clean() { sed 's/\x1b\[[0-9;]*m//g' "$1"; }
failed() { [ "$1" -ne 0 ] || clean "$2" | grep -q "Errored"; }

status "start (run of 2026-11-25)"
npx jbr generate-combinations > output/generate-combinations.log 2>&1 || { status "FAILED: generate-combinations"; exit 1; }
for c in 0 1 2; do
  status "preparing combination $c (log: output/prepare-$c.log)"
  npm run jbr -- prepare -c $c > output/prepare-$c.log 2>&1
  failed $? output/prepare-$c.log && { status "FAILED: prepare $c"; exit 1; }
done
# Pattern-only first, then the two derived configurations
for c in 1 0 2; do
  status "running combination $c (log: output/run-$c.log)"
  npm run jbr -- run -c $c > output/run-$c.log 2>&1
  failed $? output/run-$c.log && { status "FAILED: run $c"; exit 1; }
done
status "DONE: results in combinations/combination_{0,1,2}/output (0 = derived full, 1 = pattern-only, 2 = derived full + extended blocks + bound composites)"
