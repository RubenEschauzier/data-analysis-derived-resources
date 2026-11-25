"""CPU-profile one query: python3 profile_run.py <label> <image> <qid> [split_s]. Profiles land in prof/<label>/:
window 0 = engine start until the query is sent, 1 = the first split_s seconds of the query, 2 = the rest."""
import os, sys, subprocess, threading, time, pathlib, glob, shutil
sys.argv, args = sys.argv[:1], sys.argv[1:]
import run_queries_stream as R
label, image, qid = args[:3]; split = float(args[3]) if len(args) > 3 else 30
HERE = pathlib.Path(__file__).parent
def signal():
    subprocess.run(["docker", "exec", "fedshop-engine", "sh", "-c",
        'for p in $(ls /proc | grep -E "^[0-9]+$"); do tr "\\0" " " < /proc/$p/cmdline 2>/dev/null | grep -q "node" && kill -USR2 $p; done'])
    time.sleep(2)
os.environ["ENGINE_MOUNTS"] = os.environ.get("ENGINE_MOUNTS", "") + f",{HERE}/prof:/prof"
os.environ["ENGINE_ENV"] = ",".join(filter(None, [os.environ.get("ENGINE_ENV", ""), "NODE_OPTIONS=--require /prof/hook.js"]))
for f in glob.glob(str(HERE / "prof" / "*.cpuprofile")): os.remove(f)
R.start_engine(image)
time.sleep(3); signal()
threading.Timer(split, signal).start()
R.run(label, qid)
signal()
out = HERE / "prof" / label; out.mkdir(exist_ok=True)
for f in glob.glob(str(HERE / "prof" / "*.cpuprofile")): shutil.move(f, out / os.path.basename(f))
subprocess.run(["docker", "rm", "-f", "fedshop-engine"], capture_output=True)
print(sorted(os.listdir(out)))
