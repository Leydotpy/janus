# migrations/init_db.py
"""
Automated TimescaleDB migration script.

This script:
 - creates the timescaledb extension if needed,
 - creates janus_metrics table,
 - creates hypertable,
 - creates indexes,
 - creates a continuous aggregate materialized view for per-room 1-minute averages,
 - creates a continuous-aggregate policy,
 - creates a retention policy.

Usage:
  pip install asyncpg
  TIMESCale_DSN=postgresql://user:pass@host:5432/dbname python migrations/init_db.py
"""
import logging

import asyncpg

from janus_api.conf import settings
from janus_api.contrib.admin._sql import *


logger = logging.getLogger(__name__)

# DSN = os.getenv("TIMESCALE_DSN", "postgresql://postgres:postgres@localhost:5432/janus_metrics")
DSN = getattr(settings, "TIMESCALE_DSN")


async def migrate():
    conn = await asyncpg.connect(dsn=DSN)
    try:
        for s in CREATE_STATEMENTS:
            await conn.execute(s)
        # Continuous aggregate
        await conn.execute(CONTINUOUS_AGG_SQL)
        # Try to add policy — ignore errors if already exists
        try:
            await conn.execute(CONTINUOUS_AGG_POLICY_SQL)
        except Exception as e:
            logger.exception("Warning: add_continuous_aggregate_policy may already exist or failed:", exc_info=e)
        # Retention policy
        try:
            await conn.execute(RETENTION_POLICY_SQL)
        except Exception as e:
            logger.exception("Warning: add_retention_policy may already exist or failed:", exc_info=e)

        logger.info("Migrations applied successfully.")
    finally:
        await conn.close()
