"""Automated E2E trading pipeline — Scanner → AI → Risk → Trade."""
from app.modules.trading_pipeline.pipeline import run_pipeline_for_scan

__all__ = ["run_pipeline_for_scan"]
