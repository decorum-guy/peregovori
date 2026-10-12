#!/usr/bin/env python3
"""Read a PRIVATE frozen evaluation zip and extract CASES and PROBES without renaming records.

Do not commit extracted files. Only DEV by default; TEST requires explicit flag.
"""
import argparse
import json
import zipfile
from pathlib import Path

SUITES = {"dev": (25, 75), "test_a": (25, 75), "test_b": (25, 75)}


def parse_jsonl(data):
    try:
        records = [json.loads(x) for x in data.decode("utf-8-sig").splitlines() if x.strip()]
    except (UnicodeDecodeError, ValueError):
        return None
    return records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", required=True)
    p.add_argument("--suite", choices=SUITES, default="dev")
    p.add_argument("--allow-sealed-test", action="store_true")
    p.add_argument("--output-root", default="eval_private")
    a = p.parse_args()
    if a.suite != "dev" and not a.allow_sealed_test:
        raise SystemExit("Refusing to expose sealed TEST before final candidate decision")
    selected = {}
    with zipfile.ZipFile(a.zip) as archive:
        for item in archive.infolist():
            if item.is_dir() or not item.filename.lower().endswith(".jsonl"):
                continue
            if item.file_size > 40 * 1024 * 1024:
                raise SystemExit("Suspiciously large JSONL; refusing")
            data = archive.read(item)
            rows = parse_jsonl(data)
            if not rows:
                continue
            if all(isinstance(r, dict) and "id" in r and "dialogue" in r and
                   "opponent" in r for r in rows):
                kind = "cases"
            elif all(isinstance(r, dict) and "probe_id" in r and "oracle" in r for r in rows):
                kind = "probes"
            else:
                continue
            if kind in selected:
                raise SystemExit(f"Multiple {kind} files; specify manually instead")
            selected[kind] = (item.filename, data, rows)
    for kind, target in zip(("cases", "probes"), SUITES[a.suite]):
        if kind not in selected:
            raise SystemExit(f"Missing {kind}. Found only: {list(selected)}")
        if len(selected[kind][2]) != target:
            raise SystemExit(f"Expected {target} {kind}, got {len(selected[kind][2])}")
    dest = Path(a.output_root) / a.suite
    dest.mkdir(parents=True, exist_ok=True)
    for kind, (source, data, rows) in selected.items():
        path = dest / f"{kind}.jsonl"
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing {path}")
        path.write_bytes(data)
        path.chmod(0o600)
        print(f"{source} → {path}: {len(rows)} rows")
    print("Extracted files are PRIVATE. Validate with evaluation/run_gpu.py before inference.")


if __name__ == "__main__":
    main()
