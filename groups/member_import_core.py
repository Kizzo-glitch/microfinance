"""
Fedha-Grow — bulk member import (parse + validate + classify)
============================================================
Reads an uploaded .xlsx of members, validates each row, and classifies every
row as NEW / EXISTING (dedupe by phone) / ERROR — WITHOUT writing anything.
This is the "preview" half: it produces a report the agent confirms before any
records are created.

Design principles held here:
  * Creates PROFILES, not accounts — each person still activates + consents.
  * Dedupe by phone — an existing borrower links, never duplicates.
  * Validate every row; a bad row is reported, not silently imported.
  * Nothing is written during parse/validate — only on the confirm step.
"""

from dataclasses import dataclass, field
import re
import openpyxl

# The fixed template columns (header row must match these, case-insensitive).
# Keep in sync with the downloadable template and BorrowerMiniForm.
EXPECTED_COLUMNS = [
    "full_name", "phone_number", "email",
    "id_number", "date_of_birth", "income", "gender",
    "employer_name", "employment_position",
]
REQUIRED_COLUMNS = ["full_name", "phone_number"]   # the bare minimum per row


@dataclass
class RowResult:
    row_number: int                 # 1-based spreadsheet row (incl header offset)
    data: dict
    classification: str             # "new" | "existing" | "error"
    errors: list = field(default_factory=list)
    existing_borrower_id: int = None
    existing_has_account: bool = False

    @property
    def ok(self) -> bool:
        return self.classification != "error"


@dataclass
class ImportPreview:
    rows: list
    header_ok: bool = True
    header_error: str = ""

    @property
    def new_count(self):      return sum(1 for r in self.rows if r.classification == "new")
    @property
    def existing_count(self): return sum(1 for r in self.rows if r.classification == "existing")
    @property
    def error_count(self):    return sum(1 for r in self.rows if r.classification == "error")
    @property
    def importable(self):     return [r for r in self.rows if r.ok]


# ---- helpers ----
_PHONE_RE = re.compile(r"^\+?\d[\d\s\-]{6,}$")

def _clean_phone(raw) -> str:
    s = str(raw or "").strip()
    s = s.replace(" ", "").replace("-", "")
    return s

def _valid_phone(phone: str) -> bool:
    return bool(_PHONE_RE.match(phone))


def parse_workbook(file_obj) -> ImportPreview:
    """Read the xlsx into rows. Does NOT hit the DB — pure parse + shape check."""
    try:
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        return ImportPreview(rows=[], header_ok=False,
                             header_error=f"Could not read the file: {exc}")

    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    # header row
    try:
        header = next(rows_iter)
    except StopIteration:
        return ImportPreview(rows=[], header_ok=False, header_error="The file is empty.")

    header_map = {}
    for idx, col in enumerate(header):
        if col is None:
            continue
        key = str(col).strip().lower().replace(" ", "_")
        header_map[key] = idx

    missing_required = [c for c in REQUIRED_COLUMNS if c not in header_map]
    if missing_required:
        return ImportPreview(rows=[], header_ok=False,
                             header_error=f"Missing required column(s): {', '.join(missing_required)}. "
                                          f"Download and use the template.")

    results = []
    for i, raw_row in enumerate(rows_iter, start=2):   # start=2: row 1 was header
        data = {}
        for col_key, col_idx in header_map.items():
            if col_key in EXPECTED_COLUMNS:
                val = raw_row[col_idx] if col_idx < len(raw_row) else None
                data[col_key] = ("" if val is None else str(val).strip())

        # skip fully-blank rows silently
        if not any(data.values()):
            continue

        data["phone_number"] = _clean_phone(data.get("phone_number"))
        results.append(RowResult(row_number=i, data=data, classification="pending"))

    return ImportPreview(rows=results)


def classify_rows(preview: ImportPreview, group):
    """
    Second pass — validate each row and dedupe against existing borrowers and
    against this group's current members. Sets classification + errors. Hits
    the DB (read-only). Also flags duplicate phones WITHIN the file.
    """
    from borrowers.models import BorrowerProfile

    seen_phones = {}   # phone -> first row_number in this file

    # who's already an active member of this group (so we don't re-add)
    group_member_phones = set(
        group.memberships.filter(status="active")
        .values_list("borrower__phone_number", flat=True))

    for r in preview.rows:
        errors = []
        name = r.data.get("full_name", "")
        phone = r.data.get("phone_number", "")

        if not name:
            errors.append("Missing name.")
        if not phone:
            errors.append("Missing phone number.")
        elif not _valid_phone(phone):
            errors.append("Phone number doesn't look valid.")

        # duplicate phone WITHIN the uploaded file
        if phone and phone in seen_phones:
            errors.append(f"Duplicate of row {seen_phones[phone]} in this file (same phone).")
        elif phone:
            seen_phones[phone] = r.row_number

        if errors:
            r.classification = "error"
            r.errors = errors
            continue

        # dedupe against the platform (existing borrower by phone)
        existing = BorrowerProfile.objects.filter(phone_number=phone).first()
        if existing:
            r.existing_borrower_id = existing.id
            r.existing_has_account = bool(existing.user_id)
            if phone in group_member_phones:
                r.classification = "error"
                r.errors = ["Already an active member of this group."]
            else:
                r.classification = "existing"   # will link, not duplicate
        else:
            r.classification = "new"

    return preview