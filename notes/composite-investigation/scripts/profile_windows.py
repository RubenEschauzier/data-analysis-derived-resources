"""CPU-profile one query: python3 profile_windows.py <label> <image> <qid>. Profiles land in
prof/<label>/<pid>-<n>.cpuprofile: n=0 engine start until just before the query, n=1 the query. Each profile carries
startWallMs (hook.js), and prof/<label>/sent.json the wall time (ms) the query was sent, so samples can be binned by
time since the query was sent."""
import os, sys, subprocess, time, pathlib, glob, shutil, json
sys.argv, args = sys.argv[:1], sys.argv[1:]
import run_queries_stream as R
label, image, qid = args[:3]
HERE = pathlib.Path(__file__).parent
def signal():
    subprocess.Popen(["docker", "exec", "fedshop-engine", "sh", "-c",
        'for p in $(ls /proc | grep -E "^[0-9]+$"); do tr "\\0" " " < /proc/$p/cmdline 2>/dev/null | grep -q "node" && kill -USR2 $p; done'])
os.environ["ENGINE_MOUNTS"] = os.environ.get("ENGINE_MOUNTS", "") + f",{HERE}/prof:/prof"
os.environ["ENGINE_ENV"] = ",".join(filter(None, [os.environ.get("ENGINE_ENV", ""), "NODE_OPTIONS=--require /prof/hook.js"]))
for f in glob.glob(str(HERE / "prof" / "*.cpuprofile")): os.remove(f)
R.start_engine(image)
time.sleep(3); signal(); time.sleep(2)
sent = {}
_urlopen = R.urllib.request.urlopen
def urlopen(req, *a, **k):  # note when the query request goes out
    if getattr(req, "full_url", "").endswith("/sparql") and getattr(req, "data", None): sent.setdefault("ms", time.time() * 1000)
    return _urlopen(req, *a, **k)
R.urllib.request.urlopen = urlopen
R.run(label, qid)
signal(); time.sleep(3)
out = HERE / "prof" / label; shutil.rmtree(out, ignore_errors=True); out.mkdir()
for f in glob.glob(str(HERE / "prof" / "*.cpuprofile")): shutil.move(f, out / os.path.basename(f))
(out / "sent.json").write_text(json.dumps(sent))
subprocess.run(["docker", "rm", "-f", "fedshop-engine"], capture_output=True)
print(label, sorted(os.listdir(out)))
