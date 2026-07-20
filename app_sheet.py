from __future__ import annotations

import runpy

from master_store import ProStore
from sheet_mirror import mirror_record

_original_save_row = ProStore.save_row


def save_row_and_mirror(self, row, *, facility_id: str, project_id: str) -> bool:
    inserted = _original_save_row(
        self,
        row,
        facility_id=facility_id,
        project_id=project_id,
    )
    if inserted:
        payload = dict(row)
        payload["facility_id"] = facility_id
        payload["project_id"] = project_id
        ok, message = mirror_record("RD4", payload)
        print("SHEET MIRROR RD4:", "ok" if ok else message)
    return inserted

ProStore.save_row = save_row_and_mirror
runpy.run_module("app_master", run_name="__main__")
