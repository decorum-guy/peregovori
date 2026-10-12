#!/usr/bin/env python3
"""Check that finished QLoRA adapter, bundle and logs survived the Intelion reboot.

Read-only. Does not load Qwen model or require a GPU.
"""
import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "training" / "outputs"
config = output / "qlora_v1" / "run_config.json"
status = output / "final_status.json"
bundle = output / "qlora_v1_bundle.tar.gz"
checksum = output / "qlora_v1_bundle.tar.gz.sha256"
weights = output / "qlora_v1" / "adapter" / "adapter_model.safetensors"
adapter_config = output / "qlora_v1" / "adapter" / "adapter_config.json"
log = output / "run.log"

checks = {
    "final_status": status.is_file(),
    "run_config": config.is_file(),
    "adapter_weights": weights.is_file() and weights.stat().st_size > 1000,
    "adapter_config": adapter_config.is_file(),
    "bundle": bundle.is_file(),
    "bundle_sha256": checksum.is_file(),
    "run_log": log.is_file(),
}
print("QUICK AUDIT OF EXISTING SERVER DISK")
for key, value in checks.items():
    print(f"  {key}: {'OK' if value else 'MISSING'}")

if status.is_file():
    data = json.loads(status.read_text(encoding="utf-8"))
    print("final_status:", json.dumps(data, ensure_ascii=False))
if config.is_file():
    data = json.loads(config.read_text(encoding="utf-8"))
    print("train_config:", json.dumps({
        k:data.get(k) for k in ["epochs","max_steps","examples",
                                  "supervised_tokens","adapter_path"]},
        ensure_ascii=False))
if log.is_file():
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    print("LOG tail (final 35 lines):")
    print("\n".join(lines[-35:]))
if bundle.is_file() and checksum.is_file():
    actual = hashlib.sha256(bundle.read_bytes()).hexdigest()
    expected = checksum.read_text(encoding="ascii").split()[0]
    print("Bundle SHA256 match:", actual == expected, actual)
    with tarfile.open(bundle, "r:gz") as archive:
        names = archive.getnames()
        print("Bundle files:", names)
        if "adapter/adapter_config.json" not in names or not any(
            name.startswith("adapter/") and name.endswith(".safetensors") for name in names
        ):
            print("ERROR: bundle does not include adapter weights/config")
            checks["bundle_content"] = False
        else:
            checks["bundle_content"] = True
    checks["bundle_hash_match"] = actual == expected
elif bundle.is_file():
    print("WARNING: bundle exists but no SHA-256 file")
if status.is_file():
    checks["training_success"] = bool(json.loads(status.read_text(encoding="utf-8")).get("success"))
print("CHECKS ALL PASS:", all(checks.values()))
if not all(checks.values()):
    print("DO NOT retrain automatically; inspect checkpoints and log first.")
    raise SystemExit(2)
