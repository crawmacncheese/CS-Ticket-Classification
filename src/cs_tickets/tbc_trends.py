"""TBC trend snapshots: subject clustering, SQLite storage, and rollups."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

from cs_tickets.classify import classify_row_with_explanation, tbc_reason
from cs_tickets.repo_paths import training_rules_path
from cs_tickets.satisfaction import has_bad_satisfaction_rating
from cs_tickets.taxonomy import AllowList
from cs_tickets.thread_enrich import (
    build_ticket_index,
    flatten_for_classify,
    thread_enrichment_enabled,
)

from cs_tickets.pipeline import _iter_ticket_dicts

_REPLY_PREFIX_RE = re.compile(r"^(re|fw|fwd):\s*", re.IGNORECASE)
_LONG_DIGITS_RE = re.compile(r"\d{4,}")
_WHITESPACE_RE = re.compile(r"\s+")


def subject_cluster_key(subject: str) -> str:
    """Deterministic subject fingerprint for TBC cluster rollups."""
    s = (subject or "").strip().lower()
    s = _REPLY_PREFIX_RE.sub("", s)
    s = _LONG_DIGITS_RE.sub("#", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s[:80] if s else "(empty)"


def parse_tags(tags_cell: str) -> list[str]:
    try:
        value = json.loads(tags_cell or "[]")
    except json.JSONDecodeError:
        return [tags_cell] if tags_cell else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def classifier_version_hash() -> str:
    """Short hash of packaged rules + optional training rules overlay."""
    parts: list[bytes] = []
    bundled = files("cs_tickets").joinpath("classifier_rules.json")
    parts.append(bundled.read_bytes())
    training = training_rules_path()
    if training.is_file():
        parts.append(training.read_bytes())
    digest = hashlib.sha256(b"".join(parts)).hexdigest()
    return digest[:12]


def week_bucket(created_at: str) -> str:
    """ISO week label from Zendesk ``created_at`` (e.g. ``2025-W01``)."""
    raw = (created_at or "").strip()
    if not raw:
        return "unknown"
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return "unknown"
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _is_tbc(decision) -> bool:
    return decision.fallback_used or "tbc" in decision.tier[3].lower()


@dataclass(frozen=True)
class TrendTicketRecord:
    ticket_id: str
    created_at: str
    updated_at: str
    week_bucket: str
    segment: str
    is_tbc: bool
    tbc_reason: str
    subject: str
    subject_cluster: str
    tags: tuple[str, ...]


def iter_trend_records(
    ndjson_path: Path,
    allow: AllowList,
    *,
    bad_satisfaction_only: bool = False,
) -> Iterator[TrendTicketRecord]:
    """Classify each ticket in an export and yield trend rows."""
    if thread_enrichment_enabled():
        tickets = list(_iter_ticket_dicts(ndjson_path))
        thread_index = build_ticket_index(tickets)
        ticket_source: Iterator[dict[str, Any]] = iter(tickets)
    else:
        thread_index = {}
        ticket_source = _iter_ticket_dicts(ndjson_path)

    for ticket in ticket_source:
        if bad_satisfaction_only and not has_bad_satisfaction_rating(ticket):
            continue
        row = flatten_for_classify(ticket, thread_index)
        decision = classify_row_with_explanation(row, allow)
        subject = str(row.get("subject") or "").strip()
        tags = tuple(parse_tags(str(row.get("tags") or "")))
        is_tbc = _is_tbc(decision)
        reason = tbc_reason(decision) if is_tbc else "not_tbc"
        created = str(row.get("created_at") or "")
        updated = str(row.get("updated_at") or created)
        yield TrendTicketRecord(
            ticket_id=str(row.get("id") or ""),
            created_at=created,
            updated_at=updated,
            week_bucket=week_bucket(created),
            segment=decision.tier[0],
            is_tbc=is_tbc,
            tbc_reason=reason,
            subject=subject,
            subject_cluster=subject_cluster_key(subject),
            tags=tags,
        )


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS exports (
    export_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    tbc_count INTEGER NOT NULL,
    classifier_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    week_bucket TEXT NOT NULL,
    segment TEXT NOT NULL,
    is_tbc INTEGER NOT NULL,
    tbc_reason TEXT NOT NULL,
    subject TEXT NOT NULL,
    subject_cluster TEXT NOT NULL,
    export_id TEXT NOT NULL,
    classifier_version TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_tags (
    ticket_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    week_bucket TEXT NOT NULL,
    is_tbc INTEGER NOT NULL,
    PRIMARY KEY (ticket_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_tickets_week ON tickets(week_bucket);
CREATE INDEX IF NOT EXISTS idx_tickets_tbc ON tickets(is_tbc);
CREATE INDEX IF NOT EXISTS idx_ticket_tags_week_tag ON ticket_tags(week_bucket, tag);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def append_export_snapshot(
    conn: sqlite3.Connection,
    ndjson_path: Path,
    allow: AllowList,
    *,
    export_id: str | None = None,
    captured_at: datetime | None = None,
    bad_satisfaction_only: bool = False,
) -> tuple[int, int]:
    """Classify ``ndjson_path`` and upsert tickets. Returns ``(row_count, tbc_count)``."""
    when = captured_at or datetime.now(timezone.utc)
    captured_str = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    eid = export_id or ndjson_path.stem
    version = classifier_version_hash()
    records = list(
        iter_trend_records(ndjson_path, allow, bad_satisfaction_only=bad_satisfaction_only)
    )
    tbc_count = sum(1 for r in records if r.is_tbc)

    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO exports
            (export_id, source_path, captured_at, row_count, tbc_count, classifier_version)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (eid, str(ndjson_path), captured_str, len(records), tbc_count, version),
        )
        for rec in records:
            conn.execute(
                """
                INSERT OR REPLACE INTO tickets
                (ticket_id, created_at, updated_at, week_bucket, segment, is_tbc,
                 tbc_reason, subject, subject_cluster, export_id, classifier_version, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.ticket_id,
                    rec.created_at,
                    rec.updated_at,
                    rec.week_bucket,
                    rec.segment,
                    1 if rec.is_tbc else 0,
                    rec.tbc_reason,
                    rec.subject,
                    rec.subject_cluster,
                    eid,
                    version,
                    captured_str,
                ),
            )
            conn.execute("DELETE FROM ticket_tags WHERE ticket_id = ?", (rec.ticket_id,))
            for tag in rec.tags:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ticket_tags
                    (ticket_id, tag, week_bucket, is_tbc)
                    VALUES (?, ?, ?, ?)
                    """,
                    (rec.ticket_id, tag, rec.week_bucket, 1 if rec.is_tbc else 0),
                )
    return len(records), tbc_count


@dataclass(frozen=True)
class WeeklyRollupRow:
    week_bucket: str
    total: int
    tbc_count: int
    tbc_b2b: int
    tbc_b2c: int

    @property
    def tbc_pct(self) -> float:
        return 100.0 * self.tbc_count / self.total if self.total else 0.0


def load_weekly_rollup(conn: sqlite3.Connection) -> list[WeeklyRollupRow]:
    rows = conn.execute(
        """
        SELECT
            week_bucket,
            COUNT(*) AS total,
            SUM(is_tbc) AS tbc_count,
            SUM(CASE WHEN is_tbc = 1 AND segment = 'B2B' THEN 1 ELSE 0 END) AS tbc_b2b,
            SUM(CASE WHEN is_tbc = 1 AND segment = 'B2C' THEN 1 ELSE 0 END) AS tbc_b2c
        FROM tickets
        GROUP BY week_bucket
        ORDER BY week_bucket
        """
    ).fetchall()
    return [
        WeeklyRollupRow(
            week_bucket=str(r["week_bucket"]),
            total=int(r["total"]),
            tbc_count=int(r["tbc_count"] or 0),
            tbc_b2b=int(r["tbc_b2b"] or 0),
            tbc_b2c=int(r["tbc_b2c"] or 0),
        )
        for r in rows
    ]


def load_tag_rollup(conn: sqlite3.Connection, *, top_n: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT week_bucket, tag, SUM(is_tbc) AS tbc_count
        FROM ticket_tags
        WHERE is_tbc = 1
        GROUP BY week_bucket, tag
        ORDER BY week_bucket, tbc_count DESC
        """
    ).fetchall()
    by_week: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        week = str(r["week_bucket"])
        if len(by_week[week]) >= top_n:
            continue
        by_week[week].append({"week_bucket": week, "tag": r["tag"], "tbc_count": int(r["tbc_count"])})
    out: list[dict[str, Any]] = []
    for week in sorted(by_week):
        out.extend(by_week[week])
    return out


