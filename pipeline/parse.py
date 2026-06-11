"""
Claude API calls for extracting structured data from PDF text.
One call per statement type per parish.
"""
import json
import os
import time
import anthropic
from dotenv import load_dotenv
from prompts import CBS_PROMPT, SOA_PROMPT, SONA_PROMPT, CA_PROMPT

# Load .env from the same directory as this script
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_SCRIPT_DIR, ".env"), override=True)

_client = None

def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


PROMPT_MAP = {
    "cbs": CBS_PROMPT,
    "soa": SOA_PROMPT,
    "sona": SONA_PROMPT,
    "ca": CA_PROMPT,
}

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 4096

# CBS requires more tokens when there are many funds
MAX_TOKENS_CBS = 8192


def _scale_value(v, factor: int):
    """Multiply a numeric value by factor; leave None/null as-is."""
    if isinstance(v, (int, float)) and v is not None:
        return int(v * factor)
    return v


def _scale_dict(d: dict, factor: int) -> dict:
    """Recursively multiply all numeric leaf values in a dict/list by factor."""
    if isinstance(d, dict):
        return {k: _scale_dict(v, factor) for k, v in d.items()}
    elif isinstance(d, list):
        return [_scale_dict(item, factor) for item in d]
    elif isinstance(d, (int, float)) and d is not None:
        return int(d * factor)
    return d


def apply_thousands_scaling(data: dict) -> dict:
    """
    If Claude flagged in_thousands=True, multiply all numeric values by 1000.
    Skips 'parish', 'year', 'in_thousands', and 'funds' keys (metadata).
    """
    if not data or not data.get("in_thousands"):
        return data
    skip_keys = {"parish", "year", "in_thousands", "funds"}
    result = dict(data)
    for k, v in data.items():
        if k not in skip_keys:
            result[k] = _scale_dict(v, 1000)
    return result


def _build_corrections_note(parish: str, year: int, stmt_type: str, db_path: str | None) -> str:
    """
    Build a preamble of human instructions for this parish/statement:
      1. Statement-level free-text notes (e.g. "comparative PDF — use left column")
      2. Field-level confirmed/corrected values
    Statement notes are injected FIRST so Claude sees the high-level context before
    the specific field overrides.
    Returns empty string if nothing to inject, or db_path is None.
    """
    if not db_path:
        return ""
    try:
        from feedback import get_corrections_for_parish, get_statement_notes
        stmt_notes = get_statement_notes(db_path, parish, year, stmt_type)
        corrections = get_corrections_for_parish(db_path, parish, year, stmt_type)
        if not stmt_notes and not corrections:
            return ""
        lines = [
            f"IMPORTANT — Human reviewer instructions for {parish} {year} {stmt_type.upper()}:",
            "(These override any conflicting interpretation of the PDF text.)",
        ]
        if stmt_notes:
            lines.append("")
            lines.append("Statement-level context from auditor:")
            for note in stmt_notes:
                lines.append(f"  ★ {note}")
        if corrections:
            lines.append("")
            lines.append("Prior field-level corrections (human-verified):")
            for c in corrections:
                field = c.get("field_path", "unknown field")
                correct = c.get("corrected_value") or c.get("extracted_value")
                action = c.get("action", "")
                note = c.get("user_note") or c.get("reason") or ""
                if action == "corrected":
                    lines.append(f"  • {field} = {correct}  [human correction{': ' + note if note else ''}]")
                elif action == "confirmed":
                    lines.append(f"  • {field} = {correct}  [confirmed correct by human reviewer]")
        return "\n".join(lines) + "\n\n"
    except Exception:
        return ""


def extract_statement(stmt_type: str, text: str, parish: str, year: int,
                      db_path: str | None = None) -> dict | None:
    """
    Call Claude to extract structured data from a statement's raw text.
    Returns parsed JSON dict, or None on failure.
    """
    if not text or not text.strip():
        print(f"  [SKIP] No text for {stmt_type} ({parish})")
        return None

    prompt = PROMPT_MAP[stmt_type]
    # Trim text to avoid token overflows (keep ~12k chars which covers most balance sheets)
    text_trimmed = text[:14000]

    # Inject prior human corrections as few-shot context
    corrections_note = _build_corrections_note(parish, year, stmt_type, db_path)
    user_message = corrections_note + prompt + text_trimmed

    try:
        tokens = MAX_TOKENS_CBS if stmt_type == "cbs" else MAX_TOKENS
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=tokens,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if Claude adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        # Inject parish/year in case Claude misread them
        data["parish"] = parish
        data["year"] = year
        # Apply thousands scaling if flagged
        data = apply_thousands_scaling(data)
        return data

    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON parse failed for {stmt_type} ({parish}): {e}")
        print(f"  Raw response snippet: {raw[:300] if 'raw' in dir() else 'N/A'}")
        return None
    except Exception as e:
        print(f"  [ERROR] API call failed for {stmt_type} ({parish}): {e}")
        return None


def extract_all_statements(
    texts: dict[str, str | None],
    parish: str,
    year: int,
    delay: float = 0.5,
    db_path: str | None = None,
) -> dict[str, dict | None]:
    """
    Extract all 4 statement types for one parish.
    texts: dict from extractor.get_all_statement_texts()
    db_path: optional path to feedback.db for injecting prior corrections.
    """
    results = {}
    for stmt_type in ["cbs", "soa", "sona", "ca"]:
        text = texts.get(stmt_type)
        print(f"  Extracting {stmt_type.upper()}...", end=" ", flush=True)
        result = extract_statement(stmt_type, text, parish, year, db_path=db_path)
        results[stmt_type] = result
        print("OK" if result else "FAILED")
        if delay:
            time.sleep(delay)
    return results
