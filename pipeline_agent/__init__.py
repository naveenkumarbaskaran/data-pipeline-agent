"""data-pipeline-agent: Build ETL pipelines from plain English descriptions."""

from .agent import PipelineAgent
from .schema_inferrer import SchemaInferrer

__all__ = ["PipelineAgent", "SchemaInferrer"]
__version__ = "0.1.0"
