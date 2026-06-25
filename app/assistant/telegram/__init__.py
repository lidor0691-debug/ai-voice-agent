"""Assistant Telegram intake — pure helpers. DORMANT by default.

This package holds the network-free pieces of the owner-only Telegram intake:
  * ``intake``  — parse allowlist / owner-map, verify the webhook secret,
                  extract the usable fields from a Telegram update.
  * ``replies`` — format the Hebrew owner-facing reply text.

Nothing here performs I/O, imports the data adapter, or constructs an Anthropic
or Telegram client. The FastAPI route lives in
``app/routes/assistant_telegram_api.py`` and is mounted only when
``ASSISTANT_TELEGRAM_INTAKE_ENABLED`` is true.
"""
