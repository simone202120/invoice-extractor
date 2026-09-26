---
description: Extract all sample invoices with the real LLM and report field-level accuracy
---

For each file in `samples/` run the extraction and compare with `samples/expected/<name>.json`.
Print a table: file, fields correct / total, retries used, validation errors. Real calls cost money:
run once.
