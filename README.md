# data-pipeline-agent

Build complete, runnable Python ETL pipelines from plain-English descriptions
using Claude AI (`claude-sonnet-4-6`) and the Anthropic SDK.

## Features

- **Plain-English input** — describe your pipeline in natural language.
- **Schema inference** — automatically detects column types, nullability, and
  candidate primary keys from CSV files.
- **Pandas-based output** — generates clean, well-commented Python scripts.
- **Tool-use agentic loop** — Claude reads files, infers schemas, and writes the
  final script using structured tool calls.
- **Cloud-ready stubs** — generated pipelines include S3 (boto3/s3fs), Postgres
  (SQLAlchemy + psycopg2), and BigQuery (google-cloud-bigquery) patterns.
- **Rich CLI** — pretty output with syntax-highlighted scripts and Markdown summaries.

## Installation

```bash
# Base install (pandas + anthropic + rich + click)
pip install data-pipeline-agent

# With cloud connectors
pip install "data-pipeline-agent[aws]"        # S3 / boto3
pip install "data-pipeline-agent[gcp]"        # BigQuery
pip install "data-pipeline-agent[postgres]"   # Postgres / SQLAlchemy
pip install "data-pipeline-agent[all]"        # everything
```

Or install from source:

```bash
git clone https://github.com/example/data-pipeline-agent
cd data-pipeline-agent
pip install -e ".[dev]"
```

## Quick Start

### 1. Set your API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 2. Build a pipeline

```bash
# Simple CSV-to-CSV pipeline
pipeline-agent build \
  "Read sales.csv, drop rows where revenue is null, \
   deduplicate on (order_id, product_id), \
   write clean data to cleaned_sales.csv" \
  --output clean_sales_pipeline.py

# S3 → Postgres pipeline
pipeline-agent build \
  "Read parquet files from S3 bucket my-data/events/, \
   filter to rows where event_type is 'purchase', \
   join with a local users.csv on user_id, \
   write the result to Postgres table analytics.purchases" \
  --output events_pipeline.py

# CSV → BigQuery with type coercion
pipeline-agent build \
  "Read orders.csv, cast order_date to datetime, \
   cast amount to float, drop nulls in customer_id, \
   write to BigQuery dataset prod.orders" \
  --output bq_orders_pipeline.py
```

### 3. Run the generated script

```bash
pipeline-agent run --pipeline clean_sales_pipeline.py
```

Or run it directly:

```bash
python clean_sales_pipeline.py
```

## Python API

```python
from pipeline_agent import PipelineAgent

agent = PipelineAgent(
    model="claude-sonnet-4-6",  # default
    max_tokens=8192,
)

summary = agent.build(
    description="""
        Read users.csv, drop rows where email is null or empty,
        normalise the 'country' column to ISO-3166 alpha-2 codes,
        write the result to cleaned_users.parquet.
    """,
    output_path="clean_users.py",
    verbose=True,  # print tool calls to stdout
)
print(summary)
```

### Schema Inferrer

You can also use the schema inferrer on its own:

```python
from pipeline_agent import SchemaInferrer

inferrer = SchemaInferrer(sample_rows=5_000)
schema = inferrer.infer_from_csv("orders.csv")

for col in schema["columns"]:
    print(col["name"], col["inferred_type"], "nullable:", col["nullable"])

print("Candidate PKs:", schema["candidate_primary_keys"])
```

## CLI Reference

```
Usage: pipeline-agent [OPTIONS] COMMAND [ARGS]...

  data-pipeline-agent – Build ETL pipelines from plain English.

Commands:
  build  Generate an ETL pipeline from DESCRIPTION and write it to --output.
  run    Execute an already-generated pipeline script.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.
```

### `build` options

| Option | Default | Description |
|---|---|---|
| `--output / -o` | `pipeline.py` | Output path for the generated script |
| `--model` | `claude-sonnet-4-6` | Claude model to use |
| `--max-tokens` | `8192` | Max tokens in the model response |
| `--quiet / -q` | off | Suppress intermediate tool-call output |

### `run` options

| Option | Default | Description |
|---|---|---|
| `--pipeline / -p` | *(required)* | Path to the pipeline script |
| `--python` | current interpreter | Python executable to use |

## Architecture

```
description
    │
    ▼
PipelineAgent.build()
    │
    ├─ Claude claude-sonnet-4-6 (with tool use)
    │       │
    │       ├─ read_file(path)              ← inspect existing files
    │       ├─ infer_schema(csv_path)       ← SchemaInferrer
    │       └─ write_file(path, content)   ← write the ETL script
    │
    └─ returns summary string
```

Claude drives the agentic loop: it reads any referenced files, infers schemas
for CSV sources, generates the full ETL script, writes it to disk, and returns
a human-readable summary with setup instructions.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `AWS_ACCESS_KEY_ID` | For S3 pipelines | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | For S3 pipelines | AWS credentials |
| `AWS_DEFAULT_REGION` | For S3 pipelines | AWS region |
| `POSTGRES_DSN` | For Postgres pipelines | e.g. `postgresql://user:pass@host/db` |
| `GOOGLE_APPLICATION_CREDENTIALS` | For BigQuery pipelines | Path to GCP service-account JSON |
| `BIGQUERY_PROJECT` | For BigQuery pipelines | GCP project ID |

Generated pipeline scripts document which variables they need in their
docstring and will raise a clear `EnvironmentError` if a required variable
is missing at runtime.

## Development

```bash
pip install -e ".[dev]"

# Lint
ruff check pipeline_agent/

# Type-check
mypy pipeline_agent/

# Tests
pytest
```

## License

MIT
