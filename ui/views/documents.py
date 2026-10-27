"""Documents page: KB overview, multi-file upload and a self-refreshing status table."""

from datetime import datetime

import streamlit as st

import ui_api_client
import ui_messages
from ui_api_client import ApiClientError

# The status table refreshes this often while any document is queued or processing.
POLL_SECONDS = 2
POLLING_KEY = "docs_polling"
UPLOAD_RESULT_KEY = "docs_upload_result"
DELETE_RESULT_KEY = "docs_delete_result"
BUSY_STATUSES = ("queued", "processing")


def show_client_error(exc):
    level, text = ui_messages.client_error_text(exc)
    (st.warning if level == ui_messages.LEVEL_WARNING else st.error)(text)


def format_timestamp(value):
    """'2026-10-22T10:00:00Z' -> '2026-10-22 10:00:00 UTC'; anything else is shown as is."""
    if not value:
        return ""
    return value.replace("T", " ").replace("Z", " UTC") if value.endswith("Z") else value.replace("T", " ")


def kb_overview_rows(kbs):
    return [{
        "Knowledge base": kb["name"],
        "Description": kb["description"],
        "Queued": kb["counts"].get("queued", 0),
        "Processing": kb["counts"].get("processing", 0),
        "Ready": kb["counts"].get("success", 0),
        "Failed": kb["counts"].get("failed", 0),
        "Total": kb["total"],
    } for kb in kbs]


def upload_rows(response):
    """One row per file of a POST /documents response, with a plain-language reason for rejections."""
    rows = []
    for entry in response["files"]:
        error = entry.get("error") or {}
        rows.append({
            "File": (entry.get("metadata") or {}).get("original_filename") or "",
            "Result": "✅ Accepted" if entry["status"] == "accepted" else "❌ Rejected",
            "Reason": ui_messages.describe_error(error.get("code"), error.get("message")) if error else "",
        })
    return rows


def document_rows(documents):
    return [{
        "File": document["original_filename"],
        "Status": ui_messages.status_label(document["ingestion_status"]),
        "Uploaded": format_timestamp(document.get("upload_timestamp")),
        "Last update": format_timestamp(document.get("updated_at")),
        "Problem": (ui_messages.describe_failure(document.get("failure_code"), document.get("failure_reason"))
                    if document["ingestion_status"] == "failed" else ""),
        "Code": document.get("failure_code") or "",
    } for document in documents]


def upload_files(client, kb, files):
    """Send the files to the API and keep the outcome in session state, so it survives reruns."""
    try:
        response = client.upload(kb["kb_id"], [(f.name, f.getvalue(), f.type) for f in files])
    except ApiClientError as exc:
        st.session_state[UPLOAD_RESULT_KEY] = {"kb_name": kb["name"], "error": ui_messages.client_error_text(exc)}
        return
    st.session_state[UPLOAD_RESULT_KEY] = {"kb_name": kb["name"], "rows": upload_rows(response)}
    if any(entry["status"] == "accepted" for entry in response["files"]):
        st.session_state[POLLING_KEY] = True


def show_upload_result():
    result = st.session_state.get(UPLOAD_RESULT_KEY)
    if result is None:
        return
    st.markdown("**Last upload to {0}**".format(result["kb_name"]))
    if "error" in result:
        level, text = result["error"]
        (st.warning if level == ui_messages.LEVEL_WARNING else st.error)(text)
    else:
        st.dataframe(result["rows"], hide_index=True, width="stretch")


def delete_label(document):
    return "{0} ({1}, uploaded {2})".format(
        document["original_filename"], ui_messages.status_label(document["ingestion_status"]),
        format_timestamp(document.get("upload_timestamp")) or "unknown")


def delete_document(client, kb_id, document):
    """Button callback: call the API, keep the outcome for show_delete_result, and reset the confirmation."""
    name = document["original_filename"]
    try:
        client.delete_document(kb_id, document["document_id"])
        result = ("success", "Deleted {0}.".format(name))
    except ApiClientError as exc:
        if exc.code == "not_found":
            result = ("info", "{0} no longer exists. It may already have been deleted.".format(name))
        else:
            level, text = ui_messages.client_error_text(exc)
            result = (level, "Couldn't delete {0}. {1}".format(name, text))
    st.session_state[DELETE_RESULT_KEY] = result
    st.session_state["docs_delete_confirm_" + kb_id] = False
    st.session_state.pop("docs_delete_id_" + kb_id, None)


