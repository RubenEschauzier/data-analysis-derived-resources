#!/usr/bin/env bash
# Does draining composites first slow the answers through known members, and do bound requests that also carry
# the base operators' values (document-only products) arrive earlier? q16 and q14, 3 rounds, alternating.
# Labels: DR-pattern      = pattern-only
#         DR-derived      = derived full (virtual composites, FILTER pushdown), composites drained (default)
#         DR-derivedND    = the same, STEMS_DRAIN_COMPOSITES=0 (one item per operator per pass)
#         DR-bound        = derived full + extended blocks + bound requests with base-operator values, drained
#         DR-boundND      = the same, not drained
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
Q="q16#0 q14#0"
DER=DERIVED_FILTER_PUSHDOWN=1
BND=$DER,DERIVED_EXTEND_BLOCKS=1,DERIVED_BOUND_COMPOSITES=1,DERIVED_BOUND_BASE_SEEDS=1
for r in 1 2 3; do
  ENGINE_ENV= python3 run_queries_stream.py DR-pattern-r$r $PO $Q
  ENGINE_ENV=$DER python3 run_queries_stream.py DR-derived-r$r $D $Q
  ENGINE_ENV=$DER,STEMS_DRAIN_COMPOSITES=0 python3 run_queries_stream.py DR-derivedND-r$r $D $Q
  ENGINE_ENV=$BND python3 run_queries_stream.py DR-bound-r$r $D $Q
  ENGINE_ENV=$BND,STEMS_DRAIN_COMPOSITES=0 python3 run_queries_stream.py DR-boundND-r$r $D $Q
done
echo DONE
