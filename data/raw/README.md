# Raw Data

Original EXL Excel filings are stored under `data/raw/EXL`.

These files are intentionally committed as immutable source inputs so the Bronze layer can be rebuilt and audited.

If this repository was populated through the GitHub connector, push the `.xls` files from the local committed workspace because connector writes are limited to UTF-8 text.
