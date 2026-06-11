"""
PDF text extraction and statement page detection.
Handles all 4 statement types across different auditing firm layouts.
"""
import re
import pdfplumber


# MDA (Management Discussion and Analysis) pages look like financial statements
# but contain narrative text. They always mention "management's discussion".
MDA_EXCLUDE = ["management's discussion", "management discussion", "managements discussion"]

# Pages that ARE the notes section have "notes to" near the top as a title.
# We detect this differently (see _is_notes_page), not via simple substring.

def _is_notes_page(text: str) -> bool:
    """True if this page is the Notes to Financial Statements section (not just a footer)."""
    # The notes title is always within the first ~200 chars (parish name + title + date).
    # We check multiple patterns to handle OCR garbling of "Financial" (e.g. "Einancial").
    first400 = text[:400]
    very_top = text[:200]   # notes title is always here; footnote references are at the bottom
    return (
        "notes to financial" in first400
        or "notes to the financial" in first400
        or "notes to the basic" in first400      # "Notes to the Basic Financial Statements"
        or "notes to basic" in first400
        # Catch OCR garbling (e.g. "Notes to the Einancial Statements", "Notes to Finwial Statements"):
        # use first 150 chars (title area only) so CBS footer references aren't matched
        or ("notes to the" in very_top and "statements" in very_top)
        or ("notes to" in text[:150] and "statements" in text[:150])
    )


# Keywords that identify each statement type
STATEMENT_PATTERNS = {
    "cbs": {
        "require_any": [
            ["balance sheet", "governmental fund"],          # normal
            ["balance sheet", "governmental activities", "assets"],  # large cities
            ["balance sheet", "governmental fn"],            # OCR corruption: "fnnds", "fnds"
            ["balance sheet", "govemmental fund"],           # OCR drop of 'r': "Govemmental"
            ["balance sheet", "govemmental fn"],             # OCR double-drop
            ["balance sheet", "major fund", "assets"],       # "major funds" layout
            # OCR corruption variants ---
            ["balance sheet", "eund"],                       # F→e: "Governmental Eunds" (Union, Claiborne)
            ["balance sheet", "ernmental fund"],             # apostrophe/space garble: "Gon'ernmental Funds" (West Carroll)
            ["balance sheel", "governmental fund"],          # t→l: "Balance Sheel" (Cameron)
            ["balance sheel", "ernmental fund"],             # combined: "balance sheel" + garbled "governmental"
            ["balance. sheet", "governmental fund"],         # period inserted: "Balance. Sheet" (Lafourche)
            ["balancesheet", "governmental fund"],           # merged: "BalanceSheet" (St. John the Baptist)
            ["balanc e sheet", "ernmental fund"],            # space-split OCR: "Balanc E Sheet" (Caldwell)
            ["balance sheet", "govemmenia"],                 # heavy garble of "Governmental" (St. Mary)
            ["governmental fund", "comparative totals", "assets"],  # Winn-style CBS with no "balance sheet" in title
        ],
        "exclude": ["combining balance sheet", "combining statement",
                    "combining balance. sheet",           # OCR period-insert in "combining balance sheet"
                    "balance sheet nonmajor",             # consolidating/combining BS title for nonmajor funds
                    "reconciliation", "reconcl",          # "reconcl" catches OCR "reconclliatioh"
                    "discretely presented",               # component unit section (not primary CBS)
                    "presented separately",               # MDA/intro narrative pages (Bienville-type)
                    "fiduciary"]
                   + MDA_EXCLUDE,
    },
    "soa": {
        # "functions/programs" is the definitive column header of the SOA table
        # Fallbacks handle OCR artifacts in large-city CAFRs
        "require_any": [
            ["functions/programs"],
            ["statement of activities", "program revenues"],
            ["statement of activities", "charges for"],
            ["net (expense)", "program revenues"],
            ["net (expense) revenue", "general revenues"],
            # OCR-garbled variants:
            ["statement of activities", "net (expense)"],    # Claiborne: "program reveivues" garble
            ["statement of activi", "program revenu"],       # covers "activicies"/"activties" + "revenoes"
            # Iberville: "revenoes" has 'o' not 'u' (so "program revenu" fails), but "total general revenues"
            # is readable. "charges f" (= "charges for [services]") distinguishes real SOA from MDA
            # condensed tables that also mention "general revenues" and "governmental activities".
            ["statement of activi", "general revenues", "charges f"],
        ],
        "exclude": MDA_EXCLUDE,
    },
    "sona": {
        # "statement of net pos" catches both "position" and "postion" (PDF typo)
        "require_any": [
            ["statement of net pos"],
            ["statement of net assets"],
        ],
        # "condensed" excludes MDA summary tables that reprint truncated SONA data
        "exclude": ["reconciliation", "condensed", "changes in net"] + MDA_EXCLUDE,
    },
    "ca": {
        # Primary patterns for CA schedules as separate primary financial statements.
        # "statement of net pos" / "statement of net assets" in the exclude list prevents
        # SONA pages from matching (they have "capital assets, net of accumulated depreciation"
        # as a line item but their page title fires the exclude).
        "require_any": [
            ["capital assets", "not being depreciated"],   # standard section header (non-depreciable section)
            ["capital assets", "depreciable"],              # alternate "depreciable assets" section header
            ["capital assets", "accumulated depreciation"], # many schedules use accum depr column headers
        ],
        "exclude": ["policy", "policies", "summary of significant",
                    "fiduciary funds", "internal service funds",
                    # SONA pages: excluded by their title ("statement of net position/assets")
                    "statement of net pos", "statement of net assets",
                    # Reconciliation pages list capital asset amounts as adjustments
                    "reconciliation",
                    # MDA section headers for capital asset discussion (no main MDA header on these pages)
                    # Covers both "Capital Asset Administration" and "Capital Asset and Debt Administration"
                    "capital asset administration",
                    "debt administration",
                    # Net position narrative: "invested in capital assets, net of related debt" appears
                    # in SONA/MDA pages listing net position components, never in actual CA schedules
                    "invested in capital assets",
                    # Fiduciary fund statements list capital assets as a line item but are not CA schedules
                    "fiduciary"] + MDA_EXCLUDE,
    },
}

