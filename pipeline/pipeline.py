"""
Main pipeline orchestrator.

Usage:
    python pipeline.py --year 2013 --input ./2013_source/2013 --output ./output

Processes all PDFs in the input folder and produces 4 Excel files in the output folder.
Caches extracted JSON so re-runs don't re-call the API.
"""
import argparse
import json
import os
import sys

from extractor import get_all_statement_texts, extract_statement_text, get_parish_name
from parse import extract_all_statements
from validate import (
    validate_parish, write_quality_report_csv,
    write_quality_report_excel_tab, get_validation_cells,
)
from write_excel import get_or_create_workbook, add_parish_to_workbook, save_workbook, write_parish_combined_workbook


def load_manual_pages(pipeline_dir: str) -> dict:
    """Load manual_pages.json from the project root (parent of pipeline dir)."""
    project_root = os.path.dirname(pipeline_dir)
    path = os.path.join(project_root, "manual_pages.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        # Strip the _comment key if present
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return {}


def apply_manual_overrides(pdf_path: str, parish: str, manual_pages: dict) -> dict[str, str | None] | None:
    """
    If manual_pages has an entry for this parish, extract text directly using
    the hardcoded page numbers (1-indexed in JSON → 0-indexed for pdfplumber).
    Returns a texts dict like get_all_statement_texts, or None if no override.
    """
    if parish not in manual_pages:
        return None
    overrides = manual_pages[parish]
    result = {}
    for stmt_type in ["cbs", "soa", "sona", "ca"]:
        if stmt_type in overrides:
            pages_1indexed = overrides[stmt_type]
            pages_0indexed = [p - 1 for p in pages_1indexed]
            text = extract_statement_text(pdf_path, pages_0indexed)
            result[stmt_type] = text if text.strip() else None
        else:
            result[stmt_type] = None
    return result


def run_pipeline(input_dir: str, year: int, output_dir: str, cache_dir: str,
                 only_parishes: list[str] | None = None,
                 skip_cache: bool = False,
                 progress_callback: callable = print):
    """
    progress_callback: called with each status string. Defaults to print()
    so CLI behaviour is unchanged. Pass a custom callable to capture messages
    (e.g. push them into a queue for SSE streaming in the web app).
    """
    log = progress_callback

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    # Collect PDF files
    pdfs = sorted([
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.lower().endswith(".pdf")
    ])

    if not pdfs:
        log(f"No PDFs found in {input_dir}")
        return

    if only_parishes:
        pdfs = [p for p in pdfs if get_parish_name(p) in only_parishes]
        log(f"Filtered to {len(pdfs)} parish(es): {only_parishes}")

    # Load manual page overrides (for parishes where OCR is too garbled for detection)
    pipeline_dir = os.path.dirname(os.path.abspath(__file__))
    manual_pages = load_manual_pages(pipeline_dir)
    if manual_pages:
        log(f"Manual page overrides loaded for: {', '.join(manual_pages.keys())}")

    log(f"Processing {len(pdfs)} parishes for year {year}...")
    log(f"  Input:  {input_dir}")
    log(f"  Output: {output_dir}")
    log(f"  Cache:  {cache_dir}")
    log("")

    # Open/create workbooks once
    workbooks = {}
    for stmt_type in ["cbs", "soa", "sona", "ca"]:
        wb, path = get_or_create_workbook(output_dir, stmt_type, year)
        workbooks[stmt_type] = (wb, path)

    # Collect validation results for quality report (populated in main loop)
    parish_validations = []

    # Process each parish
    for i, pdf_path in enumerate(pdfs, 1):
        parish = get_parish_name(pdf_path)
        log(f"[{i:2d}/{len(pdfs)}] {parish}")

        cache_file = os.path.join(cache_dir, f"{parish}_{year}.json")

        # Try cache first
        if not skip_cache and os.path.exists(cache_file):
            log(f"  Loading from cache...")
            with open(cache_file) as f:
                results = json.load(f)
        else:
            # Extract text from PDF
            log(f"  Extracting pages from PDF...")
            try:
                manual = apply_manual_overrides(pdf_path, parish, manual_pages)
                if manual is not None:
                    log(f"  [MANUAL] Using hardcoded page overrides for {parish}")
                    texts = manual
                else:
                    texts = get_all_statement_texts(pdf_path)
            except Exception as e:
                log(f"  [ERROR] PDF extraction failed: {e}")
                continue

            # Call Claude API
            log(f"  Calling Claude API...")
            results = extract_all_statements(texts, parish, year)

            # Save to cache
            with open(cache_file, "w") as f:
                json.dump(results, f, indent=2)
            log(f"  Cached to {os.path.basename(cache_file)}")

        # Validate extracted data
        log(f"  Validating...")
        try:
            pv = validate_parish(parish, year, results)
            parish_validations.append(pv)
            status_summary = {
                "PASS": "✓", "WARNING": "⚠", "REVIEW REQUIRED": "!", "FAILED": "✗",
            }.get(pv.overall_status, "?")
            log(f"  [{status_summary}] Validation: {pv.overall_status}")
            for stmt_type, sv in pv.statements.items():
                if sv.status != "PASS":
                    errors = "; ".join(
                        c.name for c in sv.checks if not c.passed
                    )
                    log(f"    {stmt_type.upper()}: {sv.status}"
                        + (f" — {errors}" if errors else ""))
        except Exception as exc:
            log(f"  [ERROR] Validation failed: {exc}")
            pv = None

        # Write to Excel
        log(f"  Writing to Excel...")
        for stmt_type in ["cbs", "soa", "sona", "ca"]:
            data = results.get(stmt_type)
            if data:
                try:
                    wb, path = workbooks[stmt_type]
                    add_parish_to_workbook(wb, stmt_type, data, year)
                except Exception as e:
                    log(f"    [ERROR] Excel write failed for {stmt_type}: {e}")
            else:
                log(f"    [SKIP] No data for {stmt_type}")

        log("")

    # ── Add Quality Report tab before saving ─────────────────────────────────
    if parish_validations:
        log("Adding Quality Report tabs...")
        # Build index for quick lookup: parish → ParishValidation
        pv_index = {pv.parish: pv for pv in parish_validations}

        for stmt_type, (wb, path) in workbooks.items():
            try:
                write_quality_report_excel_tab(wb, parish_validations, manual_pages, year)
            except Exception as exc:
                log(f"  [ERROR] Quality tab failed for {stmt_type}: {exc}")

    # ── Save all statement workbooks ──────────────────────────────────────────
    log("Saving Excel files...")
    saved_files = []
    for stmt_type, (wb, path) in workbooks.items():
        try:
            # Move Cross Sectional and Quality Report to last positions
            sheetnames = wb.sheetnames
            for special in ["cross sectional", "governmental cross sectional", "quality report"]:
                matches = [s for s in sheetnames if s.lower() == special]
                for m in matches:
                    wb.move_sheet(m, offset=len(wb.sheetnames))
            save_workbook(wb, path)
            saved_files.append(os.path.basename(path))
            log(f"  Saved: {os.path.basename(path)}")
        except Exception as e:
            log(f"  [ERROR] Save failed for {stmt_type}: {e}")

    # ── Per-parish combined workbooks (CBS + SOA + SONA + CA in one file) ────
    log("Building parish workbooks...")
    parish_files = []
    pv_index = {pv.parish: pv for pv in parish_validations}

    for pdf_path in pdfs:
        parish = get_parish_name(pdf_path)
        cache_file = os.path.join(cache_dir, f"{parish}_{year}.json")
        if not os.path.exists(cache_file):
            continue
        with open(cache_file) as f:
            results = json.load(f)
        fname = write_parish_combined_workbook(
            output_dir, parish, results, year,
            parish_validation=pv_index.get(parish),
            manual_pages=manual_pages,
        )
        if fname:
            parish_files.append(fname)
            log(f"  Saved: {fname}")

    # ── Quality report CSV ────────────────────────────────────────────────────
    if parish_validations:
        log("")
        log("Writing quality report CSV...")
        try:
            csv_path = write_quality_report_csv(
                parish_validations, output_dir, manual_pages, year
            )
            log(f"  Saved: {os.path.basename(csv_path)}")
        except Exception as exc:
            log(f"  [ERROR] Quality report CSV failed: {exc}")

        # Summary counts
        statuses = [pv.overall_status for pv in parish_validations]
        n_pass    = statuses.count("PASS")
        n_warn    = statuses.count("WARNING")
        n_review  = statuses.count("REVIEW REQUIRED")
        n_failed  = statuses.count("FAILED")
        log("")
        log(f"  Parish summary: {n_pass} PASS | {n_warn} WARNING | "
            f"{n_review} REVIEW REQUIRED | {n_failed} FAILED")

    log("")
    log("Done.")
    return {"statement_files": saved_files, "parish_files": parish_files}


def main():
    parser = argparse.ArgumentParser(description="Louisiana Parish Audit Pipeline")
    parser.add_argument("--year", type=int, required=True, help="Fiscal year (e.g. 2013)")
    parser.add_argument("--input", required=True, help="Folder containing parish PDFs")
    parser.add_argument("--output", required=True, help="Output folder for Excel files")
    parser.add_argument("--cache", default=None, help="Cache folder for JSON results (default: output/cache)")
    parser.add_argument("--parishes", nargs="+", help="Process only specific parishes by name")
    parser.add_argument("--skip-cache", action="store_true", help="Ignore cached results, re-extract")

    args = parser.parse_args()
    cache_dir = args.cache or os.path.join(args.output, "cache")

    run_pipeline(
        input_dir=args.input,
        year=args.year,
        output_dir=args.output,
        cache_dir=cache_dir,
        only_parishes=args.parishes,
        skip_cache=args.skip_cache,
    )


if __name__ == "__main__":
    main()
