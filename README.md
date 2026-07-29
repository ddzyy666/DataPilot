# DataPilot

DataPilot is a production-oriented Text-to-SQL data analysis agent. It will
translate natural-language questions into safe SQL, execute queries, repair
failures, and explain the resulting data.

## Current milestone

The first milestone provides a minimal FastAPI service with configuration,
automated tests, and an API health check.

## Local development

Activate the Conda environment:

```powershell
conda activate text2sql-agent
cd "D:\python project\Text-t-SQL"
```

Install the project and development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run tests:

```powershell
python -m pytest
```

Initialize the deterministic e-commerce demo database:

```powershell
datapilot-seed
```

Start the API:

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to view the generated API documentation.

Useful endpoints:

- `GET /health` checks service availability.
- `GET /api/v1/schema` returns database tables, columns, primary keys, and foreign keys.
