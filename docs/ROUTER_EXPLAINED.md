# How the router works (`route()`, F4)

Code: `backend/app/agent/agent_router.py`. Tests: `backend/tests/test_agent_router.py`.
Ethan designed it on 2026-10-22, and Claude implemented it because coach mode is paused
until after Oct 27. Ethan reviews it and may rewrite it after that.

## What it does

`route(question, kb_descriptions, llm)` decides which knowledge bases `/ask` searches.

1. **Build the prompt from config.** `build_routing_instruction` lists every configured KB as
   `- <kb_id>: <description>`, using `config/kb_descriptions.json`, so nothing about the KBs is
   hardcoded. Then come the rules (usually one KB; two only if the answer *needs* both; none if
   no KB can answer it), the reply format, and 4 few-shot examples (datasheet, policy, both,
   off-topic). An example is shown only if every KB it names is configured.
2. **One LLM call.** The user message is `Question: <question>`. Thinking is set to `low`
   because this is a short classification, not reasoning. (`gemini-3.8-flash` rejects
   `minimal` with a 400, so `low` is the lowest level that works.)
3. **Parse and check the reply.** Strip a Markdown code fence if there is one, then
   `json.loads`. The reply must be an object with `kb_ids` (a list of configured ids, no
   duplicates, at most 2) and a non-blank `reason`.
4. **Return** `{kb_ids, reason, fallback}`. The ids come back in config order.
   - Valid reply: `fallback: false`. An empty `kb_ids` means off-topic, so `/ask` skips
     retrieval and lists what the KBs cover.
   - Invalid reply: every configured KB, `fallback: true`, and a reason like
     "Routing failed (unknown knowledge base 'hr'); searched every knowledge base."
   - `LlmUnavailableError` is not caught, so `/ask` returns 503.

## Why each choice

**LLM classification instead of embedding similarity.** The alternative embeds the question
and each KB description and picks the closest one.

| | LLM classification (chosen) | Embedding similarity |
|---|---|---|
| Off-topic detection | Rule 3 plus an example; the model says "none" | Needs a similarity threshold, which we can't tune without labeled data |
| "Needs both" | Can reason that a question has two parts | Two close scores don't mean both KBs are needed |
| Explanation | `reason` is shown in the API and UI | A number |
| Latency | One extra call (low thinking; 28.5 s in one run during a Gemini outage) | About 30 ms (bge-small is already loaded) |
| Cost and quota | One free-tier call per question | Free, no quota |
| Laptop feasibility | Yes (hosted LLM) | Yes |
| Training data | None (4 examples in the prompt) | None, but threshold tuning needs some |

KB descriptions are one line each, too short for reliable similarity. With two KBs and a
free-tier LLM, the extra call is worth it for correct off-topic and "both" decisions.
Embedding similarity is a good cheap pre-filter if the number of KBs grows.

**A high bar for "both", because of how RRF behaves across KBs.** RRF scores a chunk as
the sum of 1/(k + rank) over the lists it appears in, with k = 60, and ignores the raw scores.
Every KB contributes its own vector and keyword list, so a chunk ranked first in both lists
of an irrelevant KB scores 2/61, exactly like the best chunk of the relevant KB. Routing to
an irrelevant second KB doesn't just add noise at the bottom: its best chunks can take
around half of the top-10 slots the answer step sees. That's why rule 2 says a question that merely *sounds*
related to both isn't enough. Re-ranking (F7) makes this less important, because a
cross-encoder scores relevance directly.

**Two failure types, two behaviors.**
- *The LLM is unavailable* (429 or 503 after retries, network down): routing can't happen,
  and the answer call would fail the same way. Searching every KB would only delay the same
  error. So it propagates, `/ask` returns 503 with `Retry-After`, and the UI shows "busy, try
  again".
- *The LLM answered but the reply is unusable* (not JSON, wrong shape, invented KB id, more than
  2): the service works, so the answer step can still run. Searching every KB is the safe
  degradation, because a grounded answer from more chunks beats no answer. `routing_fallback:
  true` makes it visible, and the warning log keeps the bad reply for debugging.

**Strict validation instead of repair.** An unknown id isn't fuzzy-matched, and a list of three
isn't cut to two. A repaired reply would hide prompt problems; a fallback is visible and
counted.

## Likely professor questions

1. **Why not let the user pick the KB?** The spec says users shouldn't have to know how the
   documents are organized. Routing also lets other agents call one endpoint. A KB filter is
   still possible through `/search`.
2. **How do you know the router is accurate?** F6's eval set has `expected_kb` per question
   (one KB, both, or none), and the eval script reports routing accuracy as the share of
   exact KB-set matches. The few-shot examples avoid the eval questions, so they don't inflate it.
3. **What happens with 10 KBs instead of 2?** The prompt grows by one line per KB, and the
   2-KB cap and the "every KB" fallback would need rethinking (the fallback would break the
   cap). Next steps: embedding similarity to shortlist KBs, then the LLM to choose among them.
4. **Isn't an extra LLM call slow and expensive?** It's one short call with low thinking, on
   the free tier. The measured latency and tokens are in PROGRESS.md. An off-topic question
   costs only this one call, because retrieval and the answer call are skipped.
5. **Can a user manipulate the router with the question?** Rule 5 tells the model the question
   is text to classify. More importantly, the output is validated: the worst a manipulated reply
   can do is pick a wrong configured KB or trigger the fallback. It can't name another KB, run
   code, or skip grounding, because the answer step still uses only retrieved chunks.
