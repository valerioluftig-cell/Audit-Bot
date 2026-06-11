"""
Feedback and uncertainty storage for the Parish Audit Pipeline.
SQLite-backed — db lives next to the exe (or server.py) and persists across runs.
"""
import sqlite3
import json
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS coded_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    coded_dir       TEXT,
    parishes        TEXT,           -- JSON array of parish names
    total_flags     INTEGER DEFAULT 0,
    comparison_flags INTEGER DEFAULT 0,
    coding_check_flags INTEGER DEFAULT 0,
    run_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS uncertainties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT    NOT NULL,
    parish          TEXT    NOT NULL,
    year            INTEGER NOT NULL,
    statement_type  TEXT    NOT NULL,
    field_path      TEXT,
    reason          TEXT,
    extracted_value TEXT,
    alternative_value TEXT,
    page_number     INTEGER,
    text_snippet    TEXT,
    severity        TEXT    DEFAULT 'medium',
    source          TEXT    DEFAULT 'claude',
    resolved        INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uncertainty_id  INTEGER REFERENCES uncertainties(id),
    parish          TEXT,
    year            INTEGER,
    statement_type  TEXT,
    field_path      TEXT,
    action          TEXT,           -- 'confirmed' | 'corrected' | 'skipped'
    corrected_value TEXT,
    user_note       TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_unc_job    ON uncertainties(job_id);
CREATE INDEX IF NOT EXISTS idx_unc_parish ON uncertainties(parish, year);
CREATE INDEX IF NOT EXISTS idx_cor_parish ON corrections(parish, year);
"""


def _conn(db_path: str) -> sqlite3.Connection:
    c = sqlite3.connect(db_path, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db(db_path: str):
    c = _conn(db_path)
    c.executescript(_SCHEMA)
    c.commit()
    c.close()


def save_uncertainty(db_path, job_id, parish, year, stmt_type,
                     field_path=None, reason=None, extracted_value=None,
                     alternative_value=None, page_number=None, text_snippet=None,
                     severity="medium", source="claude") -> int:
    c = _conn(db_path)
    cur = c.execute("""
        INSERT INTO uncertainties
            (job_id, parish, year, statement_type, field_path, reason,
             extracted_value, alternative_value, page_number, text_snippet, severity, source)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (job_id, parish, year, stmt_type, field_path, reason,
          str(extracted_value) if extracted_value is not None else None,
          str(alternative_value) if alternative_value is not None else None,
          page_number, text_snippet, severity, source))
    row_id = cur.lastrowid
    c.commit(); c.close()
    return row_id


def save_correction(db_path, uncertainty_id, parish, year, stmt_type,
                    field_path, action, corrected_value=None, note=None):
    c = _conn(db_path)
    c.execute("""
        INSERT INTO corrections
            (uncertainty_id, parish, year, statement_type, field_path, action, corrected_value, user_note)
        VALUES (?,?,?,?,?,?,?,?)
    """, (uncertainty_id, parish, year, stmt_type, field_path, action, corrected_value, note))
    c.execute("UPDATE uncertainties SET resolved=1 WHERE id=?", (uncertainty_id,))
    c.commit(); c.close()


