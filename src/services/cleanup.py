#######################################################################
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from client import GraphClient
from models import Email
#######################################################################

logger = logging.getLogger(__name__)

class CleanupService:
    '''
    Description:
        Handles deletion of old emails, their internal attachment files,
        and old files on the external attachments volume.

    Flow:
        None

    Args:
        client (GraphClient): Graph API client for deleting emails remotely.
        internal_attachment_dir (str): Path to the internal attachments directory.
        external_attachment_dir (str): Path to the external attachments directory.
        retention_days (int): Number of days to retain data before deletion.

    Returns:
        None

    Raises:
        None

    '''

    def __init__(
        self,
        client: GraphClient,
        internal_attachment_dir: str,
        external_attachment_dir: str,
        retention_days: int = 30) -> None:
        '''
        Description:
            Initialises the service with client, directory paths, and retention period.

        Flow:
            1. Store all parameters as instance attributes.

        Args:
            client (GraphClient): Graph API client.
            internal_attachment_dir (str): Path to internal attachments directory.
            external_attachment_dir (str): Path to external attachments directory.
            retention_days (int): Days to retain data. Defaults to 30.

        Returns:
            None

        Raises:
            None

        '''

        self._client = client
        self._attachment_dir = internal_attachment_dir
        self._external_attachment_dir = external_attachment_dir
        self._retention_days = retention_days

    def run(self, session: Session) -> None:
        '''
        Description:
            Executes one full cleanup cycle: removes old emails and old
            external files.

        Flow:
            1. Clean up emails older than retention_days.
            2. Clean up external files older than retention_days.

        Args:
            session (Session): Active database session.

        Returns:
            None

        Raises:
            None

        '''

        self._cleanup_emails(session)
        self._cleanup_external()

    def _cleanup_emails(self, session: Session) -> None:
        '''
        Description:
            Deletes emails older than retention_days from disk, the database,
            and Graph API.

        Flow:
            1. Calculate cutoff datetime.
            2. Query emails received before the cutoff.
            3. For each old email:
                a. Delete attachment files from disk.
                b. Delete the database record (cascades to attachments).
                c. Delete the email from Graph API.

        Args:
            session (Session): Active database session.

        Returns:
            None

        Raises:
            None

        '''

        cutoff = datetime.now() - timedelta(days=self._retention_days)
        old = session.query(Email).filter(Email.received_at < cutoff).all()
        logger.info("Cleanup: removing %d old emails", len(old))

        for email in old:
            for att in email.attachments:
                path = os.path.join(self._attachment_dir, att.id)
                if os.path.exists(path):
                    os.remove(path)

            session.delete(email)

            try:
                self._client.delete_email(email.id)
            except Exception:
                logger.exception(
                    "Failed to delete email %s from Graph — already removed locally",
                    email.id)

    def _cleanup_external(self) -> None:
        '''
        Description:
            Deletes files older than retention_days from the external
            attachments directory based on file modification time.

        Flow:
            1. Return early if the directory does not exist.
            2. Calculate cutoff datetime.
            3. Iterate over files in the directory.
            4. Delete files whose mtime is older than the cutoff.
            5. Log the count of removed files if any.

        Args:
            None

        Returns:
            None

        Raises:
            None

        '''

        if not os.path.isdir(self._external_attachment_dir):
            return
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        removed = 0
        for filename in os.listdir(self._external_attachment_dir):
            path = os.path.join(self._external_attachment_dir, filename)
            if not os.path.isfile(path):
                continue
            if datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                os.remove(path)
                removed += 1
        if removed:
            logger.info("Cleanup: removed %d files from external dir", removed)
