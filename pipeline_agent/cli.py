"""
CLI for data-pipeline-agent.

Commands
--------
build
    Generate an ETL pipeline script from a plain-English description.

run
    Execute an already-generated pipeline script.

Examples
--------
    # Generate a pipeline script
    pipeline-agent build "read CSV from ./data.csv, clean nulls, write to output.csv" \\
        --output my_pipeline.py

    # Run the generated script
    pipeline-agent run --pipeline my_pipeline.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="data-pipeline-agent")
def cli() -> None:
    """data-pipeline-agent – Build ETL pipelines from plain English."""


# ---------------------------------------------------------------------------
# build command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("description")
@click.option(
    "--output",
    "-o",
    default="pipeline.py",
    show_default=True,
    help="Path where the generated pipeline script will be written.",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Claude model to use.",
)
@click.option(
    "--max-tokens",
    default=8192,
    show_default=True,
    help="Maximum tokens in the model response.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress intermediate tool-call output.",
)
def build(
    description: str,
    output: str,
    model: str,
    max_tokens: int,
    quiet: bool,
) -> None:
    """Generate an ETL pipeline from DESCRIPTION and write it to --output.

    DESCRIPTION is a plain-English description of the pipeline, for example:

    \b
        "Read CSV from S3 bucket my-bucket/data.csv, clean nulls in the
         'revenue' column, join with a Postgres users table on user_id,
         and write the result to BigQuery dataset analytics.sales"
    """
    # Lazy import so the CLI loads instantly even if anthropic is slow
    from .agent import PipelineAgent  # noqa: PLC0415

    console.print(
        Panel(
            f"[bold cyan]Building pipeline[/bold cyan]\n\n{description}\n\n"
            f"Output: [green]{output}[/green]  Model: [yellow]{model}[/yellow]",
            title="data-pipeline-agent",
            expand=False,
        )
    )

    agent = PipelineAgent(model=model, max_tokens=max_tokens)

    try:
        summary = agent.build(
            description=description,
            output_path=output,
            verbose=not quiet,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    # Show the generated script if it exists
    output_path = Path(output)
    if output_path.exists():
        console.print()
        console.print(
            Panel(
                Syntax(
                    output_path.read_text(encoding="utf-8"),
                    "python",
                    line_numbers=True,
                    theme="monokai",
                ),
                title=f"Generated: [green]{output}[/green]",
                expand=True,
            )
        )

    # Render Claude's summary as Markdown
    console.print()
    console.print(Panel(Markdown(summary), title="Pipeline Summary", expand=False))


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--pipeline",
    "-p",
    required=True,
    help="Path to the pipeline Python script to execute.",
)
@click.option(
    "--python",
    "python_exe",
    default=sys.executable,
    show_default=True,
    help="Python interpreter to use when running the pipeline.",
)
def run(pipeline: str, python_exe: str) -> None:
    """Execute an already-generated pipeline script.

    Example:

    \b
        pipeline-agent run --pipeline pipeline.py
    """
    pipeline_path = Path(pipeline)
    if not pipeline_path.exists():
        console.print(f"[bold red]Error:[/bold red] Pipeline script not found: {pipeline}")
        sys.exit(1)

    console.print(
        Panel(
            f"Running [green]{pipeline}[/green] with [yellow]{python_exe}[/yellow]",
            title="data-pipeline-agent run",
            expand=False,
        )
    )

    result = subprocess.run(
        [python_exe, str(pipeline_path)],
        capture_output=False,  # let stdout/stderr stream to the terminal
    )

    if result.returncode != 0:
        console.print(
            f"[bold red]Pipeline exited with code {result.returncode}[/bold red]"
        )
        sys.exit(result.returncode)
    else:
        console.print("[bold green]Pipeline completed successfully.[/bold green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