# Extra confirmation keywords that must appear somewhere in ±3 page window
CONFIRMATION = {
    "cbs": ["assets", "liabilities", "fund balance"],
    "soa": ["expenses", "general revenues"],
    "sona": ["primary", "assets", "liabilities"],
    "ca": ["depreciation", "beginning balance", "increases"],
}


def _matches_any(text: str, patterns: dict, allow_notes: bool = False) -> bool:
    """Check if text matches the pattern: any require_any group must fully match,
    all excludes must be absent, and the page must not be a notes page."""
    if not allow_notes and _is_notes_page(text):
        return False
    # Skip Table of Contents pages — they list every statement title but contain no actual data.
    # Two indicators:
    # (a) The page title says "table of contents"
    # (b) The page uses dotted-line leaders (10+ consecutive periods) to connect statement names
    #     to page numbers — a TOC formatting convention that never appears in actual statements.
    if "table of contents" in text[:400] or ".........." in text:
        return False
    for excl in patterns.get("exclude", []):
        if excl in text:
            return False
    for req_group in patterns.get("require_any", []):
        if all(kw in text for kw in req_group):
            return True
    return False


def _page_text(page) -> str:
    # Replace newlines with spaces so multi-line phrases like
    # "Balance Sheet\nNonmajor Governmental Funds" can be matched as a substring.
    return (page.extract_text() or "").lower().replace('\n', ' ')


def _matches(text: str, patterns: dict) -> bool:
    for kw in patterns["require"]:
        if kw not in text:
            return False
    for kw in patterns.get("exclude", []):
        if kw in text:
            return False
    return True


