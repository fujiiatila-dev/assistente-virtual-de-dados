# Virtual Data Assistant — Challenge 1

This repository contains the Challenge 1 product: a natural-language business data
assistant querying a read-only SQLite database, with dynamic schema discovery, SQL
self-correction, and Streamlit visualizations.

Internal specifications and development planning are intentionally kept outside the
official repository. The official database is a local dependency at
`../anexo_desafio_1.db` and must never be committed. Secrets belong only in `.env`;
commit `.env.example` instead.

The permanent branch is `main`; implementation changes should be validated before they
are merged.
