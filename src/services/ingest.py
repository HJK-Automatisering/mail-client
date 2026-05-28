#######################################################################
import logging
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from client import GraphClient
from models import Attachment, Email
#######################################################################

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Europe/Copenhagen")
_FILE_ATTACHMENT = "#microsoft.graph.fileAttachment"

class IngestService:
    '''
    Description:
        Handles ingestion of new emails and their attachments from Graph API
        into the database and internal attachments volume.

    Flow:
        None

    Args:
        client (GraphClient): Graph API client for fetching data.
        internal_attachment_dir (str): Path to store downloaded attachment files.

    Returns:
        None

    Raises:
        None

    '''

    def __init__(self, client: GraphClient, internal_attachment_dir: str) -> None:
        '''
        Description:
            Initialises the service and ensures the attachment directory exists.

        Flow:
            1. Store client and directory path.
            2. Create the directory if it does not already exist.

        Args:
            client (GraphClient): Graph API client.
            internal_attachment_dir (str): Path to the internal attachments directory.

        Returns:
            None

        Raises:
            None

        '''

        self._client = client
        self._attachment_dir = internal_attachment_dir

        os.makedirs(internal_attachment_dir, exist_ok=True)

    def run(self, session: Session) -> None:
        '''
        Description:
            Fetches all emails from Graph API and ingests any not already
            present in the database.

        Flow:
            1. Fetch all emails from Graph API.
            2. For each email, skip if already present in the database.
            3. Create an Email record.
            4. Save any file attachments to disk and create Attachment records.
            5. Log inserted/skipped/attachments counts.

        Args:
            session (Session): Active database session.

        Returns:
            None

        Raises:
            None

        '''

        logger.info("Fetching emails from Graph API")
        emails = self._client.fetch_emails()
        logger.info("Fetched %d emails", len(emails))

        inserted = skipped = attachments_saved = 0

        for raw in emails:
            if session.get(Email, raw["id"]):
                skipped += 1
                continue

            email = Email(
                id=raw["id"],
                sender=raw["from"]["emailAddress"]["address"].lower(),
                subject=raw.get("subject", ""),
                received_at=datetime.fromisoformat(
                    raw["receivedDateTime"].replace("Z", "+00:00")
                ).astimezone(_TZ),
                body=raw.get("body", {}).get("content", ""))
            session.add(email)

            for raw_att in raw.get("attachments", []):
                if raw_att.get("@odata.type") != _FILE_ATTACHMENT:
                    continue
                saved = self._save_attachment(raw["id"], raw_att)
                if saved:
                    session.add(saved)
                    attachments_saved += 1

            inserted += 1

        logger.info(
            "Emails inserted=%d skipped=%d attachments_saved=%d",
            inserted, skipped, attachments_saved)

    def _save_attachment(self, message_id: str, raw: dict) -> Attachment | None:
        '''
        Description:
            Downloads a single attachment and saves it to disk with a UUID
            filename. Returns an Attachment ORM object on success.

        Flow:
            1. Generate a UUID for the attachment.
            2. Download raw bytes via Graph API.
            3. Write bytes to disk under the UUID filename.
            4. Return a populated Attachment instance with metadata.

        Args:
            message_id (str): Graph API message ID the attachment belongs to.
            raw (dict): Raw attachment object from Graph API.

        Returns:
            Attachment | None: Populated Attachment instance, or None if download failed.

        Raises:
            None

        '''

        attachment_id = str(uuid.uuid4())
        try:
            data = self._client.fetch_attachment_bytes(message_id, raw["id"])
            path = os.path.join(self._attachment_dir, attachment_id)
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            logger.exception(
                "Failed to download attachment '%s' for message %s — skipping",
                raw.get("name"), message_id)
            return None

        return Attachment(
            id=attachment_id,
            email_id=message_id,
            original_filename=raw.get("name", "unknown"),
            content_type=raw.get("contentType", "application/octet-stream"),
            size_bytes=raw.get("size"))
