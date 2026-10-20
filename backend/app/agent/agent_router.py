"""Query routing for the Knowledge Agent (F4, coach mode: Ethan implements)."""


def route(question, kb_descriptions, llm):
    """Pick the knowledge base or bases that can answer a question.

    Args:
        question: the user's question, a non-blank string.
        kb_descriptions: {kb_id: description} for every configured KB, in
            config order, for example
                {"it_policies": "public university IT policies and procedures",
                 "hw_datasheets": "public hardware datasheets (pinouts, ...)"}.
            Its keys are the configured KB ids.
        llm: an LlmProvider (agent/agent_llm.py). llm.generate(prompt,
            system_instruction=None) returns an LlmResponse whose .text is the
            model's reply.

    Returns:
        A dict:
            {
                "kb_ids": [str, ...],  # 0, 1 or 2 configured KB ids, no duplicates
                "reason": str,         # why these KBs were chosen
                "fallback": bool,      # True only when routing failed (below)
            }
        - On-topic: the one or two configured KBs that can answer it,
          fallback False.
        - Off-topic (no KB covers it): kb_ids [], fallback False.
        - Invalid LLM reply (it can't be parsed, it names a KB id that isn't
          configured, or it has the wrong shape): kb_ids holds every configured
          KB, fallback True, and reason says that routing failed.
        kb_ids is always a subset of kb_descriptions' keys.

    Raises:
        LlmUnavailableError: from llm.generate, not caught here. /ask turns it
            into a 503.
    """
    raise NotImplementedError("route() is not implemented yet")
