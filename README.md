# patient-insights-RD2

## Facility-specific patient entry

The existing Kanazawa Red Cross Hospital entrance continues to use the Render `SITE_ID=KRCH_DERM` setting.

External facilities use a generated patient URL:

```text
https://patient-insights-rd4.onrender.com/?facility=<FACILITY_ID>&access=<RANDOM_TOKEN>
```

`facility` is never trusted by itself. RD4 validates the random token against the shared Render Master Database, then assigns the registered facility ID, facility name, project ID, usage mode, and enabled questionnaires.

- External submissions are written only to the shared Master Database.
- The shared local CSV and clinician CSV view are disabled for external facilities.
- An invalid, incomplete, rotated, suspended, or unknown facility URL cannot submit.
- ADCT is hidden unless the facility-specific ADCT permission is confirmed.
- Kanazawa Red Cross research consent remains limited to its legacy research entrance; external clinical-workflow facilities receive the general use confirmation instead.

Staff passwords are never used in patient URLs. Staff access is provided by the separate Shirabeo facility Cockpit entrance.
