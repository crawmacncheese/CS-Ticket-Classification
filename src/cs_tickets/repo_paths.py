from __future__ import annotations

import os
from pathlib import Path


def _has_doc_dir(root: Path) -> bool:
    doc = root / "doc"
    if not doc.is_dir():
        return False
    return (doc / "Taxonomy.csv").is_file() or (doc / "CS_ticket_new_categorizations.xlsx").is_file()


def resolve_repo_root() -> Path:
    """Directory containing ``doc/`` (taxonomy + reference workbook).

    Matches portal deploy resolution: ``CS_TICKETS_REPO_ROOT``, App Service
    ``HOME/site/wwwroot``, package-relative dev root, then cwd walk.
    """
    raw = (os.environ.get("CS_TICKETS_REPO_ROOT") or "").strip()
    if raw:
        root = Path(raw).expanduser().resolve()
        if _has_doc_dir(root):
            return root

    home = os.environ.get("HOME", "")
    if home:
        www = (Path(home) / "site" / "wwwroot").resolve()
        if _has_doc_dir(www):
            return www

    here = Path(__file__).resolve()
    dev = here.parents[2]
    if _has_doc_dir(dev):
        return dev

    p = Path.cwd().resolve()
    for _ in range(12):
        if _has_doc_dir(p):
            return p
        if p.parent == p:
            break
        p = p.parent

    return dev


def training_rules_path() -> Path:
    return resolve_repo_root() / "doc" / "training_rules.json"
