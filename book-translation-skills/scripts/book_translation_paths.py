"""Resolve the workspace directory where secrets and work/ live.

Layout:
    book-translation-pipeline/
    ├── workspace/              # secrets, input/, work/, output/, config/
    └── book-translation-skills/
        └── scripts/            # this file lives here

Resolution order:
1. Environment variable BOOK_TRANSLATION_WORKSPACE
2. Walk upward from cwd looking for a directory that contains
   local.secrets.json or secrets.json (supports running from workspace/ or its parent)
"""

from __future__ import annotations

import os
import pathlib


def resolve_workspace() -> pathlib.Path:
    env = os.environ.get("BOOK_TRANSLATION_WORKSPACE", "").strip()
    if env:
        p = pathlib.Path(env).expanduser().resolve()
        if p.is_dir():
            return p

    cwd = pathlib.Path.cwd().resolve()
    for d in [cwd, *cwd.parents]:
        for name in ("local.secrets.json", "secrets.json"):
            if (d / name).is_file():
                return d
        if (d / "workspace").is_dir():
            ws = d / "workspace"
            for name in ("local.secrets.json", "secrets.json"):
                if (ws / name).is_file():
                    return ws

    raise RuntimeError(
        "Could not find workspace (no local.secrets.json / secrets.json). "
        "cd into workspace/ or set BOOK_TRANSLATION_WORKSPACE."
    )
