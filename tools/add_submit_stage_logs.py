from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

completion_anchor = '''    if st.session_state.get("submission_complete"):
        saved = st.session_state.get("saved_result", {})'''
completion_replacement = '''    if st.session_state.get("submission_complete"):
        print("SUBMIT_STAGE=completion_screen", flush=True)
        saved = st.session_state.get("saved_result", {})'''

save_anchor = '''        import time
        _save_started = time.perf_counter()
        save_result(row)
        print(f"SAVE_RESULT_SECONDS={time.perf_counter() - _save_started:.3f}")'''
save_replacement = '''        import time

        print("SUBMIT_STAGE=before_save", flush=True)
        _save_started = time.perf_counter()
        save_result(row)
        print(
            f"SAVE_RESULT_SECONDS={time.perf_counter() - _save_started:.3f}",
            flush=True,
        )
        print("SUBMIT_STAGE=after_save", flush=True)'''

rerun_anchor = '''        st.session_state["questionnaire_started_at"] = datetime.now(JST).isoformat()
        st.session_state["questionnaire_timer_disease_mode"] = disease_mode
        st.rerun()'''
rerun_replacement = '''        st.session_state["questionnaire_started_at"] = datetime.now(JST).isoformat()
        st.session_state["questionnaire_timer_disease_mode"] = disease_mode
        print("SUBMIT_STAGE=before_rerun", flush=True)
        st.rerun()'''

for anchor, label in (
    (completion_anchor, "completion-screen anchor"),
    (save_anchor, "save timing anchor"),
    (rerun_anchor, "rerun anchor"),
):
    if anchor not in text:
        raise SystemExit(f"{label} not found; app.py was not changed")

text = text.replace(completion_anchor, completion_replacement, 1)
text = text.replace(save_anchor, save_replacement, 1)
text = text.replace(rerun_anchor, rerun_replacement, 1)
path.write_text(text, encoding="utf-8")
