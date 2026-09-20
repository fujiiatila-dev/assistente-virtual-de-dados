# Virtual Data Assistant — Challenge 1

This repository contains the preparation plan for Challenge 1: a natural-language
business data assistant querying a read-only SQLite database, with dynamic schema
discovery, SQL self-correction, and Streamlit visualizations.

Implementation must follow `openspec/changes/implement-data-assistant/tasks.md` and the
execution rules in `HANDOFF.md`. The official database is a local dependency at
`../anexo_desafio_1.db` and must never be committed. Secrets belong only in `.env`;
commit `.env.example` instead. The permanent branch is `main`, and every task must be
implemented in a separate `feat/` or `fix/` branch, validated, committed, and merged.

The next step is to complete T0a and T0b before starting the product scaffolding.
