from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from janus_api.conf import settings

import asyncpg

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validated_ident(name: str) -> str:
    if not _IDENT_RE.fullmatch(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


TIMESCALE_PG_NAME = _validated_ident(settings.TIMESCALE_PG_NAME)



class TimescaleStorage:
    """
    Lightweight TimescaleDB (Postgres) helper using asyncpg.

    Schema (see SQL below) uses:
      - time (timestamptz)
      - session_id bigint
      - handle_id bigint
      - plugin text
      - room_id text (optional if available)
      - peer_id text (optional)
      - metrics jsonb   -- map of metric keys -> numeric values

    Usage:
      storage = TimescaleStorage(dsn="postgresql://user:pass@db:5432/dbname")
      await storage.connect()
      await storage.insert_metric(...)
      await storage.close()
    """

    def __init__(self, dsn: str, min_pool_size: int = 1, max_pool_size: int = 10):
        self._dsn = dsn
        self._pool: Optional[asyncpg.pool.Pool] = None
        self._min = min_pool_size
        self._max = max_pool_size

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min,
            max_size=self._max,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def insert_metric(
            self,
            ts: Optional[float],
            session_id: Optional[int],
            handle_id: Optional[int],
            plugin: Optional[str],
            room_id: Optional[str],
            peer_id: Optional[str],
            metrics: Dict[str, Any],
    ) -> None:
        """
        Insert a new timeseries point. metrics should be JSON-serializable.
        ts: epoch seconds or None (server will use now()).
        """
        if not self._pool:
            raise RuntimeError("storage not connected")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        async with self._pool.acquire() as conn:
            query = (
                f'INSERT INTO "{TIMESCALE_PG_NAME}" '
                "(time, session_id, handle_id, plugin, room_id, peer_id, metrics) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)"
            )
            await conn.execute(
                query,
                dt,
                session_id,
                handle_id,
                plugin,
                room_id,
                peer_id,
                json.dumps(metrics),
            )

    async def query_aggregate(
            self,
            start: str,
            stop: str,
            group_by: str,
            metric_key: str,
            *,
            plugin: Optional[str] = None,
            room_id: Optional[str] = None,
            peer_id: Optional[str] = None,
            time_bucket: str = "1 minute",
    ) -> List[Dict[str, Any]]:
        """
        Returns aggregated series: time_bucket, label (group), avg(value), sum(value), max(value)
        group_by: 'plugin'|'room_id'|'peer_id'|'handle_id'
        start/stop: ISO timestamps
        metric_key: key inside metrics JSON to aggregate
        """
        if not self._pool:
            raise RuntimeError("storage not connected")

        allowed_group_bys = {"plugin", "room_id", "peer_id", "handle_id"}
        if group_by not in allowed_group_bys:
            raise ValueError(f"Invalid group_by: {group_by!r}")
        group_by_col = group_by

        # note: $3 currently used in query for time_bucket interval - adjust parameters order for asyncpg
        # We'll set args as: [start, stop, time_bucket_interval, metric_key, ...filters]
        final_args = [start, stop, time_bucket, metric_key]
        conditions = []
        idx = 5
        if plugin:
            conditions.append(f"plugin = ${idx}")
            final_args.append(plugin)
            idx += 1
        if room_id:
            conditions.append(f"room_id = ${idx}")
            final_args.append(room_id)
            idx += 1
        if peer_id:
            conditions.append(f"peer_id = ${idx}")
            final_args.append(peer_id)
            idx += 1
        filter_sql = "".join(f" AND {c}" for c in conditions)

        sql_ = f"""
        SELECT
          time_bucket($3::interval, time) AS bucket,
          {group_by_col} AS label,
          avg((metrics->>$4)::double precision) AS avg_val,
          sum((metrics->>$4)::double precision) AS sum_val,
          max((metrics->>$4)::double precision) AS max_val
        FROM "{TIMESCALE_PG_NAME}"
        WHERE time >= $1 AND time <= $2
        {filter_sql}
        GROUP BY bucket, {group_by_col}
        ORDER BY bucket ASC;
        """

        async with self._pool.acquire() as conn:
            records = await conn.fetch(sql_, *final_args)
            return [
                {
                    "bucket": r["bucket"].isoformat(),
                    "label": r["label"],
                    "avg": r["avg_val"],
                    "sum": r["sum_val"],
                    "max": r["max_val"],
                }
                for r in records
            ]
