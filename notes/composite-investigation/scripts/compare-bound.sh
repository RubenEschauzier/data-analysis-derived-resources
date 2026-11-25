#!/usr/bin/env bash
# P pattern-only, V virtual composites, X + extended blocks, B + bound composites; 3 rounds, 6 queries
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
Q="q16#0 q01#0 q14#0 q06#0 q13#0 q12#0"
for r in 1 2 3; do
  ENGINE_ENV= python3 run_queries.py P-r$r $PO $Q
  ENGINE_ENV= python3 run_queries.py V-r$r $D $Q
  ENGINE_ENV=DERIVED_EXTEND_BLOCKS=1 python3 run_queries.py X-r$r $D $Q
  ENGINE_ENV=DERIVED_EXTEND_BLOCKS=1,DERIVED_BOUND_COMPOSITES=1 python3 run_queries.py B-r$r $D $Q
done
echo DONE
