# Intelion RTX 3090 — runbook (4h, unattended with API auto-stop)

Repo public. No GitHub authentication or manual dataset uploads. Private DEV/TEST do not go to the training host.

**Pre-flight:** fund enough time for up to 4 hours; if Intelion UI has Auto-renew, turn it OFF. Cloud API token is separate from GitHub and is needed ONLY for automated cloud stop. Do not paste the token in chat, logs or public repo. Official Intelion API SDK supports cloud_servers.stop(server_id=...).

## 1. Start VM, open its SSH terminal or JupyterLab Terminal

```bash
nvidia-smi
python3 --version
df -h /
git clone --depth 1 https://github.com/decorum-guy/peregovori.git
cd peregovori
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip intelion-cloud
```

Do not download the full model on your Mac. The public TRAIN corpus comes directly with the git clone.

## 2. Set API token and ARМ deadline EARLY (while running on VM)

Get an Intelion Cloud API token from the provider dashboard: https://intelion.cloud/api/ . Securely enter it into a file outside Git:

```bash
python training/intelion_autostop.py token
python training/intelion_autostop.py list
```

Read the exact numeric **GPU server ID** from list output. The user account ID shown in the UI may be DIFFERENT. Confirm the name. Replace `<ID>` below (no angle brackets):

```bash
python training/intelion_autostop.py arm --server-id YOUR_SERVER_ID --minutes 210
python training/intelion_autostop.py status
```

This schedules a detached **IN-VM** hard-stop watchdog for 3h30m from arming, 30 minutes before a 4h upper bound. It uses the Intelion cloud API rather than just powering down Linux. Timer starts after VM was booted: arm quickly, and count any provisioning time separately. The job keeps running when the terminal disconnects, but cannot survive an unexpected VM shutdown/restart. Turn off Auto-renew as a second safeguard if available and confirm stop in the provider dashboard.

Optional explicit API test before spending hours: run list/status now; do not call stop until ready. Real stop behavior is not verified until provider actually acknowledges stop.

## 3. Install QLoRA stack and verify CUDA

```bash
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
python -m pip install 'transformers>=4.51,<5' 'peft>=0.15' accelerate bitsandbytes datasets safetensors
python -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.cuda.get_device_name(0))'
python training/prepare_sft.py
python training/train_qlora.py --dry-run
```

Expected: RTX 3090 and CUDA True; 200 SHA-verified cases, 895 derived SFT completions, nonzero supervised tokens and no prompt-overflow errors. STOP and fix any failed check. `--dry-run` does NOT load full model weights or run CUDA training.

## 4. Run smoke → full QLoRA → bundle → Intelion API stop

Replace YOUR_SERVER_ID with value already checked. Run after step 3:

```bash
mkdir -p training/outputs
nohup .venv/bin/python -u training/run_and_stop.py --server-id YOUR_SERVER_ID > training/outputs/run.log 2>&1 < /dev/null &
echo "Pipeline PID: $!"
tail -n 30 training/outputs/run.log
```

`run_and_stop.py` performs a 10-step smoke training and then one training epoch, checks and packs the adapter, writes SHA-256 of the archive, and requests Intelion Cloud API stop, **including when the job fails**. It runs independently of the browser/terminal. `train_qlora.py` saves checkpoints every 15 optimizer steps and gracefully stops when near hard deadline, then saves a LoRA adapter. If it runs out of time before any usable training, the stopped VM may only contain logs/checkpoints; do not assume a successful artifact.

Monitor without affecting operation:

```bash
tail -f training/outputs/run.log
python training/intelion_autostop.py status
ls -lh training/outputs/
```

## 5. When VM is stopped

Verify state **Stopped** and billing in Intelion panel; an API stop request is not the same as independently confirmed completion. Check logs if the VM is still running.

Expected files on the VM disk:

- `training/outputs/qlora_v1_bundle.tar.gz` and `.sha256` (only on successful run)
- `training/outputs/qlora_v1/adapter/adapter_model.safetensors` and `adapter_config.json`
- `training/outputs/qlora_v1/run_config.json`
- `training/outputs/run.log`, `training/outputs/final_status.json`, `training/outputs/intelion_autostop.log`
- `training/derived/peregovori_sft_report.json`

Download to your Mac by SCP or through JupyterLab **before stopping** if you are present when it finishes. With fully unattended auto-stop, files remain on the attached Intelion disk, not yet on your Mac: restart briefly later to retrieve them (this may incur billing).

**Current Intelion published policy (12 Oct 2026):** after shutdown, first 72 hours of disk retention are free; thereafter storage is charged 5 RUB/GB/month; if balance cannot cover storage disk may be deleted after notification. Check current offer for your VM before relying on it. This is not an offsite backup.

Security: remove/revoke the broad cloud API token in Intelion dashboard after training and downloading files. The local copy is at `~/.config/peregovori/intelion_token` with mode 0600.

## Validation we have/have not performed

- Previous GitHub review confirmed case counts and message alternation for 8 batches, code is committed and ready for a **runtime test**.
- This plan DOES NOT claim CUDA/SDK integration was already tested on your actual rented server. Run smoke gate before full and check resulting saved adapter.
- No `sudo shutdown` shortcut: a guest OS halt alone is not proof billing has stopped.

## Emergency/manual stop

```bash
python training/intelion_autostop.py stop --server-id YOUR_SERVER_ID
```

If provider API is unavailable, stop server from Intelion dashboard. The hard watchdog makes up to five attempts; it is a safety net, not a provider-side guaranteed spending cap.

## Recovery after unexpected VM stop (no final adapter)

If `python training/check_result.py` reports missing `final_status.json`, adapter and bundle but the train log stops mid-epoch, **do not assume successful training or start another full run**. First inspect:

```bash
find training/outputs/qlora_v1 -maxdepth 2 -type f \\
  \( -name '*.safetensors' -o -name 'trainer_state.json' \) -print
du -sh training/outputs/qlora_v1/* 2>/dev/null
tail -n 30 training/outputs/intelion_autostop.log
```

Training saves an HF Trainer checkpoint every 15 optimizer steps, retaining the last two. At step 88 the latest **expected** complete checkpoint is `checkpoint-75`, but verify the actual files. A resumable checkpoint contains `trainer_state.json`, `optimizer.pt`, `scheduler.pt`, `adapter_config.json`, and `*.safetensors`. On VM restart the old in-VM watchdog is gone; archive the stale deadline file and arm a **new** watchdog immediately, checking that no old `_watch` process is active.

After the user has checked the provider rental period/balance and confirmed a complete checkpoint, run the recovery pipeline, NOT the standard smoke/full pipeline:

```bash
cd ~/peregovori
source .venv/bin/activate
git pull --ff-only
mkdir -p training/outputs
nohup .venv/bin/python -u training/run_and_stop.py --server-id 11425 --resume-latest \\
  > training/outputs/recovery.log 2>&1 < /dev/null &
tail -f training/outputs/recovery.log
```

This continues the **original** epoch using the saved Trainer optimizer/scheduler/model state and then bundles the adapter and requests provider stop. The `--resume-latest` option skips the 10-step smoke rerun. It refuses to resume if there is no complete checkpoint. If no checkpoint survives, stop and investigate provider timing/disk/files before deciding to retrain.
