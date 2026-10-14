"""Future TRAIN v2 converter, CPU only. No corpus is created by importing this.

Requires NEW runtime-train-v2.0 records, never reads legacy TRAIN or DEV/TEST.
Default qwen prompts include the inference suffix exactly once for tokenizer SFT.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "web/backend")]
from app.roleplay_contract import future_sft, contract_manifest, digest


def convert_records(records, style="A"):
    return [example for record in records for example in future_sft(record, style=style)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--style", choices=["A", "spoken-dialogue-1.0"], default="A")
    args = p.parse_args()
    records = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    samples = convert_records(records, args.style)
    manifest = dict(contract_manifest(), dataset_sha256=digest(records), examples=len(samples),
                    corpus_sha256=digest(samples), selected_style=args.style, GPU_started=False)
    if not args.dry_run:
        if not args.output or args.output.exists():
            raise ValueError("A new output path is required; overwrite forbidden")
        allowed = (ROOT / "training/derived/runtime-v2").resolve()
        if allowed not in args.output.resolve().parents:
            raise ValueError("Write only into new ignored training/derived/runtime-v2 directory")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in samples))
        args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
