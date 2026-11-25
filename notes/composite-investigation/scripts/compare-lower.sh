#!/usr/bin/env bash
# Lowering links into a dataset whose document is still to be handled (priority -1 until handled).
# Labels: LP-<config>-<on|off>-r<n>; config pattern = pattern-only, derived = derived full (FILTER pushdown,
# one-pattern composites left out). "off" sets LINK_LOWER_PENDING_DATASETS=0. 3 rounds, alternating, q16 and q14.
# Lowering's own CPU time is logged in engine-LP-*-on-*.log ([lower] lines, field ms).
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
Q="q16#0 q14#0"
for r in 1 2 3; do
  ENGINE_ENV=LINK_LOWER_PENDING_DATASETS=0 python3 run_queries_stream.py LP-pattern-off-r$r $PO $Q
  ENGINE_LOG=engine-LP-pattern-on-r$r.log ENGINE_ENV=LINK_PRIORITY_DEBUG=1 python3 run_queries_stream.py LP-pattern-on-r$r $PO $Q
  ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1,LINK_LOWER_PENDING_DATASETS=0 python3 run_queries_stream.py LP-derived-off-r$r $D $Q
  ENGINE_LOG=engine-LP-derived-on-r$r.log ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1,LINK_PRIORITY_DEBUG=1 python3 run_queries_stream.py LP-derived-on-r$r $D $Q
done
echo DONE
