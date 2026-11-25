#!/usr/bin/env bash
# Do one-pattern composite blocks (e.g. ?listing fs:listingOf ?product on its own) delay the known members' answers?
# Labels: SB-pattern = pattern-only; SB-derived = derived full (FILTER pushdown); SB-nosingle = derived full with
# DERIVED_SKIP_SINGLE_BLOCKS=1. 3 rounds, alternating, q16 and q14, SteMs timelines in engine-SB-*.log.
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
Q="q16#0 q14#0"
for r in 1 2 3; do
  ENGINE_LOG=engine-SB-pattern-r$r.log ENGINE_ENV=STEMS_TIMESERIES_LOG=1 python3 run_queries_stream.py SB-pattern-r$r $PO $Q
  ENGINE_LOG=engine-SB-derived-r$r.log ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1,STEMS_TIMESERIES_LOG=1 python3 run_queries_stream.py SB-derived-r$r $D $Q
  ENGINE_LOG=engine-SB-nosingle-r$r.log ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1,DERIVED_SKIP_SINGLE_BLOCKS=1,STEMS_TIMESERIES_LOG=1 python3 run_queries_stream.py SB-nosingle-r$r $D $Q
done
echo DONE
