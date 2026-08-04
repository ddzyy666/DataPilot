# DataPilot

DataPilot is a production-oriented Text-to-SQL data analysis agent. It will
translate natural-language questions into safe SQL, execute queries, repair
failures, and explain the resulting data.

## Current milestone

The service reads database metadata, generates readonly SQL with an LLM,
reviews SQL semantics against the question and schema, validates and executes
the SQL, automatically repairs failed SQL once, and returns structured query
results with per-stage timings and a configurable row limit.

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

Validate all 50 golden SQL answers without calling the LLM:

```powershell
datapilot-benchmark --gold-only
```

Run the full 50-question LLM benchmark and write a JSON report:

```powershell
datapilot-benchmark
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
- `POST /api/v1/query` generates and executes a readonly SQL query from a natural-language question.

For SiliconFlow, a typical local `.env` configuration is:

```env
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen3-8B
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=800
LLM_USE_RESPONSE_FORMAT=false
LLM_TRUST_ENV=false
LLM_ENABLE_THINKING=false
LLM_MAX_RETRIES=1
LLM_RETRY_DELAY_SECONDS=1
QUERY_MAX_ROWS=200
QUERY_MAX_REPAIR_ATTEMPTS=1
QUERY_ENABLE_SQL_REVIEW=true
```
