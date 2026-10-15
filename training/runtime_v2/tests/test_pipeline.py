import copy
import json
from pathlib import Path
import time
import pytest

from training.runtime_v2.common import (HERE, EXPERIMENTS, completed, digest, file_inventory,
                                       load_config, read_json, sha_file, write_json)
from training.runtime_v2.contract import QWEN_SUFFIX, check_prompt, rebuild, runtime_identity, verify_row
from training.runtime_v2.import_corpus import PendingData, import_corpus, verify_corpus
from training.runtime_v2.train import check_budget, seal_checkpoint, validate_resume


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_four_configs(name):
    c = load_config(HERE / "configs" / (name + ".json"))
    assert c["epochs"] in [1, 2]
    assert c["learning_rate"] == 1e-4
    assert completed(c["epochs"], 177 * c["epochs"], 1416, c)
    assert not completed(c["epochs"] - 0.0001, 9999, 1416, c)
    assert not completed(c["epochs"], 1, 1416, c)


@pytest.mark.parametrize("key,value", [("epochs", 3), ("epochs", 4), ("rank", 8), ("alpha", 16),
    ("learning_rate", 2e-4), ("seed", 0), ("revision", "main"), ("batch_size", 2),
    ("output_dir", "training/outputs/old"), ("max_prompt_tokens", 3072)])
def test_config_tampering(tmp_path, key, value):
    c = read_json(HERE / "configs/qwen3_14b_r16_e2.json")
    c[key] = value
    p = tmp_path / "c.json"
    write_json(p, c)
    with pytest.raises(ValueError):
        load_config(p)


def test_pinned_source_and_teacher_canary(record):
    assert runtime_identity()["contract"]["serializer"] == "app.prompts.roleplay_messages"
    rows = rebuild(record)
    assert "teaching" in rows[0]["prompt"][0]["content"]
    assert "SECRET_CANARY" not in json.dumps(rows)
    assert rows[0]["prompt"][0]["content"].count(QWEN_SUFFIX) == 1
    mutated = copy.deepcopy(record)
    mutated["runtime_case"]["teaching"]["acceptable_outcomes"] = ["ALTERNATE_SECRET"]
    assert [r["prompt"] for r in rebuild(mutated)] == [r["prompt"] for r in rows]
    assert rows[0]["completion"][0]["content"] == record["dialogue"][2]["text"]
    assert rows[-1]["prompt"][-1]["content"] == record["dialogue"][-2]["text"]


@pytest.mark.parametrize("attack", ["suffix", "teaching", "oracle", "history", "completion", "plain_text"])
def test_real_leakage_or_source_mismatch(record, attack):
    row = rebuild(record)[0]
    if attack == "suffix":
        row["prompt"][0]["content"] += QWEN_SUFFIX
    elif attack in {"teaching", "oracle"}:
        s = row["prompt"][0]["content"]
        row["prompt"][0]["content"] = s.replace('"category":', '"' + attack + '":"CLOSED", "category":', 1)
    elif attack == "history":
        row["prompt"][-1]["content"] += " changed"
    elif attack == "completion":
        row["completion"][0]["content"] += " changed"
    else:
        row["prompt"][0]["content"] = "oracle answer leaked\n" + row["prompt"][0]["content"]
    with pytest.raises(ValueError):
        verify_row(row, record, 2)


def make_release(tmp_path, record):
    root = tmp_path / "private"
    root.mkdir()
    source = root / "branches.jsonl"
    source.write_text(json.dumps(record, ensure_ascii=False) + "\n")
    cards = root / "cards.json"
    write_json(cards, [{"case_id": record["case_id"], "runtime_case": record["runtime_case"]}])
    sft = root / "sft.jsonl"
    sft.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rebuild(record)))
    evidence = root / "acceptance.json"
    write_json(evidence, {"human_acceptance": "artificial fixture only"})
    a = {"status": "ACCEPTED", "split": "TRAIN", "cases": 1, "examples": 2, "excluded_ids": ["NOT_ACCEPTED"],
        "sources": [{"release": "synthetic.v2", "accepted": True, "acceptance_reference": "TEST ONLY",
            "cases": 1, "branches": 1, "examples": 2, "accepted_ids": [record["case_id"]],
            "files": {k: {"path": str(p), "sha256": sha_file(p)} for k, p in
                      {"branches": source, "cards": cards, "sft": sft, "manifest": evidence}.items()}}]}
    path = tmp_path / "registry.json"
    write_json(path, a)
    return path, a


