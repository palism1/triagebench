# FILE MAP
#   20-30   Paths: where each repo's frozen files live
#   33-60   write_repo: write t0/t1 JSONL (one canonical line per issue, sorted by number)
#   63-80   write_manifest / read_manifest
#   83-110  load_split: the ONLY way tuning and eval code reads data; guards the test split
#
# Purpose: on-disk format of the frozen dataset. JSONL lines are canonical JSON, so a file's
# bytes are fully determined by its records and the manifest hashes can be re-checked.

from __future__ import annotations

import json
import os
from pathlib import Path

from evals.config import DATA_DIR
from evals.snapshot import T0Snapshot, T1Truth, canonical_json, content_hash

SPLITS = ("dev", "test")
FINAL_EVAL_ENV = "TRIAGEBENCH_FINAL_EVAL"


class SealedSplitError(PermissionError):
    """Raised when code reads the test split without the final-eval switch."""


def repo_dir(root: Path, repo_key: str) -> Path:
    return root / repo_key


def write_repo(
    root: Path, repo_key: str, rows: list[tuple[str, T0Snapshot, T1Truth]]
) -> list[dict]:
    """Write <root>/<repo>/{split}.t0.jsonl and .t1.jsonl. Returns manifest entries."""
    d = repo_dir(root, repo_key)
    d.mkdir(parents=True, exist_ok=True)
    entries = []
    for split in SPLITS:
        part = sorted((r for r in rows if r[0] == split), key=lambda r: r[1].number)
        t0_lines = [canonical_json(t0.to_dict()) for _, t0, _ in part]
        t1_lines = [canonical_json(t1.to_dict()) for _, _, t1 in part]
        (d / f"{split}.t0.jsonl").write_text("".join(line + "\n" for line in t0_lines))
        (d / f"{split}.t1.jsonl").write_text("".join(line + "\n" for line in t1_lines))
        for _, t0, t1 in part:
            entries.append(
                {
                    "number": t0.number,
                    "split": split,
                    "t0_sha": t0.t0_sha,
                    "t0_hash": content_hash(t0.to_dict()),
                    "t1_hash": content_hash(t1.to_dict()),
                }
            )
    return sorted(entries, key=lambda e: e["number"])


def write_manifest(root: Path, manifest: dict) -> None:
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def read_manifest(root: Path = DATA_DIR) -> dict:
    return json.loads((root / "manifest.json").read_text())


def load_split(
    repo_key: str, split: str, part: str = "t0", root: Path = DATA_DIR
) -> list[dict]:
    """Load one split. part="t0" is agent input; part="t1" is ground truth for scoring.

    DO NOT TOUCH: the test split is sealed. It opens only when TRIAGEBENCH_FINAL_EVAL=1,
    which only the final-eval job sets. Prompt and guardrail tuning must use "dev".
    """
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}")
    if split == "test" and os.environ.get(FINAL_EVAL_ENV) != "1":
        raise SealedSplitError(
            f"test split is sealed; set {FINAL_EVAL_ENV}=1 only for the final frozen eval"
        )
    path = repo_dir(root, repo_key) / f"{split}.{part}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line]
