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
- `POST /api/v1/query` generates a readonly SQL query from a natural-language question.

For SiliconFlow, a typical local `.env` configuration is:

```env
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen3-8B
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=800
LLM_USE_RESPONSE_FORMAT=false
LLM_TRUST_ENV=false
LLM_ENABLE_THINKING=false
```
