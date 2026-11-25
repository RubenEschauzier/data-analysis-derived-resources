#!/usr/bin/env bash
# q12 and q16 in P (pattern-only), V (virtual) and B (virtual + extended + bound), 3 rounds each, with the Solid server
# as one process (W1) and with 4 workers (W4). Per-row arrival times via run_queries_stream.py; CPU sampled.
cd "$(dirname "$0")"
export ENGINE_MOUNTS=$(bash mounts.sh)
EXP=~/projects/query-derived-resources/benchmark-experiments/fedshop-discovery-full-experiment
GEN=$EXP/generated
GENIMG=rubeneschauzier/fedshop-discovery-generator@sha256:38166e090500f80a3cc129a959b0ef2072f968c52598adea30b1a778c585b56d
D=jbr-experiment-fedshop-discovery-full-experiment-combination_0-sparql-endpoint-comunica:latest
PO=jbr-experiment-fedshop-discovery-full-experiment-combination_1-sparql-endpoint-comunica:latest
css() {  # extra CSS arguments
  CSS_CMD=$(python3 -c "
import json, shlex; d = json.load(open('$GEN/benchmark/serving.json')); c = d['css_command']
c[c.index('-l') + 1] = 'error'; print(shlex.join(c))")
  WEB=$(python3 -c "import json; print(json.load(open('$GEN/benchmark/serving.json'))['web_dir'])")
  docker rm -f fedshop-css >/dev/null 2>&1
  docker run -d --name fedshop-css --network fedshop-local -v "$GEN/benchmark/web:$WEB:ro" $GENIMG sh -c "exec $CSS_CMD $*" >/dev/null
  for i in $(seq 1 300); do curl -sf localhost:3999/health >/dev/null && { echo "css $* healthy after ${i}s"; return; }; sleep 1; done
  echo "css not healthy"; exit 1
}
: > css-cpu.log
( while true; do echo "$(date +%s) $(docker stats --no-stream --format '{{.Name}}={{.CPUPerc}}' fedshop-css fedshop-engine 2>/dev/null | tr '\n' ' ')"; sleep 2; done ) >> css-cpu.log &
SAMPLER=$!
for W in 1 4; do
  if [ $W = 1 ]; then css; else css -w 4; fi
  echo "phase W$W $(date +%s)" >> css-cpu.log
  for r in 1 2 3; do
    ENGINE_ENV= python3 run_queries_stream.py W$W-P-r$r $PO 'q12#0' 'q16#0'
    ENGINE_ENV= python3 run_queries_stream.py W$W-V-r$r $D 'q12#0' 'q16#0'
    ENGINE_ENV=DERIVED_EXTEND_BLOCKS=1,DERIVED_BOUND_COMPOSITES=1 python3 run_queries_stream.py W$W-B-r$r $D 'q12#0' 'q16#0'
  done
done
kill $SAMPLER
css   # back to one process
echo CSSDONE
