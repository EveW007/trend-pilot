#!/usr/bin/env python3
"""Download immutable Kronos model snapshots from Hugging Face."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


MODELS = {
    "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
    "model": "NeoQuasar/Kronos-small",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    api = HfApi()
    manifest: dict[str, dict[str, str]] = {}
    for kind, repo_id in MODELS.items():
        revision = api.model_info(repo_id).sha
        target = args.output / repo_id.rsplit("/", 1)[-1]
        snapshot_download(repo_id=repo_id, revision=revision, local_dir=target)
        manifest[kind] = {
            "repo_id": repo_id,
            "revision": revision,
            "local_path": str(target.resolve()),
        }

    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
