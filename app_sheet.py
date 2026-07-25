from __future__ import annotations

import runpy


# Google Sheet mirroring has been retired.
# RD4 now saves to the local CSV backup and Render Master Database only.
runpy.run_module("app_master", run_name="__main__")
