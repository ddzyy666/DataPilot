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
- `POST /api/v1/query/{request_id}/clarify` resumes a query after the user supplies missing information.
- `POST /api/v1/query/{request_id}/confirm` resumes or rejects a query waiting for approval.
- `GET /api/v1/audit/{request_id}` returns the audit record for one query request.

For SiliconFlow, a typical local `.env` configuration is:

```env
AGENT_RUNTIME=langgraph
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
QUERY_TIMEOUT_SECONDS=5
QUERY_ALLOWED_TABLES=regions,customers,categories,products,orders,order_items
QUERY_DENIED_COLUMNS=
QUERY_MAX_REPAIR_ATTEMPTS=1
QUERY_ENABLE_SQL_REVIEW=true
```

Switch to the LangGraph orchestration runtime while keeping the same business services:

```env
AGENT_RUNTIME=langgraph
CHECKPOINT_DATABASE_PATH=./data/checkpoints.db
QUERY_ENABLE_CLARIFICATION=true
QUERY_MAX_CLARIFICATION_ROUNDS=2
QUERY_ENABLE_RESULT_ANALYSIS=true
QUERY_RESULT_ANALYSIS_MAX_ROWS=20
QUERY_REQUIRE_CONFIRMATION_FOR_HIGH_RISK=true
```

If the question is materially ambiguous, `/api/v1/query` returns
`status=waiting_for_clarification` before SQL generation. Continue the same graph thread with:

```json
POST /api/v1/query/{request_id}/clarify
{
  "answer": "按销售金额统计2025年前10名"
}
```

The answer is merged into the effective question and checked again. The configured round limit
prevents an endless clarification loop, and the original question remains unchanged in audit data.

When a generated SQL statement is assessed as high risk, `/api/v1/query` returns
`status=waiting_for_confirmation`, `requires_confirmation=true`, and a `request_id`
without executing it. Resume it with:

```json
POST /api/v1/query/{request_id}/confirm
{
  "approved": true,
  "edited_sql": null
}
```

Set `approved` to `false` to reject it. `edited_sql` may contain a manually corrected
statement; it is still checked by the readonly and table/column permission policies.
The SQLite checkpointer keeps interrupted graph state across process restarts.

## Business semantic layer

The structured semantic catalog maps user wording to standard metrics and dimensions before SQL
generation. Each metric can define aliases, an authoritative SQL expression, required tables,
default filters, a time field, output naming, and calculation notes. Dimensions define business
fields and grouping expressions. The `resolve_semantics` graph node selects only relevant entries
and JOIN relationships, then supplies the same semantic context to question clarification, SQL
generation, semantic review, and repair. API responses expose `matched_metrics`,
`matched_dimensions`, and `semantic_context` for debugging and explainability.

After a successful query, the `analyze_result` node returns a Chinese summary, up to three
insights, a deterministic data profile, and a chart recommendation. Numeric facts such as
minimum, maximum, sum, and average are calculated in Python rather than by the model. Only
the configured number of result rows are sent to the LLM. If narrative generation fails, the
SQL rows and chart recommendation are still returned with `result_analysis_error` populated.

## Frontend dashboard

The React dashboard renders metric cards, bar charts, line charts, result tables, data profiles,
clarification prompts, and high-risk SQL approval controls. Start the backend first:

```powershell
conda activate text2sql-agent
python -m uvicorn app.main:app --reload
```

Then start the frontend in another terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to the FastAPI service at
`http://127.0.0.1:8000`, so no additional CORS configuration is required in development.