def show_delete_result():
    result = st.session_state.pop(DELETE_RESULT_KEY, None)
    if result is None:
        return
    level, text = result
    {"success": st.success, "info": st.info, ui_messages.LEVEL_WARNING: st.warning}.get(level, st.error)(text)


def delete_section(client, kb):
    """Pick a document, tick the confirmation, press Delete. Documents still queued or processing can't be deleted."""
    st.subheader("Delete a document")
    show_delete_result()
    try:
        documents = client.list_documents(kb["kb_id"])
    except ApiClientError as exc:
        show_client_error(exc)
        return
    if not documents:
        st.caption("Nothing to delete in {0}.".format(kb["name"]))
        return
    by_id = {document["document_id"]: document for document in documents}
    chosen_id = st.selectbox("Document to delete", options=list(by_id), key="docs_delete_id_" + kb["kb_id"],
                             format_func=lambda value: delete_label(by_id[value]))
    chosen = by_id[chosen_id]
    busy = chosen["ingestion_status"] in BUSY_STATUSES
    if busy:
        st.caption("This document is still {0}. Wait until it has finished, then delete it.".format(
            chosen["ingestion_status"]))
    confirmed = st.checkbox("Yes, permanently delete this document and its search entries. This can't be undone.",
                            key="docs_delete_confirm_" + kb["kb_id"], disabled=busy)
    st.button("Delete document", disabled=busy or not confirmed, on_click=delete_document,
              args=(client, kb["kb_id"], chosen))


client = ui_api_client.get_client()
st.title("Documents")

try:
    kbs = client.list_kbs()
except ApiClientError as exc:
    show_client_error(exc)
    st.stop()

st.subheader("Knowledge bases")
st.dataframe(kb_overview_rows(kbs), hide_index=True, width="stretch")

kb_by_id = {kb["kb_id"]: kb for kb in kbs}
kb_id = st.selectbox("Knowledge base", options=list(kb_by_id), format_func=lambda value: kb_by_id[value]["name"],
                     key="docs_kb_id")
selected_kb = kb_by_id[kb_id]
st.caption(selected_kb["description"])

st.subheader("Upload")
with st.form("upload_form", clear_on_submit=True):
    chosen_files = st.file_uploader("Files to add to {0} (PDF, TXT or MD)".format(selected_kb["name"]),
                                    type=["pdf", "txt", "md"], accept_multiple_files=True)
    submitted = st.form_submit_button("Add files to {0}".format(selected_kb["name"]), type="primary")
if submitted:
    if not chosen_files:
        st.warning("Choose at least one file first.")
    else:
        with st.spinner("Uploading {0} file(s)...".format(len(chosen_files))):
            upload_files(client, selected_kb, chosen_files)
show_upload_result()

st.subheader("Documents in {0}".format(selected_kb["name"]))
polling = st.session_state.get(POLLING_KEY, False)


# run_every is fixed when the fragment is defined, so turning polling on or off
# reruns the whole app to define it again with the new interval.
@st.fragment(run_every=POLL_SECONDS if polling else None)
def status_table(kb_id):
    try:
        documents = client.list_documents(kb_id)
    except ApiClientError as exc:
        show_client_error(exc)
        return
    needs_polling = any(document["should_poll"] for document in documents)
    if needs_polling != st.session_state.get(POLLING_KEY, False):
        st.session_state[POLLING_KEY] = needs_polling
        st.rerun(scope="app")
    if not documents:
        st.info("No documents in this knowledge base yet. Upload one above.")
    else:
        st.dataframe(document_rows(documents), hide_index=True, width="stretch")
    note = " Refreshing every {0} s while files are queued or processing.".format(POLL_SECONDS) if needs_polling else ""
    st.caption("Last refreshed {0}.{1}".format(datetime.now().strftime("%H:%M:%S"), note))


status_table(kb_id)
delete_section(client, selected_kb)
