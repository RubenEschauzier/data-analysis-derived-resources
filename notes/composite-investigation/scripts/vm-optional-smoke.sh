#!/usr/bin/env bash
# Smoke test (2026-11-25) of the star / star + hop split of extended blocks (one OPTIONAL request to Virtuoso) with
# the engine fix for nested composites, and of the one-shot rule of bound composites. q12, q13, q14, q16, one round.
# Mounts the compiled lib directories of the SteMs join, the star-first partition actor and the composite-source actor.
cd "$(dirname "$0")"
IMG=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
NM=/var/www/@comunica/query-sparql-link-traversal-solid/node_modules/@comunica
F=$HOME/q13-duplicate/fix
M=$HOME/optional-smoke/mount
export ENGINE_MOUNTS="$F/QuerySourceSparql.js:$NM/actor-query-source-identify-hypermedia-sparql/lib/QuerySourceSparql.js:ro,$F/SparqlEndpointFetcherNTriples.js:$NM/actor-query-source-identify-hypermedia-sparql/lib/SparqlEndpointFetcherNTriples.js:ro,$M/multi-stems:$NM/actor-rdf-join-inner-multi-stems/lib:ro,$M/partition-star-first:$NM/actor-derived-resource-partition-star-first/lib:ro,$M/composite-source:$NM/actor-derived-resource-execute-composite-source/lib:ro"
Q="q12#0 q13#0 q14#0 q16#0"
declare -A ENVS=(
  [extended-split]="DERIVED_BOUND_TRACE=1,DERIVED_EXTEND_BLOCKS=1"
  [bound-rule]="DERIVED_BOUND_TRACE=1,DERIVED_EXTEND_BLOCKS=1,DERIVED_BOUND_COMPOSITES=1"
)
echo "$(date -Is) start" > output/STATUS
bash up.sh >> output/STATUS 2>&1 || { echo "$(date -Is) FAILED: servers" >> output/STATUS; exit 1; }
for c in extended-split bound-rule; do
  echo "$(date -Is) $c" >> output/STATUS
  ENGINE_ENV="${ENVS[$c]}" ENGINE_LOG="engine-$c.log" python3 run_queries_stream.py "$c-r1" "$IMG" $Q >> output/run.log 2>&1
done
docker rm -f fedshop-engine fedshop-proxy fedshop-css fedshop-virtuoso fedshop-virtuoso-known >/dev/null 2>&1
docker network rm fedshop-local >/dev/null 2>&1
echo "$(date -Is) DONE" >> output/STATUS
