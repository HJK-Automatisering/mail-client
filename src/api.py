#######################################################################
import base64
import logging
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.orm import Session

from client import GraphClient
from config import Config
from db import Database
from models import Attachment, Email
#######################################################################

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("api")

config = Config.from_env()
db = Database(config.db_url)
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_key(key: str = Security(api_key_header)):
    '''
    Description:
        FastAPI dependency that validates the X-API-Key header against
        the configured API key.

    Flow:
        1. Compare the provided key to the configured key.
        2. Raise 403 if they do not match.

    Args:
        key (str): Value of the X-API-Key header.

    Returns:
        None

    Raises:
        HTTPException: 403 if the key is invalid.

    '''

    if key != config.api_key:
        raise HTTPException(status_code=403)

def get_session() -> Generator[Session, None, None]:
    '''
    Description:
        FastAPI dependency that yields a database session per request
        with automatic commit and rollback.

    Flow:
        1. Open a session via the Database context manager.
        2. Yield the session to the endpoint handler.
        3. Commit or rollback on exit.

    Args:
        None

    Returns:
        Generator[Session, None, None]: Active database session.

    Raises:
        None

    '''

    with db.session() as session:
        yield session

app = FastAPI(dependencies=[Depends(verify_key)])

class SendMailRequest(BaseModel):
    '''
    Description:
        Request body model for POST /send.

    Flow:
        None

    Args:
        to (str | list[str]): One or more recipient addresses.
        subject (str): Email subject.
        body (str): Plain text message body.
        files (list[str]): Absolute paths to files on the shared volume.

    Returns:
        None

    Raises:
        None

    '''

    to: str | list[str]
    subject: str
    body: str
    files: list[str] = []

@app.get("/emails")
def list_emails(
    since: datetime | None = None,
    sender: str | None = None,
    subject: str | None = None,
    session: Session = Depends(get_session)):
    '''
    Description:
        Returns ingested emails, newest first, with optional filters.

    Flow:
        1. Start a base query for all emails.
        2. Apply since, sender, and subject filters if provided.
        3. Order results by received_at descending.
        4. Return serialised list with nested attachment metadata.

    Args:
        since (datetime | None): Return only emails received after this time.
        sender (str | None): Filter by exact sender address.
        subject (str | None): Filter by subject substring (case-insensitive).
        session (Session): Injected database session.

    Returns:
        list[dict]: Serialised email objects with attachment metadata.

    Raises:
        None

    '''

    query = session.query(Email)
    if since:
        query = query.filter(Email.received_at >= since)
    if sender:
        query = query.filter(Email.sender == sender.lower())
    if subject:
        query = query.filter(Email.subject.ilike(f"%{subject}%"))

    emails = query.order_by(Email.received_at.desc()).all()

    return [
        {
            "id": e.id,
            "sender": e.sender,
            "subject": e.subject,
            "received_at": e.received_at,
            "attachments": [
                {
                    "id": a.id,
                    "filename": a.original_filename,
                    "content_type": a.content_type,
                    "size_bytes": a.size_bytes,
                    "download_url": f"/attachments/{a.id}/download"}
                for a in e.attachments]}
        for e in emails]

@app.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: str,
    session: Session = Depends(get_session)):
    '''
    Description:
        Downloads a single attachment file by its UUID.

    Flow:
        1. Look up the Attachment record in the database.
        2. Verify the file exists on disk.
        3. Return a FileResponse with the original filename and content type.

    Args:
        attachment_id (str): UUID of the attachment.
        session (Session): Injected database session.

    Returns:
        FileResponse: The attachment file with original filename and MIME type.

    Raises:
        HTTPException: 404 if the attachment record or file is not found.

    '''

    att = session.get(Attachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    path = os.path.join(config.internal_attachment_dir, attachment_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File missing from disk")

    return FileResponse(
        path=path,
        media_type=att.content_type,
        filename=att.original_filename)

@app.post("/send")
def send_email(request: SendMailRequest):
    '''
    Description:
        Sends an email via Microsoft Graph, optionally with file attachments
        read from the shared volume.

    Flow:
        1. For each file path, verify it exists on disk.
        2. Guess MIME type and base64-encode the file content.
        3. Build Graph API fileAttachment objects.
        4. Call GraphClient.send_email with the assembled payload.
        5. Return a status confirmation.

    Args:
        request (SendMailRequest): Validated request body.

    Returns:
        dict: {"status": "sent"} on success.

    Raises:
        HTTPException: 400 if a referenced file does not exist.
        HTTPException: 502 if the Graph API call fails.

    '''

    attachments = []
    for file_path in request.files:
        p = Path(file_path)
        if not p.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {file_path}")
        mime, _ = mimetypes.guess_type(p)
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": p.name,
            "contentType": mime or "application/octet-stream",
            "contentBytes": base64.b64encode(p.read_bytes()).decode()})

    try:
        GraphClient(config).send_email(
            request.to, request.subject, request.body, attachments or None)
    except Exception as e:
        logger.exception("Failed to send email")
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "sent"}