def load_subject_cluster_rollup(conn: sqlite3.Connection, *, top_n: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT week_bucket, subject_cluster, subject, is_tbc
        FROM tickets
        WHERE is_tbc = 1
        """
    ).fetchall()
    counts: Counter[tuple[str, str]] = Counter()
    sample_subjects: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for r in rows:
        key = (str(r["week_bucket"]), str(r["subject_cluster"]))
        counts[key] += 1
        subj = str(r["subject"] or "").strip()
        if subj:
            sample_subjects[key][subj] += 1

    by_week: dict[str, list[tuple[tuple[str, str], int]]] = defaultdict(list)
    for key, count in counts.items():
        by_week[key[0]].append((key, count))

    out: list[dict[str, Any]] = []
    for week in sorted(by_week):
        ranked = sorted(by_week[week], key=lambda x: x[1], reverse=True)[:top_n]
        for (wb, cluster), count in ranked:
            samples = sample_subjects.get((wb, cluster), Counter())
            display = samples.most_common(1)[0][0] if samples else cluster
            out.append(
                {
                    "week_bucket": wb,
                    "subject_cluster": cluster,
                    "sample_subject": display,
                    "tbc_count": count,
                }
            )
    return out


def load_tbc_reason_rollup(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT week_bucket, tbc_reason, COUNT(*) AS tbc_count
        FROM tickets
        WHERE is_tbc = 1
        GROUP BY week_bucket, tbc_reason
        ORDER BY week_bucket, tbc_count DESC
        """
    ).fetchall()
    return [
        {
            "week_bucket": str(r["week_bucket"]),
            "tbc_reason": str(r["tbc_reason"]),
            "tbc_count": int(r["tbc_count"]),
        }
        for r in rows
    ]