def find_statement_pages(pdf_path: str) -> dict[str, list[int]]:
    """
    Returns dict mapping statement type → list of 0-based page indices
    that together contain the full statement text.
    """
    result = {"cbs": [], "soa": [], "sona": [], "ca": []}

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        n = len(pages)
        texts = [_page_text(p) for p in pages]

        # Capital assets note-search fallback patterns (stricter, allowed in notes section)
        CA_NOTES_PATTERNS = [
            ["capital assets", "accumulated depreciation", "beginning"],
            ["capital assets", "beginning balance"],
            ["note", "capital assets", "beginning"],
            # Alternate column header styles (no "beginning" keyword).
            # Require "not being depreciated" to avoid false positives on Note 1 capital asset
            # accounting policy pages, which also mention "accumulated depreciation" + "ending".
            ["capital assets", "accumulated depreciation", "additions", "not being depreciated"],   # "Additions" column (WBR)
            ["capital assets", "accumulated depreciation", "ending", "not being depreciated"],      # "Beguming/Ending" OCR (St. Helena)
            ["capital assets", "accumulated depreciation", "not being depreciated", "increases"],   # "Increases/Decreases" columns (Washington)
            ["capital assets", "accumulated depreciation", "cost at december"],                      # Iberville: date-based columns "Cost at December 31, 20XX"
            # Lincoln: columns labeled "2012 Balance / Additions / Disposals / 2013 Balance" (no "beginning" keyword)
            # "capital asset" (no 's') + depreciable + additions + disposals uniquely identifies the CA schedule
            ["capital asset", "depreciable", "additions", "disposals"],
            # Assumption-style: "Note I - Capital Assets / Additions / Deletions" columns (no "beginning" or "balance" keyword)
            # "deletions" (vs "disposals" or "decreases") is specific to this format; combined with "additions" identifies the table
            ["capital assets", "additions", "deletions"],
        ]

        for stmt_type, patterns in STATEMENT_PATTERNS.items():
            # Find the anchor page (first match that passes all pattern checks)
            anchor = None
            for i, text in enumerate(texts):
                if _matches_any(text, patterns):
                    # Confirm at least one confirmation keyword exists nearby (±3 pages)
                    window = " ".join(texts[max(0, i-1):min(n, i+4)])
                    if any(kw in window for kw in CONFIRMATION[stmt_type]):
                        anchor = i
                        break

            # CA fallback: if no CA found, search inside Notes with stricter patterns
            if anchor is None and stmt_type == "ca":
                for i, text in enumerate(texts):
                    if not _is_notes_page(text):
                        continue  # only look in notes pages for this fallback
                    # Check stricter CA note patterns
                    for req_group in CA_NOTES_PATTERNS:
                        if all(kw in text for kw in req_group):
                            window = " ".join(texts[max(0, i-1):min(n, i+4)])
                            if any(kw in window for kw in CONFIRMATION["ca"]):
                                anchor = i
                                break
                    if anchor is not None:
                        break

            if anchor is None:
                continue

            # SOA spans more pages (functions + general revenues sections)
            max_continuation = 8 if stmt_type == "soa" else 6

            # Collect anchor + continuation pages
            collected = [anchor]
            blank_streak = 0
            for j in range(anchor + 1, min(n, anchor + max_continuation + 1)):
                t = texts[j]
                char_count = len(t)
                # Stop on a clearly new major section
                new_section = any([
                    "independent auditor" in t,
                    "management's discussion" in t,
                    # Use _is_notes_page (checks TITLE area only) instead of bare substring,
                    # so pages with a "see notes to financial statements" FOOTER don't stop early.
                    _is_notes_page(t),
                    "required supplementary" in t,
                    ("combining balance sheet" in t and stmt_type == "cbs"),
                    ("combining" in t and "nonmajor" in t and stmt_type == "cbs"),
                    "table of contents" in t,
                    # Stop CBS continuation at the reconciliation page (comes right after the CBS)
                    ("reconciliation of" in t and stmt_type == "cbs"),
                    # Stop SOA at the next completely different statement.
                    # Check title area (first 300 chars) for "balance sheet" to catch all CBS formats
                    # including consolidated-government layouts that don't say "governmental fund".
                    ("balance sheet" in t[:300] and stmt_type == "soa"),
                    ("balance sheel" in t[:300] and stmt_type == "soa"),   # OCR t→l variant
                    ("balance. sheet" in t[:300] and stmt_type == "soa"),  # OCR period variant
                    # Stop SONA/CA continuations at other primary financial statements.
                    # Without these, every page until the Notes title would be collected
                    # (since financial statement pages only have the notes FOOTER, not title).
                    ("functions/programs" in t and stmt_type in ("sona", "ca")),          # SOA
                    ("statement of activities" in t[:300] and stmt_type in ("sona", "ca")),  # SOA title
                    ("statement of net pos" in t[:300] and stmt_type == "ca"),             # SONA title
                    ("balance sheet" in t and "governmental fund" in t and stmt_type in ("sona", "ca")),  # CBS
                    ("balance sheet" in t and "ernmental fund" in t and stmt_type in ("sona", "ca")),     # CBS OCR
                ])
                if new_section:
                    break
                if char_count > 150:
                    collected.append(j)
                    blank_streak = 0
                elif char_count < 50:
                    blank_streak += 1
                    if blank_streak >= 2:
                        break  # two consecutive blank pages = end of section

            result[stmt_type] = collected

    return result


def extract_statement_text(pdf_path: str, page_indices: list[int]) -> str:
    """Concatenates text from specified pages."""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in page_indices:
            text = pdf.pages[i].extract_text() or ""
            if text.strip():
                parts.append(f"[Page {i+1}]\n{text}")
    return "\n\n".join(parts)


def detect_in_thousands(text: str) -> bool:
    """Returns True if the statement reports in thousands of dollars."""
    t = text.lower()
    return "in thousands" in t or "thousands of dollars" in t


def get_parish_name(pdf_path: str) -> str:
    """Extract parish name from the PDF filename."""
    import os
    return os.path.splitext(os.path.basename(pdf_path))[0]


def get_all_statement_texts(pdf_path: str) -> dict[str, str | None]:
    """
    Main entry point. Returns dict with raw text for each statement type.
    None if the statement wasn't found.
    """
    page_map = find_statement_pages(pdf_path)
    result = {}
    for stmt_type, pages in page_map.items():
        if pages:
            result[stmt_type] = extract_statement_text(pdf_path, pages)
        else:
            result[stmt_type] = None
    return result
