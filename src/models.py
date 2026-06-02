#######################################################################
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base
#######################################################################

class Email(Base):
    '''
    Description:
        ORM model representing an ingested email from the mailbox.

    Flow:
        None

    Args:
        id (str): Graph API message ID (primary key).
        sender (str): Normalised sender address (lowercase).
        subject (str | None): Email subject line.
        received_at (datetime): Timestamp when the email was received.
        body (str | None): Plain text body content.
        body_raw (str | None): Raw HTML body content.
        attachments: Related Attachment records.

    Returns:
        None

    Raises:
        None

    '''

    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String(1000), primary_key=True)
    sender: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(1000))
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    body_raw: Mapped[str | None] = mapped_column(Text)

    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="email", cascade="all, delete-orphan")

class Attachment(Base):
    '''
    Description:
        ORM model representing a file attachment linked to an ingested email.

    Flow:
        None

    Args:
        id (str): UUID assigned on ingest — primary key and filename on disk.
        email_id (str): Foreign key to the parent Email.
        original_filename (str): Original filename from Graph API.
        content_type (str | None): MIME type of the attachment.
        size_bytes (int | None): File size in bytes.

    Returns:
        None

    Raises:
        None

    '''

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_id: Mapped[str] = mapped_column(
        String(1000), ForeignKey("emails.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    email: Mapped["Email"] = relationship("Email", back_populates="attachments")
