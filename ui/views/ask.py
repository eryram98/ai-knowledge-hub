"""Ask page: a question goes to POST /ask; shows the answer, routing, sources, latency and token usage."""

import time

import streamlit as st

import ui_api_client
import ui_messages
from ui_api_client import ApiClientError

OUTCOME_KEY = "ask_outcome"
MAX_QUESTION_CHARS = 2000


def escape_markdown(text):
    """Keep '$' literal: st.markdown would render text between two of them as LaTeX."""
    return (text or "").replace("$", "\\$")


def page_label(page_start, page_end):
    if page_start is None:
        return "no page"
    if page_end is None or page_end == page_start:
        return "p. {0}".format(page_start)
    return "p. {0}–{1}".format(page_start, page_end)


def ordered_sources(sources):
    """Cited sources first, each group in the answer's [n] order."""
    return sorted(sources, key=lambda source: (not source["cited"], source["number"]))


def source_title(source, kb_names):
    return "[{0}] {1} · {2} · {3} · {4}".format(
        source["number"], source["document"], page_label(source.get("page_start"), source.get("page_end")),
        kb_names.get(source["kb_id"], source["kb_id"]), "Cited" if source["cited"] else "Not cited",
    )


def badges(result):
    found = []
    if result["off_topic"]:
        found.append(":orange-badge[:material/block: Off-topic]")
    if result["routing_fallback"]:
        found.append(":red-badge[:material/warning: Routing fell back to all KBs]")
    if result["no_answer"] and not result["off_topic"]:
        found.append(":gray-badge[:material/help: No answer in the knowledge base]")
    return found


def show_result(result, latency_seconds, kb_names):
    routed = ", ".join(kb_names.get(kb_id, kb_id) for kb_id in result["kb_ids"]) or "no knowledge base"
    st.markdown(" ".join([":blue-badge[:material/route: Routed to {0}]".format(routed)] + badges(result)))
    st.caption("Why: " + escape_markdown(result["route_reason"]))

    st.subheader("Answer")
    st.markdown(escape_markdown(result["answer"]))

    usage = result["usage"]
    columns = st.columns(4)
    columns[0].metric("Latency", "{0:.1f} s".format(latency_seconds))
    columns[1].metric("Input tokens", "{0:,}".format(usage["input_tokens"]))
    columns[2].metric("Output tokens", "{0:,}".format(usage["output_tokens"]))
    columns[3].metric("LLM calls", len(usage["calls"]))

    sources = result["sources"]
    if sources:
        cited = sum(1 for source in sources if source["cited"])
        st.subheader("Sources ({0} shown to the model, {1} cited)".format(len(sources), cited))
        for source in ordered_sources(sources):
            with st.expander(source_title(source, kb_names)):
                st.markdown(escape_markdown(source["snippet"]))
                st.caption("Chunk {0}".format(source["chunk_id"]))

    st.subheader("Token usage per call")
    st.dataframe([{
        "Step": call["step"], "Model": call["model"],
        "Input tokens": call["input_tokens"], "Output tokens": call["output_tokens"],
    } for call in usage["calls"]], hide_index=True, width="stretch")


client = ui_api_client.get_client()
st.title("Ask")

try:
    kbs = client.list_kbs()
except ApiClientError:
    # The KB names only label the result; /ask itself reports a problem with the API.
    kbs = []
kb_names = {kb["kb_id"]: kb["name"] for kb in kbs}

with st.form("ask_form"):
    question = st.text_area("Question", max_chars=MAX_QUESTION_CHARS,
                            placeholder="For example: What are the board dimensions of the Pico?")
    submitted = st.form_submit_button("Ask", type="primary")
if submitted:
    if not question.strip():
        st.warning("Type a question first.")
    else:
        started = time.perf_counter()
        with st.spinner("Routing the question and writing the answer..."):
            try:
                outcome = {"result": client.ask(question.strip())}
            except ApiClientError as exc:
                outcome = {"error": ui_messages.client_error_text(exc)}
        outcome["question"] = question.strip()
        outcome["latency"] = time.perf_counter() - started
        st.session_state[OUTCOME_KEY] = outcome

outcome = st.session_state.get(OUTCOME_KEY)
if outcome is None:
    covered = " and ".join(kb_names.values()) or "the knowledge bases"
    st.info("Ask a question about {0}. You don't pick a knowledge base: the question is routed for you.".format(
        covered))
else:
    st.markdown("**Question:** " + escape_markdown(outcome["question"]))
    if "error" in outcome:
        level, text = outcome["error"]
        (st.warning if level == ui_messages.LEVEL_WARNING else st.error)(text)
    else:
        show_result(outcome["result"], outcome["latency"], kb_names)
