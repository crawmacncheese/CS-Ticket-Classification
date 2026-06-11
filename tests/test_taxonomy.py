from pathlib import Path

import pytest

from cs_tickets.taxonomy import load_allowlist


def test_load_allowlist_non_empty(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    assert len(allow.tuples) >= 50
    assert ("B2B", "Service Task", "General Support", "TBC (Manual Review)", "N/A") in allow
