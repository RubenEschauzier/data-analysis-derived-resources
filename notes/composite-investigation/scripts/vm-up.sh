#!/usr/bin/env bash
# Serve the instance-0 copy's generated benchmark by hand (as ExperimentFedShopDiscovery.run does), with the
# new proxy (generator:dev) writing its request log. Reuses the Virtuoso volumes loaded for that experiment.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
EXP=~/jbr-experiment-fedshop-discovery-instance0
GEN=$EXP/generated
NET=fedshop-local
VOL=fedshop-discovery-597731afcb
VIRT=openlink/virtuoso-opensource-7@sha256:2c7453b3e401bca274f46972117a18cf1965c6b30afb9b8c86cb4340c0c9ba70
GENIMG=rubeneschauzier/fedshop-discovery-generator:dev
mkdir -p "$HERE/output"

docker rm -f fedshop-engine fedshop-proxy fedshop-css fedshop-virtuoso fedshop-virtuoso-known >/dev/null 2>&1 || true
docker network rm $NET >/dev/null 2>&1 || true
docker network create $NET >/dev/null

reserved() {  # the service listener ports of a load script, as ExperimentFedShopDiscovery.reservedPorts
  python3 - "$1" <<'EOF'
import re, sys
ports = sorted({int(p) for p in re.findall(r"lhost\s*=>\s*':(\d+)'", open(sys.argv[1]).read())})
ranges, i = [], 0
while i < len(ports):
    j = i
    while j + 1 < len(ports) and ports[j + 1] == ports[j] + 1:
        j += 1
    ranges.append(f"{ports[i]}-{ports[j]}" if j > i else str(ports[i]))
    i = j + 1
print(",".join(ranges))
EOF
}

virtuoso() {  # name buffers volume-suffix
  local which=$3 buffers=$2
  docker run -d --name "$1" --network $NET -v "$VOL-$which:/database" \
    --sysctl "net.ipv4.ip_local_reserved_ports=$(reserved "$GEN/benchmark/virtuoso/$which/load.sql")" \
    -e SPARQL_UPDATE=false -e DBA_PASSWORD=dba -e VIRT_HTTPServer_ServerPort=8890 \
    -e VIRT_HTTPServer_ServerThreads=64 -e VIRT_HTTPServer_MaxClientConnections=64 \
    -e VIRT_HTTPServer_MaxKeepAlives=64 -e VIRT_HTTPServer_KeepAliveTimeout=30 \
    -e VIRT_SPARQL_MaxQueryCostEstimationTime=0 -e VIRT_SPARQL_ResultSetMaxRows=0 \
    -e VIRT_SPARQL_MaxQueryExecutionTime=0 -e VIRT_SPARQL_MaxConstructTriples=2097150 \
    -e VIRT_Parameters_MaxQueryMem=2G -e VIRT_Parameters_ServerThreads=100 \
    -e VIRT_Parameters_MaxClientConnections=100 -e VIRT_Parameters_CheckpointInterval=0 \
    -e VIRT_Parameters_DefaultIsolation=1 \
    -e "VIRT_Parameters_NumberOfBuffers=$buffers" -e "VIRT_Parameters_MaxDirtyBuffers=$((buffers * 3 / 4))" \
    $VIRT >/dev/null
}
virtuoso fedshop-virtuoso 340000 main
virtuoso fedshop-virtuoso-known 85000 known

CSS_CMD=$(python3 -c "
import json, shlex; d = json.load(open('$GEN/benchmark/serving.json')); c = d['css_command']
c[c.index('-l') + 1] = 'error'; print(shlex.join(c))")
WEB=$(python3 -c "import json; print(json.load(open('$GEN/benchmark/serving.json'))['web_dir'])")
docker run -d --name fedshop-css --network $NET -v "$GEN/benchmark/web:$WEB:ro" $GENIMG sh -c "exec $CSS_CMD" >/dev/null

python3 -c "
import json; d = json.load(open('$GEN/benchmark/serving.json'))
m = d['proxy_map']; m['monitor']['components'] = []
json.dump(m, open('$HERE/proxy-run.json', 'w'))"
# Reserve the proxy's own service ports (34300-34439), so an outgoing connection it opens while still binding
# them cannot take one (EADDRINUSE on 2026-11-24)
docker run -d --name fedshop-proxy --network $NET -p 3999:3999 \
  --sysctl net.ipv4.ip_local_reserved_ports=34300-34439 \
  -v "$HERE/proxy-run.json:/generated/proxy-run.json:ro" -v "$HERE/output:/output" \
  $GENIMG node /fedshop/experiments/bsbm/discovery/tools/proxy/proxy.js /generated/proxy-run.json /output/proxy-requests.jsonl >/dev/null

for i in $(seq 1 600); do
  if curl -sf localhost:3999/health >/dev/null; then echo "servers healthy after ${i}s"; exit 0; fi
  sleep 1
done
echo "servers not healthy:"; curl -s localhost:3999/health; exit 1
