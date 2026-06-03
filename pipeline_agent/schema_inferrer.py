"""
SchemaInferrer: Infer column types, nullability, and candidate primary keys
from a CSV sample without requiring the full file in memory.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Type detection helpers
# ---------------------------------------------------------------------------


def _is_integer(value: str) -> bool:
    try:
        int(value)
        return True
    except ValueError:
        return False


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _is_boolean(value: str) -> bool:
    return value.strip().lower() in {"true", "false", "1", "0", "yes", "no"}


def _is_date_like(value: str) -> bool:
    """Very lightweight check – avoids importing dateutil at inference time."""
    import re

    date_patterns = [
        r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$",  # ISO-8601
        r"^\d{2}/\d{2}/\d{4}$",  # MM/DD/YYYY
        r"^\d{2}-\d{2}-\d{4}$",  # MM-DD-YYYY
        r"^\d{4}/\d{2}/\d{2}$",  # YYYY/MM/DD
    ]
    for pat in date_patterns:
        if re.match(pat, value.strip()):
            return True
    return False


_NULL_SENTINELS = {"", "null", "none", "na", "n/a", "nan", "nil", "#n/a"}


def _is_null(value: str) -> bool:
    return value.strip().lower() in _NULL_SENTINELS


# ---------------------------------------------------------------------------
# Column statistics accumulator
# ---------------------------------------------------------------------------


class _ColumnStats:
    def __init__(self, name: str) -> None:
        self.name = name
        self.total: int = 0
        self.null_count: int = 0
        self.integer_count: int = 0
        self.float_count: int = 0
        self.boolean_count: int = 0
        self.date_count: int = 0
        self.unique_values: set[str] = set()
        self.max_unique_track = 1000  # stop tracking after this many uniques

    def observe(self, raw: str) -> None:
        self.total += 1
        if _is_null(raw):
            self.null_count += 1
            return
        stripped = raw.strip()
        if len(self.unique_values) < self.max_unique_track:
            self.unique_values.add(stripped)
        if _is_integer(stripped):
            self.integer_count += 1
            self.float_count += 1  # integers are also valid floats
        elif _is_float(stripped):
            self.float_count += 1
        if _is_boolean(stripped):
            self.boolean_count += 1
        if _is_date_like(stripped):
            self.date_count += 1

    # ------------------------------------------------------------------

    @property
    def non_null_count(self) -> int:
        return self.total - self.null_count

    def inferred_type(self) -> str:
        """Return the most specific SQL/pandas-compatible type name."""
        n = self.non_null_count
        if n == 0:
            return "string"  # all nulls – can't tell
        if self.boolean_count == n:
            return "boolean"
        if self.integer_count == n:
            return "integer"
        if self.float_count == n:
            return "float"
        if self.date_count == n:
            return "datetime"
        return "string"

    def is_nullable(self) -> bool:
        return self.null_count > 0

    def null_fraction(self) -> float:
        if self.total == 0:
            return 0.0
        return self.null_count / self.total

    def cardinality(self) -> int:
        """Number of distinct non-null values seen (may be capped)."""
        return len(self.unique_values)

    def looks_like_primary_key(self) -> bool:
        """Heuristic: integer/string column with high cardinality and no nulls."""
        if self.is_nullable():
            return False
        # If we tracked all unique values and they equal total rows – unique!
        if (
            len(self.unique_values) < self.max_unique_track
            and len(self.unique_values) == self.non_null_count
        ):
            return True
        return False


# ---------------------------------------------------------------------------
# SchemaInferrer
# ---------------------------------------------------------------------------


class SchemaInferrer:
    """Infer schema information from CSV files.

    Parameters
    ----------
    sample_rows:
        Maximum number of rows to read when inferring schema.
        Defaults to 10 000 (fast even on large files).
    """

    def __init__(self, sample_rows: int = 10_000) -> None:
        self.sample_rows = sample_rows

    def infer_from_csv(self, path: str | Path) -> dict[str, Any]:
        """Infer schema from a CSV file.

        Parameters
        ----------
        path:
            Path to the CSV file.

        Returns
        -------
        dict
            A schema dict with keys:
            - ``file``: str – file path
            - ``rows_sampled``: int
            - ``columns``: list of column descriptors
            - ``candidate_primary_keys``: list[str]
        """
        path = Path(path)
        stats: list[_ColumnStats] = []
        rows_read = 0

        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return {"error": "CSV has no header row"}

            stats = [_ColumnStats(name) for name in reader.fieldnames]
            name_to_stat = {s.name: s for s in stats}

            for row in reader:
                if rows_read >= self.sample_rows:
                    break
                for col_name, raw_value in row.items():
                    if col_name in name_to_stat:
                        name_to_stat[col_name].observe(raw_value or "")
                rows_read += 1

        columns = []
        candidate_pks: list[str] = []

        for stat in stats:
            col_info: dict[str, Any] = {
                "name": stat.name,
                "inferred_type": stat.inferred_type(),
                "nullable": stat.is_nullable(),
                "null_fraction": round(stat.null_fraction(), 4),
                "distinct_values_seen": stat.cardinality(),
                "rows_sampled": rows_read,
            }
            columns.append(col_info)
            if stat.looks_like_primary_key():
                candidate_pks.append(stat.name)

        return {
            "file": str(path),
            "rows_sampled": rows_read,
            "columns": columns,
            "candidate_primary_keys": candidate_pks,
        }
