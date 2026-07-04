"""CSV helpers for the Reports module. Returns a StreamingResponse with an attachment header."""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from fastapi.responses import StreamingResponse


def csv_response(filename: str, headers: list[str], rows: Iterable[Iterable]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if c is None else c for c in row])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
