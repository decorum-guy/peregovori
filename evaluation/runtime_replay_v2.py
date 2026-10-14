"""Future CPU replay input verifier. Does not load weights or call any provider."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "web/backend")]
from app.roleplay_contract import dev_replay, digest, contract_manifest


def replay_messages(case, history, language="ru", *, style="A", target="tokenizer"):
    # tokenizer = post-inference-suffix prompt; http = website payload, suffix is
    # added by the Qwen server itself. Do not send tokenizer messages back over HTTP.
    if target not in {"tokenizer", "http"}:
        raise ValueError("Unknown replay target")
    return dev_replay(case, history, language, style=style, transport="qwen" if target == "tokenizer" else "cloud")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--target", choices=["tokenizer", "http"], default="tokenizer")
    p.add_argument("--style", choices=["A", "spoken-dialogue-1.0"], default="A")
    args = p.parse_args()
    record = json.loads(args.input.read_text())
    messages = replay_messages(record["runtime_case"], record["history"], record.get("language", "ru"), style=args.style, target=args.target)
    print(json.dumps(dict(contract_manifest(), prompt_sha256=digest(messages), target=args.target,
                         selected_style=args.style, status="CPU_ONLY_NO_GENERATION"), indent=2))
