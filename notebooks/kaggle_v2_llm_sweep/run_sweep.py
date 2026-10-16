# Credits: Paridhi Mittal. Full attribution: CREDITS.md.
# v2 LLM sweep with the I3 review fix (commit 98c741e), resuming from saved replies.
# Everything is logged to stdout; outputs land in /kaggle/working.
import glob, hashlib, json, os, shutil, subprocess, sys, time, zipfile

WORK = "/kaggle/working"
REPO = f"{WORK}/repo"
MODEL = "qwen2.5:3b-instruct-q4_K_M"
EXPECT_NODES = "113a5393a3e21d92"
EXPECT_RAW = "9e81698322606c86"


def sh(cmd, check=True):
    print(f"\n$ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    print(r.stdout[-4000:], flush=True)
    if check and r.returncode != 0:
        sys.exit(f"FAILED ({r.returncode}): {cmd}")
    return r.stdout


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


sh("nvidia-smi --query-gpu=name,memory.total --format=csv")

# 1. Code: the dataset may hold the zip or its extracted contents.
os.makedirs(REPO, exist_ok=True)
runner = glob.glob("/kaggle/input/**/scripts/run_harness.py", recursive=True)
if runner:
    shutil.copytree(os.path.dirname(os.path.dirname(runner[0])), REPO, dirs_exist_ok=True)
else:
    zipfile.ZipFile(glob.glob("/kaggle/input/**/repo_code.zip", recursive=True)[0]).extractall(REPO)
os.chdir(REPO)
nodes = sha("src/agents/nodes.py")[:16]
raw = sha("data/raw/hyderabad.csv")[:16]
print("nodes.py", nodes, "| raw data", raw, flush=True)
if nodes != EXPECT_NODES or raw != EXPECT_RAW:
    sys.exit("code or data is not the expected version")

# 2. Saved replies from the first sweep.
cache = glob.glob("/kaggle/input/**/llm_cache_responses.json", recursive=True)[0]
shutil.copy(cache, "data/llm_cache/responses.json")
print("saved replies:", len(json.load(open("data/llm_cache/responses.json"))), flush=True)

# 3. Python deps and tests.
sh("pip install -q -r requirements.txt")
sh("python -m pytest -q -p no:cacheprovider 2>&1 | tail -3")

# 4. Ollama on the GPU.
sh("apt-get install -y -qq zstd lshw > /dev/null", check=False)
sh("curl -fsSL https://ollama.com/install.sh | sh")
subprocess.Popen(["ollama", "serve"], stdout=open(f"{WORK}/ollama.log", "w"),
                 stderr=subprocess.STDOUT, start_new_session=True)
time.sleep(10)
sh(f"ollama pull {MODEL} 2>&1 | tail -2")
sh("ollama list")
sh(f"""curl -s localhost:11434/api/generate -d '{{"model":"{MODEL}","prompt":"Say OK","stream":false,"options":{{"temperature":0,"seed":11}}}}' | head -c 200""")
sh("ollama ps")

# 5. The sweep. It stops itself if Ollama stops answering.
started = time.time()
with open(f"{WORK}/harness.log", "w") as log:
    code = subprocess.call(
        [sys.executable, "-u", "scripts/run_harness.py", "--tag", "v2_llm", "--llm"],
        stdout=log, stderr=subprocess.STDOUT)
print(f"harness exit code {code} after {time.time() - started:.0f}s", flush=True)
print(open(f"{WORK}/harness.log").read()[-6000:], flush=True)
sh("grep -c 'POST' /kaggle/working/ollama.log", check=False)
# The server log runs to hundreds of MB; keep only the request lines.
sh("grep '\\[GIN\\]' /kaggle/working/ollama.log > /kaggle/working/ollama_requests.log; "
   "rm /kaggle/working/ollama.log", check=False)

# 6. Package the outputs.
with zipfile.ZipFile(f"{WORK}/v2_llm_out.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for path in glob.glob("results/v2_llm/*") + ["data/llm_cache/responses.json"]:
        z.write(path)
shutil.rmtree(REPO)                     # keep the Output tab small
if code != 0:
    sys.exit(f"harness failed with exit code {code}")
print("DONE", flush=True)
