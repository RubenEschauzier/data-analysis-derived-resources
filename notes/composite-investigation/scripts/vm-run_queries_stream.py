"""Start one engine image and run query instances through it, as FedShopDiscoveryRunner does: reset the
proxy with the query as label and its known publishers, then send the query with its context. Each raw
response (results plus the engine's statistics) is kept in output/<label>-<query>_<id>.json.

usage: ENGINE_MOUNTS=host:container[,...] ENGINE_ENV=K=V[,...] python run_queries.py <label> <engine-image> <query-id>...
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = Path.home() / "jbr-experiment-fedshop-discovery-instance0"
INSTANCES = {f"{i['name']}#{i['id']}": i for i in json.loads((EXP / "generated/queries/plain.json").read_text())}


def control(path, body=None):
    req = urllib.request.Request(f"http://localhost:3999{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def start_engine(image):
    subprocess.run(["docker", "rm", "-f", "fedshop-engine"], capture_output=True)
    mounts = [a for m in filter(None, os.environ.get("ENGINE_MOUNTS", "").split(",")) for a in ("-v", m)]
    mounts += [a for e in filter(None, os.environ.get("ENGINE_ENV", "").split(",")) for a in ("-e", e)]
    subprocess.run(["docker", "run", "-d", "--name", "fedshop-engine", "--network", "fedshop-local", "--cpus", "1",
                    "-p", "3001:3000", "-v", f"{EXP}/input/context-client.json:/tmp/context.json:ro", *mounts, image],
                   check=True, capture_output=True)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://localhost:3001/sparql", timeout=2)
            return
        except urllib.error.HTTPError:
            return  # it answers
        except Exception:
            time.sleep(1)
    raise RuntimeError("engine did not start")


def run(label, qid):
    inst = INSTANCES[qid]
    query = (EXP / "generated" / inst["queryFile"]).read_text()
    control("/reset", {"label": f"{label}:{qid}", "known": inst.get("known")})
    body = urllib.parse.urlencode({"query": query, "context": json.dumps(inst["context"])}).encode()
    req = urllib.request.Request("http://localhost:3001/sparql", data=body, method="POST", headers={
        "content-type": "application/x-www-form-urlencoded", "accept": "application/sparql-results+json"})
    began = time.time()
    try:
        # Time every binding when its bytes arrive. The serializer writes the ",\n" that ends a row together with
        # the next row, so a row is taken as soon as the unterminated tail of the buffer parses as a binding.
        chunks, timed, buf, tail_taken = [], [], "", False
        def take(text, now):
            text = text.strip().lstrip(",").rstrip(",")
            if text.startswith("{") and not text.startswith('{"head"') and '"type"' in text:
                try:
                    timed.append({"t": now - began, "binding": json.loads(text), "exact": True})
                    return True
                except ValueError:
                    pass
            return False
        with urllib.request.urlopen(req, timeout=240) as resp:
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                now = time.time()
                chunks.append(chunk)
                buf += chunk.decode("utf-8", "replace")
                *lines, buf = buf.split("\n")
                for i, line in enumerate(lines):
                    if i == 0 and tail_taken:
                        tail_taken = False  # taken already while it was the tail
                        continue
                    take(line, now)
                if buf and not tail_taken:
                    tail_taken = take(buf, now)
        raw = b"".join(chunks)
        (HERE / "output" / f"{label}-{qid.replace('#', '_')}.json").write_bytes(raw)
        (HERE / "output" / f"{label}-{qid.replace('#', '_')}.rows.json").write_text(json.dumps(timed))
        status = f"{len(raw)} bytes, {len(timed)} timed rows"
    except Exception as e:
        status = f"failed: {e}"
    elapsed = time.time() - began
    # Wall times of the query, so that engine log lines (the bound-composite trace, in ms) can be assigned to it
    (HERE / "output" / f"{label}-{qid.replace('#', '_')}.meta.json").write_text(json.dumps(
        {"label": label, "query": qid, "began_ms": int(began * 1000), "ended_ms": int((began + elapsed) * 1000)}))
    stats = control("/stats")
    print(f"{label:10} {qid:6} {elapsed:6.1f}s {status} requests={stats['total']['requests']} "
          f"sparql={stats['total']['sparql']}", flush=True)
    time.sleep(3)


if __name__ == "__main__":
    label, image, *qids = sys.argv[1:]
    start_engine(image)
    for qid in qids:
        run(label, qid)
    if os.environ.get("ENGINE_LOG"):
        with open(os.environ["ENGINE_LOG"], "wb") as f:
            f.write(subprocess.run(["docker", "logs", "fedshop-engine"], capture_output=True).stderr)
    subprocess.run(["docker", "rm", "-f", "fedshop-engine"], capture_output=True)
