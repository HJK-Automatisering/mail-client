#######################################################################
import msal
import requests

from config import Config
#######################################################################

class GraphClient:
    '''
    Description:
        HTTP client for the Microsoft Graph API. Handles token acquisition
        and provides methods for email ingestion, attachment download,
        and sending emails.

    Flow:
        None

    Args:
        config (Config): Application configuration with Azure AD credentials.

    Returns:
        None

    Raises:
        None

    '''

    _SCOPE = ["https://graph.microsoft.com/.default"]

    def __init__(self, config: Config) -> None:
        '''
        Description:
            Initialises the client with configuration and builds the
            Azure AD authority URL.

        Flow:
            1. Store config reference.
            2. Construct authority URL from tenant ID.

        Args:
            config (Config): Application configuration.

        Returns:
            None

        Raises:
            None

        '''

        self._config = config
        self._authority = f"https://login.microsoftonline.com/{config.tenant_id}"

    def _token(self) -> str:
        '''
        Description:
            Acquires an OAuth2 access token using client credentials flow.

        Flow:
            1. Instantiate a ConfidentialClientApplication.
            2. Request a token for the Graph API scope.
            3. Return the access token string.

        Args:
            None

        Returns:
            str: Bearer token for use in the Authorization header.

        Raises:
            RuntimeError: If token acquisition fails or the response is missing access_token.

        '''

        app = msal.ConfidentialClientApplication(
            self._config.client_id,
            authority=self._authority,
            client_credential=self._config.client_secret)
        result = app.acquire_token_for_client(scopes=self._SCOPE)
        if not result or "access_token" not in result:
            raise RuntimeError("Failed to acquire token")
        return result["access_token"]

    def _headers(self) -> dict[str, str]:
        '''
        Description:
            Builds the Authorization header dict for a Graph API request.

        Flow:
            1. Acquire a fresh token.
            2. Return header dict with Bearer token.

        Args:
            None

        Returns:
            dict[str, str]: Authorization header.

        Raises:
            RuntimeError: If token acquisition fails.

        '''

        return {"Authorization": f"Bearer {self._token()}"}

    def fetch_emails(self) -> list[dict]:
        '''
        Description:
            Fetches all messages from the configured mailbox, following
            pagination until all pages are retrieved.

        Flow:
            1. Build initial request URL with top=50, ordered by receivedDateTime.
            2. GET messages, expanding attachment metadata.
            3. Follow @odata.nextLink until no more pages remain.
            4. Return combined list of raw message dicts.

        Args:
            None

        Returns:
            list[dict]: Raw Graph API message objects.

        Raises:
            requests.HTTPError: If any request fails.

        '''

        url = (
            f"https://graph.microsoft.com/v1.0/users/{self._config.user_id}/mailFolders/inbox/messages"
            "?$top=50&$orderby=receivedDateTime desc&$expand=attachments")
        results = []
        while url:
            resp = requests.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return results

    def fetch_attachment_bytes(self, message_id: str, attachment_id: str) -> bytes:
        '''
        Description:
            Downloads the raw binary content of a single attachment using
            the /$value endpoint.

        Flow:
            1. Build URL for the attachment /$value endpoint.
            2. GET the binary content.
            3. Return raw bytes.

        Args:
            message_id (str): Graph API message ID.
            attachment_id (str): Graph API attachment ID.

        Returns:
            bytes: Raw file content.

        Raises:
            requests.HTTPError: If the request fails.

        '''

        url = (
            f"https://graph.microsoft.com/v1.0/users/{self._config.user_id}"
            f"/messages/{message_id}/attachments/{attachment_id}/$value")
        resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.content

    def delete_email(self, message_id: str) -> None:
        '''
        Description:
            Permanently deletes an email from the mailbox via Graph API.

        Flow:
            1. Build DELETE URL for the message.
            2. Send request and raise on error.

        Args:
            message_id (str): Graph API message ID to delete.

        Returns:
            None

        Raises:
            requests.HTTPError: If the request fails.

        '''

        url = (
            f"https://graph.microsoft.com/v1.0/users/{self._config.user_id}"
            f"/messages/{message_id}")
        resp = requests.delete(url, headers=self._headers())
        resp.raise_for_status()

    def send_email(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        attachments: list[dict] | None = None) -> None:
        '''
        Description:
            Sends an email from the configured mailbox via Graph API.

        Flow:
            1. Normalise recipient(s) to a list.
            2. Build message payload with subject, body, and recipients.
            3. Attach file attachments if provided.
            4. POST to the sendMail endpoint.

        Args:
            to (str | list[str]): One or more recipient email addresses.
            subject (str): Email subject line.
            body (str): Plain text message body.
            attachments (list[dict] | None): Optional list of Graph API fileAttachment objects.

        Returns:
            None

        Raises:
            requests.HTTPError: If sending fails.

        '''

        recipients = [to] if isinstance(to, str) else to
        url = f"https://graph.microsoft.com/v1.0/users/{self._config.user_id}/sendMail"
        message: dict = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in recipients]}
        if attachments:
            message["attachments"] = attachments
        resp = requests.post(url, headers=self._headers(), json={"message": message})
        resp.raise_for_status()
