"""
PipelineAgent: Uses Claude claude-sonnet-4-6 with tool use to build ETL pipelines
from plain English descriptions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

from .schema_inferrer import SchemaInferrer

# ---------------------------------------------------------------------------
# Tool implementations (executed locally, results fed back to Claude)
# ---------------------------------------------------------------------------


def _read_file(path: str) -> str:
    """Read a file and return its contents as a string."""
    p = Path(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    if not p.is_file():
        return f"ERROR: Path is not a file: {path}"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"ERROR reading {path}: {exc}"


def _write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: Wrote {len(content)} characters to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR writing {path}: {exc}"


def _infer_schema(csv_path: str) -> str:
    """Infer schema (column types, nullability, candidate primary keys) from a CSV."""
    p = Path(csv_path)
    if not p.exists():
        return f"ERROR: CSV file not found: {csv_path}"
    inferrer = SchemaInferrer()
    try:
        schema = inferrer.infer_from_csv(csv_path)
        return json.dumps(schema, indent=2)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR inferring schema from {csv_path}: {exc}"


# ---------------------------------------------------------------------------
# Tool definitions (JSON schema fed to Claude)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file from disk. "
            "Use this to examine existing scripts, configs, or data samples."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write text content to a file on disk (creates parent directories). "
            "Use this to write the final ETL Python script and any helper files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Destination file path (e.g. 'pipeline.py').",
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "infer_schema",
        "description": (
            "Infer column types, nullability, and candidate primary keys from a CSV file. "
            "Returns a JSON object describing the schema. "
            "Call this when the pipeline description mentions a CSV source."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "csv_path": {
                    "type": "string",
                    "description": "Path to the CSV file to analyse.",
                }
            },
            "required": ["csv_path"],
        },
    },
]

# ---------------------------------------------------------------------------
# Dispatcher: execute a tool call by name
# ---------------------------------------------------------------------------


def _dispatch_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute the named tool and return its string result."""
    if name == "read_file":
        return _read_file(tool_input["path"])
    if name == "write_file":
        return _write_file(tool_input["path"], tool_input["content"])
    if name == "infer_schema":
        return _infer_schema(tool_input["csv_path"])
    return f"ERROR: Unknown tool '{name}'"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert data-pipeline engineer. Your job is to generate complete, \
runnable Python ETL scripts that use pandas (and optionally sqlalchemy, boto3, \
or google-cloud-bigquery) based on a plain-English description provided by the user.

You have three tools available:
- read_file   – inspect existing files on disk
- write_file  – write the final ETL script (and any helper files)
- infer_schema – analyse a CSV file and return its schema

Workflow:
1. Carefully read the pipeline description.
2. If a CSV source file is mentioned and exists locally, call infer_schema to \
   understand the data before writing code.
3. Generate a complete, working Python ETL script:
   - Use pandas for data manipulation.
   - Include clear comments and a __main__ block so it can be run directly.
   - Handle common issues: type coercion, null cleaning, deduplication.
   - Where cloud credentials or connection strings are needed, read them from \
     environment variables and document which variables are required.
4. Call write_file to persist the script to the path requested by the user.
5. Reply with a short summary of what the pipeline does and any setup \
   instructions (env variables, pip packages, etc.).

Always write idiomatic, production-quality Python. Do not truncate the script.
"""


# ---------------------------------------------------------------------------
# PipelineAgent
# ---------------------------------------------------------------------------


class PipelineAgent:
    """An AI agent that builds ETL pipelines from plain English descriptions.

    Parameters
    ----------
    api_key:
        Anthropic API key. Defaults to the ``ANTHROPIC_API_KEY`` env variable.
    model:
        Claude model to use. Defaults to ``claude-sonnet-4-6``.
    max_tokens:
        Maximum tokens in the response. Defaults to 8192.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        description: str,
        output_path: str = "pipeline.py",
        verbose: bool = True,
    ) -> str:
        """Generate an ETL pipeline script from a plain-English description.

        Parameters
        ----------
        description:
            Plain-English description of the pipeline
            (e.g. "read CSV from S3, clean nulls, write to BigQuery").
        output_path:
            Where to write the generated Python script.
        verbose:
            If True, print tool calls and intermediate messages to stdout.

        Returns
        -------
        str
            The final text reply from Claude summarising the pipeline.
        """
        user_message = (
            f"{description}\n\n"
            f"Write the pipeline script to: {output_path}"
        )
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        # Agentic loop: keep calling Claude until it stops requesting tools
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )

            if verbose:
                self._print_response_summary(response)

            # Append the full assistant content to history
            messages.append({"role": "assistant", "content": response.content})

            # If Claude is done, extract and return the final text reply
            if response.stop_reason == "end_turn":
                return self._extract_text(response)

            # If Claude wants to use tools, execute them and feed results back
            if response.stop_reason == "tool_use":
                tool_results = self._execute_tool_calls(response.content, verbose)
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason – surface it and stop
            return f"Pipeline generation stopped unexpectedly: {response.stop_reason}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_tool_calls(
        self,
        content_blocks: list[Any],
        verbose: bool,
    ) -> list[dict[str, Any]]:
        """Execute all tool_use blocks in *content_blocks* and return results."""
        results: list[dict[str, Any]] = []
        for block in content_blocks:
            if block.type != "tool_use":
                continue
            tool_name = block.name
            tool_input = block.input  # already a dict
            if verbose:
                print(f"  [tool] {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:120]})")
            result_text = _dispatch_tool(tool_name, tool_input)
            if verbose and len(result_text) < 400:
                print(f"  [result] {result_text}")
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                }
            )
        return results

    @staticmethod
    def _extract_text(response: anthropic.types.Message) -> str:
        """Return the concatenated text from all TextBlock items in the response."""
        parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)

    @staticmethod
    def _print_response_summary(response: anthropic.types.Message) -> None:
        """Print a brief summary of Claude's response to stdout."""
        text_blocks = sum(1 for b in response.content if b.type == "text")
        tool_blocks = sum(1 for b in response.content if b.type == "tool_use")
        tools_used = [
            b.name for b in response.content if b.type == "tool_use"
        ]
        print(
            f"[Claude] stop_reason={response.stop_reason} "
            f"text_blocks={text_blocks} tool_calls={tool_blocks}"
            + (f" tools={tools_used}" if tools_used else "")
        )
