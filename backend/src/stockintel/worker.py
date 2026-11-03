"""Scheduled worker. Milestone 1 records a heartbeat; later milestones add data jobs."""

import argparse
import logging
import socket

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import Engine

from stockintel.config import get_settings
from stockintel.db import get_engine, worker_heartbeats

log = logging.getLogger("stockintel.worker")


def record_heartbeat(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(worker_heartbeats.insert().values(hostname=socket.gethostname()))
    log.info("heartbeat recorded")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="record one heartbeat and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    engine = get_engine()
    record_heartbeat(engine)  # Fails loudly at start-up if the database is unavailable.
    if args.once:
        return

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        record_heartbeat,
        "interval",
        seconds=get_settings().worker_heartbeat_seconds,
        args=[engine],
        max_instances=1,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
