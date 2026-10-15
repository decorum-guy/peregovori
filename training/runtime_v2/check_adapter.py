"""Offline adapter integrity/metadata/tensor verification. Never allocates a GPU."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
from .common import TARGET_MODULES, completed, digest, file_inventory, read_json, require


def check_adapter(output):
    import numpy as np
    from safetensors import safe_open
    output = Path(output)
    inventory = read_json(output / "SHA256.json")
    require(inventory == file_inventory(output, exclude=("SHA256.json",)), "Result SHA-256 mismatch")
    state, identity = read_json(output / "status.json"), read_json(output / "identity.json")
    require(state["status"] == "COMPLETE" and state.get("adapter") == "adapter", "Partial/preflight is not a candidate")
    c, report = identity["config"], read_json(output / "tokenization.json")
    require(state["identity_sha256"] == digest(identity), "Run identity mismatch")
    require(completed(state["actual_epoch"], state["global_step"], report["examples"], c), "Incomplete epochs/steps")
    for key in ("corpus_sha256", "runtime_contract_sha256", "tokenizer_revision"):
        require(state[key] == identity[key], "Result provenance mismatch: " + key)
    require(state["base_model"] == c["model"] and state["rank"] == c["rank"] and state["alpha"] == c["alpha"],
            "Result model/rank/alpha mismatch")
    adapter = output / "adapter"
    ac = read_json(adapter / "adapter_config.json")
    require(ac["base_model_name_or_path"] == c["model"] and ac.get("revision") == c["revision"] and ac["r"] == c["rank"] and
            ac["lora_alpha"] == c["alpha"] and ac["peft_type"] == "LORA" and
            ac["task_type"] == "CAUSAL_LM" and set(ac["target_modules"]) == set(TARGET_MODULES),
            "Adapter does not match experiment")
    pairs, locations = {}, set()
    layers = 36 if c["model"].endswith("8B") else 40
    hidden, intermediate = (4096, 12288) if layers == 36 else (5120, 17408)
    dimensions = {"q_proj": (hidden, hidden), "k_proj": (hidden, 1024), "v_proj": (hidden, 1024),
                  "o_proj": (hidden, hidden), "gate_proj": (hidden, intermediate),
                  "up_proj": (hidden, intermediate), "down_proj": (intermediate, hidden)}
    with safe_open(str(adapter / "adapter_model.safetensors"), framework="numpy") as f:
        for key in f.keys():
            match = re.fullmatch(r"(.+\.layers\.(\d+)\..+\.([a-z_]+))\.lora_([AB])\.weight", key)
            require(match is not None and match[3] in TARGET_MODULES, "Unexpected tensor: " + key)
            location = (int(match[2]), match[3], match[4])
            require(location not in locations and 0 <= location[0] < layers, "Duplicate/out-of-range layer")
            locations.add(location)
            tensor = f.get_tensor(key)
            require(tensor.ndim == 2 and np.isfinite(tensor).all(), "Non-finite/invalid adapter tensor")
            require(tensor.shape[0 if match[4] == "A" else 1] == c["rank"], "Tensor rank mismatch")
            input_dim, output_dim = dimensions[match[3]]
            expected_shape = (c["rank"], input_dim) if match[4] == "A" else (output_dim, c["rank"])
            require(tensor.shape == expected_shape, "Tensor base-model dimensions mismatch")
            pairs.setdefault(match[1], {})[match[4]] = tensor.shape
    require(len(pairs) == layers * len(TARGET_MODULES) and all(set(v) == {"A", "B"} for v in pairs.values()),
            "Missing LoRA modules/layers/pairs")
    checkpoint = output / state["final_checkpoint"]
    cm = read_json(checkpoint / "checkpoint_manifest.json")
    require(cm["identity_sha256"] == digest(identity) and cm["files"] ==
            file_inventory(checkpoint, exclude=("checkpoint_manifest.json",)), "Final full checkpoint invalid")
    ts = read_json(checkpoint / "trainer_state.json")
    require(ts["epoch"] == state["actual_epoch"] and ts["global_step"] == state["global_step"], "Final state differs")
    return {"status": "ADAPTER_INTEGRITY_PASS", "model": c["model"], "rank": c["rank"],
            "actual_epoch": state["actual_epoch"], "tensor_pairs": len(pairs),
            "adapter_sha256": digest(file_inventory(adapter)), "identity_sha256": digest(identity),
            "functional_generation": "NOT_CHECKED"}


if __name__ == "__main__":
    import json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    print(json.dumps(check_adapter(p.parse_args().output), indent=2))
