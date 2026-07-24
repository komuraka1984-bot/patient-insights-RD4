from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

anchor = "        save_result(row)\n\n        st.session_state[\"saved_result\"] = {"
replacement = "        import time\n        _save_started = time.perf_counter()\n        save_result(row)\n        print(f\"SAVE_RESULT_SECONDS={time.perf_counter() - _save_started:.3f}\")\n\n        st.session_state[\"saved_result\"] = {"

if replacement in text:
    raise SystemExit("Timing instrumentation already present")
if anchor not in text:
    raise SystemExit("Expected save_result anchor not found; no changes made")

text = text.replace(anchor, replacement, 1)
compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")
