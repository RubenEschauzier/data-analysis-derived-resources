#!/usr/bin/env bash
# P pattern-only vs D derived (virtual composites) with FILTER pushdown; both with the CPU fixes mounted.
# 6 queries, 4 rounds, alternating; per-row arrival times via run_queries_stream.py.
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
Q="q16#0 q01#0 q14#0 q06#0 q13#0 q12#0"
for r in 1 2 3 4; do
  ENGINE_ENV= python3 run_queries_stream.py FP-P-r$r $PO $Q
  ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1 python3 run_queries_stream.py FP-D-r$r $D $Q
done
echo DONE
