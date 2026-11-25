#!/usr/bin/env bash
# Rounds 2 and 3 of compare-drain.sh again (the first ones ran under QLever load), without the bound arms.
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
Q="q16#0 q14#0"
for r in 2 3; do
  ENGINE_ENV= python3 run_queries_stream.py DR-pattern-r$r $PO $Q
  ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1 python3 run_queries_stream.py DR-derived-r$r $D $Q
  ENGINE_ENV=DERIVED_FILTER_PUSHDOWN=1,STEMS_DRAIN_COMPOSITES=0 python3 run_queries_stream.py DR-derivedND-r$r $D $Q
done
echo DONE