def test_dynamic_count_import_lineage_and_recheck(tmp_path, record):
    path, a = make_release(tmp_path, record)
    output = tmp_path / "out"
    result = import_corpus(path, output)
    rows, m = verify_corpus(output)
    assert result["examples"] == len(rows) == 2  # neither 895 nor hardcoded 1416
    assert rows[-1]["provenance"]["target_turn_index"] == 4
    assert rows[-1]["provenance"]["history_sha256"] == digest(record["dialogue"][:4])
    with pytest.raises(ValueError, match="already exists"):
        import_corpus(path, output)
    (output / "train.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="SHA"):
        verify_corpus(output)


@pytest.mark.parametrize("attack", ["pending", "count", "ids", "exclude", "sha", "missing", "duplicate_source", "split"])
def test_import_gates(tmp_path, record, attack):
    path, a = make_release(tmp_path, record)
    s = a["sources"][0]
    if attack == "pending": s["accepted"] = False
    if attack == "count": a["examples"] = 2160
    if attack == "ids": s["accepted_ids"] = ["NOT_ACCEPTED"]
    if attack == "exclude": a["excluded_ids"] = [record["case_id"]]
    if attack == "sha": s["files"]["branches"]["sha256"] = "0" * 64
    if attack == "missing": s["files"]["sft"]["path"] = str(tmp_path / "missing.jsonl")
    if attack == "duplicate_source": a["sources"].append(copy.deepcopy(s))
    if attack == "split": a["split"] = "DEV"
    write_json(path, a)
    with pytest.raises((ValueError, PendingData)):
        import_corpus(path, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_full_checkpoint_resume_identity_and_corruption(tmp_path):
    identity = {"config": {"epochs": 2}, "corpus": "train-sha"}
    folder = tmp_path / "checkpoint-15"
    folder.mkdir()
    for n in ["optimizer.pt", "scheduler.pt", "rng_state.pth", "adapter_config.json", "adapter_model.safetensors"]:
        (folder / n).write_bytes(b"synthetic")
    write_json(folder / "trainer_state.json", {"epoch": 0.25})
    seal_checkpoint(folder, identity)
    assert validate_resume(folder, tmp_path, identity) == str(folder.resolve())
    with pytest.raises(ValueError, match="Cross-experiment"):
        validate_resume(folder, tmp_path, {**identity, "corpus": "other"})
    (folder / "rng_state.pth").unlink()
    with pytest.raises(ValueError):
        validate_resume(folder, tmp_path, identity)
    with pytest.raises(ValueError):
        seal_checkpoint(folder, identity)


def test_budget_deadline_and_unverified_stop(tmp_path):
    p = tmp_path / "budget.json"
    b = {"provider_stop_verified": True, "external_watchdog_armed": True,
         "train_stop_epoch": time.time() + 1000, "billing_stop_epoch": time.time() + 1800,
         "server_id": 123, "max_hourly_rub": 100, "max_total_rub": 200, "billing_start_epoch": time.time()-60}
    write_json(p, b)
    assert check_budget(p)
    b["provider_stop_verified"] = False
    write_json(p, b)
    with pytest.raises(ValueError): check_budget(p)
    b["provider_stop_verified"] = True
    b["train_stop_epoch"] = time.time() - 1
    write_json(p, b)
    with pytest.raises(ValueError): check_budget(p)
