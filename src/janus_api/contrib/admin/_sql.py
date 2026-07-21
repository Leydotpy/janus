import re

from janus_api.conf import settings

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validated_ident(name: str) -> str:
    if not _IDENT_RE.fullmatch(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


TIMESCALE_PG_NAME = _validated_ident(settings.TIMESCALE_PG_NAME)
_TABLE_NAME = f'"{TIMESCALE_PG_NAME}"'
_ROOM_1M_VIEW = _validated_ident(f"{TIMESCALE_PG_NAME}_room_1m")
_ROOM_1M_VIEW_NAME = f'"{_ROOM_1M_VIEW}"'

CREATE_STATEMENTS = [
    # create extension
    "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;",
    # create table
    f"""
            CREATE TABLE IF NOT EXISTS {_TABLE_NAME}
            (
                time
                timestamptz
                NOT
                NULL,
                session_id
                bigint,
                handle_id
                bigint,
                plugin
                text,
                room_id
                text,
                peer_id
                text,
                metrics
                jsonb
            );
            """,
    # create hypertable
    f"SELECT create_hypertable('{TIMESCALE_PG_NAME}', 'time', if_not_exists => TRUE);",
    # indexes
    f"CREATE INDEX IF NOT EXISTS idx_janus_metrics_plugin ON {_TABLE_NAME} (plugin);",
    f"CREATE INDEX IF NOT EXISTS idx_janus_metrics_room ON {_TABLE_NAME} (room_id);",
    f"CREATE INDEX IF NOT EXISTS idx_janus_metrics_handle ON {_TABLE_NAME} (handle_id);",
]

# Continuous aggregate (materialized view) for per-room 1-minute aggregates.
# You can add more continuous aggregates for other metrics or time buckets.
CONTINUOUS_AGG_SQL = f"""
CREATE MATERIALIZED VIEW IF NOT EXISTS {_ROOM_1M_VIEW_NAME}
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 minute', time)           AS bucket,
  room_id,
  avg((metrics->>'inbound_bytes')::double precision) AS avg_inbound_bytes,
  avg((metrics->>'outbound_bytes')::double precision) AS avg_outbound_bytes,
  sum((metrics->>'packets_lost')::double precision)  AS sum_packets_lost
FROM {_TABLE_NAME}
WHERE room_id IS NOT NULL
GROUP BY bucket, room_id;
"""

# Add a policy: keep aggregate data fresh for 7 days of materialization window (adjust as needed)
CONTINUOUS_AGG_POLICY_SQL = f"""
SELECT add_continuous_aggregate_policy('{_ROOM_1M_VIEW}',
    start_interval => INTERVAL '1 day',
    end_interval   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');
"""

# Retention policy for raw hypertable: keep raw points for 30 days (adjust as needed)
RETENTION_POLICY_SQL = f"SELECT add_retention_policy('{TIMESCALE_PG_NAME}', INTERVAL '30 days');"
# -- create the materialized view for 1-minute per-room aggregates
# -- policy to maintain the continuous aggregate (refresh window)
# -- retention policy for raw hypertable (delete raw points older than 30 days)
AGGREGATE_SQL = f"""

CREATE MATERIALIZED VIEW IF NOT EXISTS {_ROOM_1M_VIEW_NAME}
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 minute', time)           AS bucket,
  room_id,
  avg((metrics->>'inbound_bytes')::double precision) AS avg_inbound_bytes,
  avg((metrics->>'outbound_bytes')::double precision) AS avg_outbound_bytes,
  sum((metrics->>'packets_lost')::double precision)  AS sum_packets_lost
FROM {_TABLE_NAME}
WHERE room_id IS NOT NULL
GROUP BY bucket, room_id;


SELECT add_continuous_aggregate_policy(
  '{_ROOM_1M_VIEW}',
  start_interval => INTERVAL '1 day',
  end_interval => INTERVAL '1 minute',
  schedule_interval => INTERVAL '1 minute'
);


SELECT add_retention_policy('{TIMESCALE_PG_NAME}', INTERVAL '30 days');
"""
