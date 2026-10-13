# Qwen3-14B BASE on Intelion RTX 3090: one-command DEV run

> **ИСТОРИЧЕСКИЙ RUNBOOK, ТОЛЬКО BASE-инференс!** Владелец 14.10.2026 утвердил новую цепочку **BASE → 14B QLoRA E1/E2 → DEV**, см. [training/EXPERIMENT_14B_5H.md](../training/EXPERIMENT_14B_5H.md) и `bash training/start_14b_epochs.sh`. Не запускать одновременно/вместо нового пайплайна `evaluation/start_14b.sh`: он останавливает сервер после одного baseline.


**First experiment after successful 8B QLoRA V1.** This is INFERENCE ONLY. We do not yet train 14B and do not open TEST_A or TEST_B.

## What already exists on Intelion server 11425

- CUDA RTX 3090 / 24 GiB, `/root/peregovori/.venv` already installed.
- `training/outputs/qlora_v1_bundle.tar.gz` and matching SHA256.
- `eval_private/dev/cases.jsonl` (25 private frozen cases) and `probes.jsonl` (75 private probes).
- `eval_private/results/dev/base.jsonl`, `lora.jsonl`, `run_config.json` from 8B vs 8B+QLoRA.
- Saved Intelion cloud API token in home config, outside public Git.
- Intelion auto-renewal **must be disabled** (was disabled previously; confirm in provider panel). Server ID 11425, not a newly created VM.

**No private cases, oracles, credentials or model weights go into public GitHub.** The model Qwen/Qwen3-14B loads from Hugging Face into VM cache.

## Run in the SSH terminal on the EXISTING Intelion VM

Enable/fund and start **same** Intelion server ID 11425, not a new VM. Count the billing time from instance start. Then:

```bash
ssh root@YOUR_CURRENT_INTELION_IP
cd /root/peregovori
git pull --ff-only
bash evaluation/start_14b.sh
```

The SSH command is executed on your Mac; the rest on the VM. Already in SSH? Only run the final three lines.

**One-command launcher performs:**
1. Confirms adapter integrity and frozen DEV input matches existing 8B reference by SHA-256.
2. Confirms old 8B BASE + QLoRA have all 75 replies under exactly the same decode configuration.
3. Detects a running Intelion watchdog; otherwise archives a stale deadline file and arms a NEW 80-minute **in-VM** API stop timer.
4. Launches 14B in detached `tmux qwen14b-dev`, loading **only Qwen3-14B BASE**, NF4/4-bit, non-thinking, 192 tokens, greedy decoding to match past 8B runs.
5. Runs 75 DEV probes and creates blind 3-way review A/B/C (8B base, 8B QLoRA V1, 14B base).
6. Writes partial responses each turn, final status and SHA256 archive, then requests provider stop in a `finally` block. Watchdog backup remains armed.

**No model comparisons using TEST_A / TEST_B until a candidate is selected.**

## Monitoring

```bash
cd ~/peregovori
tail -f eval_private/results/qwen3_14b_base/pipeline.log
```

Ctrl+C leaves detached tmux job running. Another terminal:

```bash
tmux ls
python training/intelion_autostop.py status
```

Expected final artifacts ON SERVER (not automatically on Mac):

```text
eval_private/qwen3_14b_dev_outputs.tar.gz
eval_private/qwen3_14b_dev_outputs.tar.gz.sha256
eval_private/results/qwen3_14b_base/pipeline.log
eval_private/results/qwen3_14b_base/final_status.json
eval_private/results/qwen3_14b_base/base.jsonl
eval_private/results/qwen3_14b_base/three_way_blind_review.csv
eval_private/results/qwen3_14b_base/three_way_blind_key_PRIVATE.json
eval_private/results/qwen3_14b_base/three_way_summary.json
```

When the VM stops, archive remains on attached disk if Intelion retains the disk. It is **not yet on your Mac**.

### SCP download to Mac

If instance already auto-stopped, briefly restart **same** server to allow SSH; count its billed time; do not re-run inference. On Mac, use CURRENT provider IP:

```bash
mkdir -p ~/Downloads/peregovori_14b_dev
scp root@YOUR_CURRENT_INTELION_IP:/root/peregovori/eval_private/qwen3_14b_dev_outputs.tar.gz \
    root@YOUR_CURRENT_INTELION_IP:/root/peregovori/eval_private/qwen3_14b_dev_outputs.tar.gz.sha256 \
    root@YOUR_CURRENT_INTELION_IP:/root/peregovori/eval_private/results/qwen3_14b_base/pipeline.log \
    ~/Downloads/peregovori_14b_dev/
cd ~/Downloads/peregovori_14b_dev
shasum -a 256 -c qwen3_14b_dev_outputs.tar.gz.sha256
```

Expect `qwen3_14b_dev_outputs.tar.gz: OK`. Then manually stop instance through Intelion dashboard or known API stop command, and verify stopped state.

```bash
cd ~/peregovori && source .venv/bin/activate
python training/intelion_autostop.py stop --server-id 11425
```

**Do not run 14B again simply to download**. Beware changing host SSH keys: verify remote fingerprint out of band before replacing known_hosts entries.

## Why this is fair and what it won't show

The model is **14B without LoRA**, not a newly trained network. It sees the same case, opponent-only private facts, history and user reply as original 8B, without `teaching` or `oracle`. The Qwen3-14B model card indicates 14.8B parameters, native 32768 tokens. The same non-thinking greedy decoding is used to compare with earlier 8B, even though sampling may improve generation.

This compares the effect of a **larger pretrained backbone** versus 8B and 8B+QLoRA, not 14B fine-tuning. 14B NF4/4-bit inference is expected to fit 24GB, but is NOT yet validated on the Intelion machine; OOM, Hugging Face download or API errors remain possible. 14B weight cache may consume tens of GB.

The three-way CSV is **unscored**, to be judged blind by a human or separate LLM using frozen `must`/`must_not`. Until scored, speed/length statistics prove nothing about negotiation quality.

## Later experiments (NOT launched automatically)

The existing training script now supports CLI `--lora-rank`, `--lora-alpha` and `--lora-dropout`, alongside `--epochs` and independent `--output`. Proposed after checking 14B result:
- Qwen3-8B QLoRA rank16, **2 epochs from the original base** (independent run, never overwrite V1).
- Qwen3-8B QLoRA rank32, **1 epoch from the original base** (independent run, never overwrite V1).
- Qwen3-32B BASE requires a GPU/memory preflight on a machine with much more VRAM; do not assume a single 3090/24GB works comfortably.

Do not apply the generic `training/run_and_stop.py` to those variants: it targets the V1 output path. A separate safe runner will be prepared after deciding based on 14B DEV results.
