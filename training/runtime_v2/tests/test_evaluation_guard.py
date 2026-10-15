import copy
import json
from types import SimpleNamespace
import pytest

from training.runtime_v2.common import digest, read_json, sha_file, write_json
from training.runtime_v2.contract import runtime_messages
from training.runtime_v2.evaluate import CANDIDATES, PROTOCOLS, blind, prepare
from training.runtime_v2.guard import stop_and_verify, stop_confirmed
from test_pipeline import make_release
from training.runtime_v2.import_corpus import import_corpus


def make_dev(tmp_path, record, overlap=False):
    source = tmp_path / "train_source"
    source.mkdir()
    registry, _ = make_release(source, record)
    corpus = tmp_path / "train"
    import_corpus(registry, corpus)
    dev_record = copy.deepcopy(record)
    if not overlap:
        dev_record["case_id"] = "SYNTHETIC_DEV_ONLY"
        dev_record["runtime_case"]["public"]["context"] = "Другая искусственная сцена с синей коробкой."
    item = {"id": "probe1", "case_id": dev_record["case_id"], "runtime_case": dev_record["runtime_case"],
            "history": dev_record["dialogue"][:2], "oracle": "PRIVATE_ORACLE_CANARY",
            "continuation_player_turns": ["Встретимся у входа."]}
    path = tmp_path / "dev.jsonl"
    path.write_text(json.dumps(item, ensure_ascii=False) + "\n")
    m = tmp_path / "dev.manifest.json"
    write_json(m, {"split": "DEV", "status": "FROZEN", "sha256": sha_file(path),
                   "records": 1, "case_ids": [item["case_id"]]})
    return path, m, corpus


def test_same_dev_six_candidates_and_oracle_isolation(tmp_path, record):
    dev, manifest, corpus = make_dev(tmp_path, record)
    bundle = tmp_path / "bundle"
    plan = prepare(dev, manifest, corpus, bundle)
    assert plan["candidates"] == CANDIDATES and len(CANDIDATES) == 6
    assert PROTOCOLS["website"]["temperature"] == .75
    assert all(p["max_new_tokens"] == 600 for p in PROTOCOLS.values())
    item = json.loads((bundle / "inputs.jsonl").read_text())
    prompt = runtime_messages(item["runtime_case"], item["history"], style="A", transport="qwen")
    assert "PRIVATE_ORACLE_CANARY" not in json.dumps(prompt)
    assert "SECRET_CANARY" not in json.dumps(prompt)
    assert "PRIVATE_ORACLE_CANARY" in (bundle / "judge_private.jsonl").read_text()
    # Synthetic generation result fixture, not model-quality evidence.
    for name in CANDIDATES:
        result = bundle / "results" / f"{name}.website.jsonl"
        result.parent.mkdir(exist_ok=True)
        result.write_text(json.dumps({"id": "probe1", "candidate": name, "protocol": "website",
            "plan_sha256": digest(plan), "generations": [{"text": "Artificial test answer"}]}) + "\n")
        write_json(result.with_suffix(".manifest.json"), {"sha256": sha_file(result), "plan_sha256": digest(plan)})
    packet = blind(bundle, "website")
    assert packet["candidates"] == 6
    assert all(v is None for ratings in read_json(bundle / "blind_website/review.json")[0]["ratings"].values()
               for v in ratings.values())


def test_dev_train_overlap_rejected(tmp_path, record):
    dev, manifest, corpus = make_dev(tmp_path, record, overlap=True)
    with pytest.raises(ValueError, match="overlap"):
        prepare(dev, manifest, corpus, tmp_path / "bundle")


@pytest.mark.parametrize("status,state,open_usage,expected", [(-1,0,False,True), (0,200,True,False),
    (2,0,True,False), (-1,200,False,False), (-1,0,True,False)])
def test_stopped_is_not_request_ack(status, state, open_usage, expected):
    server = SimpleNamespace(status=status, server_state=state,
                             usage_act=SimpleNamespace(stop_dt=None) if open_usage else None)
    assert stop_confirmed(server) == expected


def test_provider_retries_until_verified_and_reports_failure(tmp_path):
    class Client:
        def __init__(self): self.cloud_servers = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, server_id): return SimpleNamespace(status=2, server_state=0, usage_act=None)
        def stop(self, server_id): pass  # ACK never proves stop.
    report = tmp_path / "stop.json"
    with pytest.raises(RuntimeError, match="NOT confirmed"):
        stop_and_verify(1, report, client_factory=Client, sleep=lambda _: None, attempts=2)
    assert read_json(report)["status"] == "STOP_UNCONFIRMED_MANUAL_ACTION_REQUIRED"
    class Stopped(Client):
        def get(self, server_id): return SimpleNamespace(status=-1, server_state=0, usage_act=None)
    assert stop_and_verify(1, report, client_factory=Stopped, attempts=1)["status"] == "PROVIDER_STOP_CONFIRMED"