def load_export_summary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT export_id, source_path, captured_at, row_count, tbc_count, classifier_version
        FROM exports
        ORDER BY captured_at
        """
    ).fetchall()
    return [dict(r) for r in rows]


def write_rollup_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_weekly_rollup_csv(path: Path, rows: list[WeeklyRollupRow]) -> None:
    write_rollup_csv(
        path,
        ["week_bucket", "total", "tbc_count", "tbc_pct", "tbc_b2b", "tbc_b2c"],
        [
            {
                "week_bucket": r.week_bucket,
                "total": r.total,
                "tbc_count": r.tbc_count,
                "tbc_pct": f"{r.tbc_pct:.1f}",
                "tbc_b2b": r.tbc_b2b,
                "tbc_b2c": r.tbc_b2c,
            }
            for r in rows
        ],
    )


def build_summary_markdown(conn: sqlite3.Connection) -> str:
    weekly = load_weekly_rollup(conn)
    exports = load_export_summary(conn)
    tag_rows = load_tag_rollup(conn, top_n=15)
    cluster_rows = load_subject_cluster_rollup(conn, top_n=15)
    reason_rows = load_tbc_reason_rollup(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    total_tickets = sum(r.total for r in weekly)
    total_tbc = sum(r.tbc_count for r in weekly)
    overall_pct = 100.0 * total_tbc / total_tickets if total_tickets else 0.0

    lines = [
        "# TBC Trend Summary",
        "",
        f"Generated: {now}",
        "",
        f"**{total_tickets}** tickets across **{len(weekly)}** week bucket(s); "
        f"**{total_tbc}** manual review (TBC) — **{overall_pct:.1f}%** overall.",
        "",
        "## Snapshots ingested",
        "",
    ]
    if exports:
        lines.append("| Export | Rows | TBC | Captured | Classifier |")
        lines.append("|--------|------|-----|----------|------------|")
        for ex in exports:
            pct = 100.0 * int(ex["tbc_count"]) / int(ex["row_count"]) if ex["row_count"] else 0.0
            lines.append(
                f"| `{ex['export_id']}` | {ex['row_count']} | "
                f"{ex['tbc_count']} ({pct:.1f}%) | {ex['captured_at']} | `{ex['classifier_version']}` |"
            )
    else:
        lines.append("_No exports ingested yet._")
    lines.extend(["", "## Weekly TBC rate", ""])
    if weekly:
        lines.append("| Week | Tickets | TBC | TBC % | B2B TBC | B2C TBC |")
        lines.append("|------|---------|-----|-------|---------|---------|")
        for r in weekly:
            lines.append(
                f"| {r.week_bucket} | {r.total} | {r.tbc_count} | {r.tbc_pct:.1f}% | "
                f"{r.tbc_b2b} | {r.tbc_b2c} |"
            )
    else:
        lines.append("_No ticket rows in database._")

    lines.extend(["", "## Top TBC tags (latest weeks)", ""])
    if tag_rows:
        current_week = tag_rows[-1]["week_bucket"] if tag_rows else ""
        week_tags = [r for r in tag_rows if r["week_bucket"] == current_week][:15]
        for r in week_tags:
            lines.append(f"- `{r['tag']}` — {r['tbc_count']}")
    else:
        lines.append("_No TBC tag data._")

    lines.extend(["", "## Top subject clusters (all weeks)", ""])
    if cluster_rows:
        seen: set[tuple[str, str]] = set()
        shown = 0
        for r in sorted(cluster_rows, key=lambda x: x["tbc_count"], reverse=True):
            key = (r["week_bucket"], r["subject_cluster"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"- **{r['week_bucket']}** `{r['subject_cluster']}` — "
                f"{r['tbc_count']} (e.g. _{r['sample_subject'][:80]}_)"
            )
            shown += 1
            if shown >= 15:
                break
    else:
        lines.append("_No subject cluster data._")

    lines.extend(["", "## TBC reason mix", ""])
    if reason_rows:
        by_week: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in reason_rows:
            by_week[r["week_bucket"]].append(r)
        for week in sorted(by_week):
            parts = ", ".join(f"{r['tbc_reason']}: {r['tbc_count']}" for r in by_week[week])
            lines.append(f"- **{week}** — {parts}")
    else:
        lines.append("_No TBC reason data._")

    lines.append("")
    return "\n".join(lines)


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def trends_snapshot_enabled() -> bool:
    return _truthy_env("TBC_TRENDS_ENABLED")


def trends_db_path(repo_root: Path) -> Path:
    raw = (os.environ.get("TBC_TRENDS_DB_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return repo_root / "reports" / "tbc_trends" / "tbc_trends.db"


def trends_events_path(repo_root: Path) -> Path:
    raw = (os.environ.get("TBC_TRENDS_EVENTS_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return repo_root / "reports" / "tbc_trends" / "events.json"


@dataclass(frozen=True)
class TrendEvent:
    date: str
    label: str


def load_trend_events(events_path: Path) -> list[TrendEvent]:
    if not events_path.is_file():
        return []
    try:
        payload = json.loads(events_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not read trend events from %s", events_path)
        return []
    if not isinstance(payload, list):
        return []
    out: list[TrendEvent] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "").strip()
        label = str(item.get("label") or "").strip()
        if date and label:
            out.append(TrendEvent(date=date, label=label))
    return sorted(out, key=lambda e: e.date)


def try_append_portal_snapshot(
    ndjson_path: Path,
    allow: AllowList,
    *,
    repo_root: Path,
    source_filename: str,
    bad_satisfaction_only: bool = False,
) -> tuple[int, int] | None:
    """Append a portal upload to the trends DB when ``TBC_TRENDS_ENABLED`` is set."""
    if not trends_snapshot_enabled():
        return None
    db_path = trends_db_path(repo_root)
    export_id = Path(source_filename).stem or ndjson_path.stem
    try:
        conn = init_db(db_path)
        try:
            return append_export_snapshot(
                conn,
                ndjson_path,
                allow,
                export_id=export_id,
                bad_satisfaction_only=bad_satisfaction_only,
            )
        finally:
            conn.close()
    except Exception:
        logger.exception("TBC trends snapshot failed for %s", source_filename)
        return None


@dataclass(frozen=True)
class DashboardSnapshot:
    total_tickets: int
    total_tbc: int
    week_count: int
    export_count: int
    classifier_version: str | None


def dashboard_snapshot(conn: sqlite3.Connection) -> DashboardSnapshot:
    weekly = load_weekly_rollup(conn)
    exports = load_export_summary(conn)
    total_tickets = sum(r.total for r in weekly)
    total_tbc = sum(r.tbc_count for r in weekly)
    version = exports[-1]["classifier_version"] if exports else None
    return DashboardSnapshot(
        total_tickets=total_tickets,
        total_tbc=total_tbc,
        week_count=len(weekly),
        export_count=len(exports),
        classifier_version=version,
    )


def write_trend_reports(output_dir: Path, conn: sqlite3.Connection) -> list[Path]:
    """Write ``summary.md`` and rollup CSVs; return paths written."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    summary_path = output_dir / "summary.md"
    summary_path.write_text(build_summary_markdown(conn), encoding="utf-8")
    written.append(summary_path)

    weekly_path = output_dir / "weekly_rollup.csv"
    write_weekly_rollup_csv(weekly_path, load_weekly_rollup(conn))
    written.append(weekly_path)

    tag_path = output_dir / "tag_rollup.csv"
    write_rollup_csv(tag_path, ["week_bucket", "tag", "tbc_count"], load_tag_rollup(conn))
    written.append(tag_path)

    cluster_path = output_dir / "cluster_rollup.csv"
    write_rollup_csv(
        cluster_path,
        ["week_bucket", "subject_cluster", "sample_subject", "tbc_count"],
        load_subject_cluster_rollup(conn),
    )
    written.append(cluster_path)

    reason_path = output_dir / "tbc_reason_rollup.csv"
    write_rollup_csv(
        reason_path,
        ["week_bucket", "tbc_reason", "tbc_count"],
        load_tbc_reason_rollup(conn),
    )
    written.append(reason_path)

    return written
