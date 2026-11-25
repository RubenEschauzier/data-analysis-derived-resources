#!/usr/bin/env bash
# Bound composites on the VM's instance-0 data (2026-11-25): derived full, + extended blocks, + bound composites
# seeded from every constant ('all'), + bound composites seeded only one-shot ('one-shot'). q12, q13, q14, q16;
# 3 rounds, configuration order rotated per round. Every configuration runs the derived-full image with the new
# composite-source actor and the N-Triples fix mounted, and writes the bound trace (DERIVED_BOUND_TRACE=1).
# Output: output/<config>-r<n>-<query>.{json,rows.json,meta.json}, engine-<config>-r<n>.log (the trace).
cd "$(dirname "$0")"
IMG=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
NM=/var/www/@comunica/query-sparql-link-traversal-solid/node_modules/@comunica
F=$HOME/q13-duplicate/fix
B=$HOME/bound-experiment/mount
export ENGINE_MOUNTS="$F/QuerySourceSparql.js:$NM/actor-query-source-identify-hypermedia-sparql/lib/QuerySourceSparql.js:ro,$F/SparqlEndpointFetcherNTriples.js:$NM/actor-query-source-identify-hypermedia-sparql/lib/SparqlEndpointFetcherNTriples.js:ro,$B/ActorDerivedResourceExecuteCompositeSource.js:$NM/actor-derived-resource-execute-composite-source/lib/ActorDerivedResourceExecuteCompositeSource.js:ro,$B/BoundCompositeCoordinator.js:$NM/actor-derived-resource-execute-composite-source/lib/BoundCompositeCoordinator.js:ro"
Q="q12#0 q13#0 q14#0 q16#0"
declare -A ENVS=(
  [derived]="DERIVED_BOUND_TRACE=1"
  [extended]="DERIVED_BOUND_TRACE=1,DERIVED_EXTEND_BLOCKS=1"
  [bound-all]="DERIVED_BOUND_TRACE=1,DERIVED_EXTEND_BLOCKS=1,DERIVED_BOUND_COMPOSITES=1,DERIVED_BOUND_POLICY=all"
  [bound-oneshot]="DERIVED_BOUND_TRACE=1,DERIVED_EXTEND_BLOCKS=1,DERIVED_BOUND_COMPOSITES=1,DERIVED_BOUND_POLICY=one-shot"
)
ORDER=(derived extended bound-all bound-oneshot)
echo "$(date -Is) start" > output/STATUS
bash up.sh >> output/STATUS 2>&1 || { echo "$(date -Is) FAILED: servers" >> output/STATUS; exit 1; }
for r in 1 2 3; do
  for i in 0 1 2 3; do
    c=${ORDER[$(( (i + r - 1) % 4 ))]}
    echo "$(date -Is) round $r $c" >> output/STATUS
    ENGINE_ENV="${ENVS[$c]}" ENGINE_LOG="engine-$c-r$r.log" python3 run_queries_stream.py "$c-r$r" "$IMG" $Q >> output/run.log 2>&1
  done
done
docker rm -f fedshop-engine fedshop-proxy fedshop-css fedshop-virtuoso fedshop-virtuoso-known >/dev/null 2>&1
docker network rm fedshop-local >/dev/null 2>&1
echo "$(date -Is) DONE" >> output/STATUS
