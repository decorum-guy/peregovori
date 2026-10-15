"""Download only locked public tokenizer/config files, never model weights."""
import argparse
import json
from pathlib import Path
from .common import HERE, read_json, require, sha_file


def main():
    from huggingface_hub import snapshot_download
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="training/derived/runtime_v2/tokenizers")
    a = p.parse_args()
    for model, lock in read_json(HERE / "model_locks.json").items():
        folder = Path(a.output) / model.split("-")[-1]
        snapshot_download(model, revision=lock["revision"], allow_patterns=list(lock["files"]), local_dir=folder)
        for name, sha in lock["files"].items():
            require(sha_file(folder / name) == sha, "Tokenizer download SHA mismatch: " + name)
        print(json.dumps({"model": model, "revision": lock["revision"], "tokenizer_sha256_verified": True}))


if __name__ == "__main__":
    main()
