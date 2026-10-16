# The Kaggle job that produced `results/v2_llm/`

> **Credits:** Paridhi Mittal. Full attribution: CREDITS.md.

`run_sweep.py` is the script kernel that ran the final contract-v2 LLM sweep on
a Kaggle T4 (16 October 2026). It checks the code (`src/agents/nodes.py`) and
the raw data by checksum, restores the saved model replies, runs the tests,
installs Ollama, confirms the model answers on the GPU, runs
`scripts/run_harness.py --tag v2_llm --llm`, and packages the results. Its full
log is `audit/llm_logs/kaggle_notebook_tse-v2-llm-sweep-reviewfix.log`.

To run it again (replace `<kaggle-username>` in both metadata files):

```bash
git -c core.autocrlf=false archive -o dataset/repo_code.zip HEAD
cp data/llm_cache/responses.json dataset/llm_cache_responses.json
cp notebooks/kaggle_v2_llm_sweep/dataset-metadata.json dataset/
kaggle datasets create -p dataset            # private by default
kaggle kernels push -p notebooks/kaggle_v2_llm_sweep --accelerator NvidiaTeslaT4
kaggle kernels output <kaggle-username>/tse-v2-llm-sweep-reviewfix -p out
```

`EXPECT_NODES` in `run_sweep.py` pins the `nodes.py` checksum of the commit
that was run (`113a5393…`); update it when running different code. Use a T4,
not a P100: the Ollama build uses CUDA 13, which no longer supports the P100.
Checking the results needs no GPU: `python scripts/replay_llm_sweep.py`.
