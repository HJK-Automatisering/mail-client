#######################################################################
import asyncio
import logging

from client import GraphClient
from config import Config
from db import Database
from services.cleanup import CleanupService
from services.ingest import IngestService
#######################################################################

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("worker")

async def main() -> None:
    '''
    Description:
        Entry point for the worker process. Runs ingest and cleanup in a
        continuous loop with a configurable sleep interval between cycles.

    Flow:
        1. Load configuration from environment variables.
        2. Initialise database and create tables if needed.
        3. Instantiate Graph client, ingest service, and cleanup service.
        4. Log startup message.
        5. Loop indefinitely:
            a. Open a database session.
            b. Run ingest to fetch new emails and attachments.
            c. Run cleanup to delete old emails and external files.
            d. Sleep for FETCH_INTERVAL_SECONDS before the next cycle.

    Args:
        None

    Returns:
        None

    Raises:
        Exception: Cycle failures are caught, logged, and do not stop the loop.

    '''

    config = Config.from_env()

    db = Database(config.db_url)
    db.create_tables()

    client = GraphClient(config)
    ingest = IngestService(client, config.internal_attachment_dir)
    cleanup = CleanupService(client, config.internal_attachment_dir, config.external_attachment_dir, config.retention_days)

    logger.info("Worker started — interval %ds", config.fetch_interval_seconds)

    while True:
        with db.session() as session:
            try:
                ingest.run(session)
                cleanup.run(session)
            except Exception:
                logger.exception("Cycle failed")

        await asyncio.sleep(config.fetch_interval_seconds)

if __name__ == "__main__":
    asyncio.run(main())