def get_uncertainties_for_job(db_path, job_id):
    c = _conn(db_path)
    rows = c.execute("""
        SELECT u.*,
               cor.action        AS cor_action,
               cor.corrected_value AS cor_value,
               cor.user_note     AS cor_note
        FROM uncertainties u
        LEFT JOIN corrections cor ON cor.uncertainty_id = u.id
        WHERE u.job_id = ?
        ORDER BY u.statement_type, u.parish, u.severity DESC, u.id
    """, (job_id,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_corrections_for_parish(db_path, parish, year, stmt_type):
    """Returns past confirmed/corrected items to inject as examples into future prompts."""
    c = _conn(db_path)
    rows = c.execute("""
        SELECT cor.field_path, cor.action, cor.corrected_value, cor.user_note,
               u.extracted_value, u.reason
        FROM corrections cor
        JOIN uncertainties u ON u.id = cor.uncertainty_id
        WHERE cor.parish=? AND cor.year=? AND cor.statement_type=?
          AND cor.action IN ('corrected','confirmed')
        ORDER BY cor.created_at DESC
        LIMIT 20
    """, (parish, year, stmt_type)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def save_statement_note(db_path, parish, year, stmt_type, note):
    """Save a free-text statement-level note (no specific field) to inject into future prompts."""
    c = _conn(db_path)
    c.execute("""
        INSERT INTO corrections
            (uncertainty_id, parish, year, statement_type, field_path, action, corrected_value, user_note)
        VALUES (NULL,?,?,?,NULL,'note',NULL,?)
    """, (parish, year, stmt_type, note))
    c.commit(); c.close()


def get_statement_notes(db_path, parish, year, stmt_type):
    """Return the most recent statement-level notes for this parish/statement (newest first)."""
    c = _conn(db_path)
    rows = c.execute("""
        SELECT user_note FROM corrections
        WHERE parish=? AND year=? AND statement_type=? AND action='note'
          AND field_path IS NULL AND user_note IS NOT NULL
        ORDER BY created_at DESC LIMIT 5
    """, (parish, year, stmt_type)).fetchall()
    c.close()
    return [r["user_note"] for r in rows]


def get_parish_stats(db_path):
    """Aggregate uncertainty counts — used by the analytics view."""
    c = _conn(db_path)
    rows = c.execute("""
        SELECT parish, year, statement_type, severity,
               COUNT(*)       AS total,
               SUM(resolved)  AS resolved
        FROM uncertainties
        GROUP BY parish, year, statement_type, severity
        ORDER BY total DESC
    """).fetchall()
    c.close()
    return [dict(r) for r in rows]


def save_coded_data(db_path, year, coded_dir, parishes, total_flags,
                    comparison_flags, coding_check_flags):
    """Record a completed comparison run."""
    c = _conn(db_path)
    c.execute("""
        INSERT INTO coded_runs
            (year, coded_dir, parishes, total_flags, comparison_flags, coding_check_flags)
        VALUES (?,?,?,?,?,?)
    """, (year, coded_dir, json.dumps(parishes),
          total_flags, comparison_flags, coding_check_flags))
    c.commit(); c.close()


def get_training_stats(db_path):
    """Return per-year training stats for the Training tab."""
    c = _conn(db_path)
    # Coded runs
    runs = c.execute("""
        SELECT year, MAX(run_at) as last_run,
               SUM(total_flags) as total_flags,
               SUM(comparison_flags) as comparison_flags,
               SUM(coding_check_flags) as coding_check_flags,
               parishes
        FROM coded_runs
        GROUP BY year
        ORDER BY year DESC
    """).fetchall()
    # Uncertainty counts by year/source
    unc = c.execute("""
        SELECT year, source,
               COUNT(*) as total,
               SUM(resolved) as resolved
        FROM uncertainties
        WHERE source IN ('comparison','coding_check')
        GROUP BY year, source
    """).fetchall()
    c.close()

    # Build result
    unc_map = {}
    for r in unc:
        key = (r["year"], r["source"])
        unc_map[key] = {"total": r["total"], "resolved": r["resolved"]}

    result = []
    for r in runs:
        year = r["year"]
        parishes = json.loads(r["parishes"] or "[]")
        result.append({
            "year": year,
            "last_run": r["last_run"],
            "parishes_covered": len(parishes),
            "parish_list": parishes,
            "total_flags": r["total_flags"] or 0,
            "comparison_flags": r["comparison_flags"] or 0,
            "coding_check_flags": r["coding_check_flags"] or 0,
            "comparison_resolved": (unc_map.get((year, "comparison")) or {}).get("resolved", 0),
            "coding_check_resolved": (unc_map.get((year, "coding_check")) or {}).get("resolved", 0),
        })
    return result
