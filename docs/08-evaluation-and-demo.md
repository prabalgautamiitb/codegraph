# Evaluation And Demo

Demo command:

```bash
python3 -m backend.app.ingestion.cli fixtures/python_demo --pretty
```

Automated checks:

```bash
pytest
cd frontend && npm run build
```

No benchmark numbers are published yet.

The fixture now includes Python, Markdown and `pyproject.toml` facts. The stale-node regression edits a copied fixture, republishes a snapshot and confirms removed dependencies no longer appear in current symbol search.
