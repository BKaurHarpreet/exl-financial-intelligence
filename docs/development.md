# Development

## Commands

Start the stack:

```bash
docker compose up --build
```

Run ETL:

```bash
docker compose run --rm api python -m app.etl.run_pipeline
```

Run tests:

```bash
docker compose run --rm api pytest
```

## Repository Principles

- Preserve raw source data before deriving metrics.
- Keep transformations explicit and traceable.
- Prefer SQL tables with clear schema boundaries over opaque files.
- Keep the frontend thin; the ETL and database design are the core product.
- Each change should leave Docker Compose runnable.
