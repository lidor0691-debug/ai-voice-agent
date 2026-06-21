"""Hebrew parser evaluation harness. DEV-ONLY, DORMANT.

A read-only, opt-in tool that measures the real Claude Stage-1 parser
(``app.assistant.core.llm_parser.ClaudeParser``) against the canonical 25
Hebrew NLP cases (the test oracle in ``tests/assistant/nlp``).

It lives under ``tools/`` — NOT ``app/`` — so it is never imported by the
FastAPI service, a route, a scheduler, or any production code path.

Hard boundaries:
  * Importing this package constructs NO Anthropic client and makes NO network
    call (the parser builds its client lazily, only when a live run fires).
  * This package imports NO Supabase / data adapter (it never touches the DB).
  * Live Claude calls happen ONLY through ``run_eval`` and ONLY when both
    ``ASSISTANT_RUN_LIVE_EVAL=1`` and ``ANTHROPIC_API_KEY`` are set.
"""
