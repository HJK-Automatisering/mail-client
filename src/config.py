#######################################################################
import os
from dataclasses import dataclass

from dotenv import load_dotenv
#######################################################################

@dataclass(frozen=True)
class Config:
    '''
    Description:
        Immutable configuration object populated from environment variables.

    Flow:
        None

    Args:
        tenant_id (str): Azure AD tenant ID.
        client_id (str): App registration client ID.
        client_secret (str): App registration client secret.
        user_id (str): Mailbox user ID or UPN to ingest from.
        fetch_interval_seconds (int): Polling interval in seconds.
        db_url (str): SQLAlchemy-compatible database connection URL.
        internal_attachment_dir (str): Path to store incoming attachment files.
        external_attachment_dir (str): Path to the shared outbound volume.
        retention_days (int): Days to retain emails and attachments before deletion.
        api_key (str): Key required in API request headers.

    Returns:
        None

    Raises:
        None

    '''

    tenant_id: str
    client_id: str
    client_secret: str
    user_id: str
    fetch_interval_seconds: int
    db_url: str
    internal_attachment_dir: str
    external_attachment_dir: str
    retention_days: int
    api_key: str

    @classmethod
    def from_env(cls) -> "Config":
        '''
        Description:
            Constructs a Config instance from environment variables.

        Flow:
            1. Load .env file if present.
            2. Build MSSQL connection URL from server, database, and optional credentials.
            3. Construct and return a frozen Config instance.

        Args:
            None

        Returns:
            Config: Populated configuration instance.

        Raises:
            KeyError: If a required environment variable is missing.

        '''

        load_dotenv()

        driver = os.environ.get("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
        server = os.environ["MSSQL_SERVER"]
        database = os.environ["MSSQL_DATABASE"]
        username = os.environ.get("MSSQL_USERNAME")
        password = os.environ.get("MSSQL_PASSWORD")

        if username and password:
            db_url = (
                f"mssql+pyodbc://{username}:{password}@{server}/{database}"
                f"?driver={driver.replace(' ', '+')}&TrustServerCertificate=yes")
        else:
            db_url = (
                f"mssql+pyodbc://@{server}/{database}"
                f"?driver={driver.replace(' ', '+')}"
                f"&TrustServerCertificate=yes&trusted_connection=yes")

        return cls(
            tenant_id=os.environ["TENANT_ID"],
            client_id=os.environ["CLIENT_ID"],
            client_secret=os.environ["CLIENT_SECRET"],
            user_id=os.environ["USER_ID"],
            fetch_interval_seconds=int(os.environ.get("FETCH_INTERVAL_SECONDS", "300")),
            db_url=db_url,
            internal_attachment_dir=os.environ.get("INTERNAL_ATTACHMENT_DIR", "./attachments"),
            external_attachment_dir=os.environ.get("EXTERNAL_ATTACHMENT_DIR", "/shared"),
            retention_days=int(os.environ.get("RETENTION_DAYS", "30")),
            api_key=os.environ["API_KEY"])
