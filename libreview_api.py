import requests
import hashlib
import logging
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from typing import Optional, Dict, Any

# --- Set up logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LibreViewAPI")
urllib3.disable_warnings(InsecureRequestWarning)

# --- Custom Exception Classes ---
class LibreViewAPIError(Exception):
    """General error for LibreView API."""
    pass

class LibreViewAuthenticationError(LibreViewAPIError):
    """Raised on authentication failures with LibreView API."""
    pass

class LibreViewTimeoutError(LibreViewAPIError):
    """Raised when a request times out."""
    pass

class LibreViewResponseError(LibreViewAPIError):
    """Raised when a non-JSON or unexpected response is received."""
    pass

class LibreViewAPI:
    """
    Handles authentication and data requests to the LibreView API.
    """

    def __init__(self, email: str, password: str, default_version: str = "4.16.0", product: str = "llu.android", timeout: int = 10) -> None:
        self.email: str = email
        self.password: str = password
        self.default_version: str = default_version
        self.product: str = product
        self.timeout: int = timeout
        self.token: Optional[str] = None
        self.account_id: Optional[str] = None
        self.login_url: str = "https://api.libreview.io/llu/auth/login"
        self.account_url: str = "https://api-us.libreview.io/account"
        self.session: requests.Session = requests.Session()
        self.login_and_setup()

    def login_and_setup(self) -> None:
        """Authenticate and set up account id."""
        self.login()
        self.fetch_and_hash_account_id()

    def login(self) -> None:
        """Authenticate with the LibreView API and obtain a session token."""
        payload: Dict[str, str] = {
            "email": self.email,
            "password": self.password
        }
        headers: Dict[str, str] = self.get_headers(api_version=self.default_version, include_auth=False, include_account=False)
        headers["Content-Type"] = "application/json"
        try:
            response: requests.Response = self.session.post(self.login_url, json=payload, headers=headers, verify=False, timeout=self.timeout)
        except requests.Timeout:
            logger.error("Login request timed out.")
            raise LibreViewTimeoutError("Login request timed out.")
        except Exception as ex:
            logger.error(f"Unexpected error during login: {ex}")
            raise LibreViewAPIError(f"Unexpected error during login: {ex}")

        try:
            data: Dict[str, Any] = response.json()
        except ValueError:
            logger.error("Login response was not JSON.")
            raise LibreViewResponseError("Login response was not JSON.")

        if response.status_code == 401:
            logger.error("Authentication failed: Invalid credentials.")
            raise LibreViewAuthenticationError("Invalid credentials.")
        if response.status_code != 200 or "data" not in data:
            logger.error(f"Failed to log in: {data}")
            raise LibreViewAPIError(f"Failed to log in: {data}")
        self.token = str(data["data"]["authTicket"]["token"])
        logger.debug(f"[SUCCESS]: Received an authentication token for {self.email}!\n")

    def fetch_and_hash_account_id(self) -> None:
        """
        Fetches account ID from /account API and hashes it.
        ALWAYS uses version 4.7 for this endpoint.
        """
        headers: Dict[str, str] = self.get_headers(api_version="4.7", include_auth=True, include_account=False)
        try:
            response: requests.Response = self.session.get(self.account_url, headers=headers, verify=False, timeout=self.timeout)
        except requests.Timeout:
            logger.error("Account ID request timed out.")
            raise LibreViewTimeoutError("Account ID request timed out.")
        except Exception as ex:
            logger.error(f"Unexpected error fetching account id: {ex}")
            raise LibreViewAPIError(f"Unexpected error fetching account id: {ex}")

        try:
            data: Dict[str, Any] = response.json()
        except ValueError:
            logger.error("Account ID response was not JSON.")
            raise LibreViewResponseError("Account ID response was not JSON.")

        if response.status_code != 200 or "data" not in data:
            logger.error(f"Failed to get account data: {data}")
            raise LibreViewAPIError(f"Failed to get account data: {data}")
        raw_id: str = str(data["data"]["user"]["id"])
        self.account_id = hashlib.sha256(raw_id.encode('utf-8')).hexdigest()
        logger.debug(f"[SUCCESS]: Retrieved the Account-Id: '{raw_id}' and calculated the SHA256 hash: {self.account_id} for future API requests.\n")

    def get_headers(self, api_version: Optional[str] = None, include_auth: bool = True, include_account: bool = True) -> Dict[str, str]:
        """
        Returns headers for requests. Allows specifying API version.

        Args:
            api_version (str, optional): API version to use.
            include_auth (bool, optional): Include Authorization header.
            include_account (bool, optional): Include Account-Id header.
        """
        version: str = api_version if api_version else self.default_version
        headers: Dict[str, str] = {
            "version": version,
            "product": self.product,
            "Accept": "application/json"
        }
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if include_account and self.account_id:
            headers["Account-Id"] = self.account_id
        return headers

    def request(self, method: str, url: str, api_version: Optional[str] = None, **kwargs: Any) -> requests.Response:
        """
        Makes a request. Allows overriding API version per call.
        Handles token expiry and retries once.

        Args:
            method (str): HTTP method.
            url (str): The endpoint URL.
            api_version (str, optional): API version to use.
            **kwargs: Additional arguments for requests.

        Returns:
            Response object.
        """
        headers: Dict[str, str] = self.get_headers(api_version=api_version)
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
            kwargs.pop("headers")
        try:
            response: requests.Response = self.session.request(method, url, headers=headers, timeout=self.timeout, verify=False, **kwargs)
        except requests.Timeout:
            logger.error(f"Request to {url} timed out.")
            raise LibreViewTimeoutError(f"Request to {url} timed out.")
        except Exception as ex:
            logger.error(f"Unexpected error during request to {url}: {ex}")
            raise LibreViewAPIError(f"Unexpected error during request: {ex}")

        if response.status_code == 401:
            logger.warning("Token expired or invalid. Refreshing...")
            self.login_and_setup()
            headers = self.get_headers(api_version=api_version)
            try:
                response = self.session.request(method, url, headers=headers, timeout=self.timeout, verify=False, **kwargs)
            except requests.Timeout:
                logger.error(f"Retry request to {url} timed out.")
                raise LibreViewTimeoutError(f"Retry request to {url} timed out.")
            except Exception as ex:
                logger.error(f"Unexpected error during retry to {url}: {ex}")
                raise LibreViewAPIError(f"Unexpected error during retry request: {ex}")
        return response

    def get_patient_id(self) -> Optional[str]:
        """
        Retrieves the patientId from the https://api.libreview.io/llu/connections API.

        Returns:
            Optional[str]: The patientId if available, else None.
        """
        url = "https://api.libreview.io/llu/connections"
        response = self.request("GET", url)
        try:
            connections = response.json()
        except ValueError:
            logger.error("Connections response was not JSON.")
            raise LibreViewResponseError("Connections response was not JSON.")

        data = connections.get("data")
        if not data or not isinstance(data, list) or len(data) == 0:
            logger.warning("No connections found.")
            return None
        if "patientId" not in data[0]:
            logger.warning("First connection does not contain a 'patientId' key.")
            return None
        return data[0].get("patientId")

    def get_graph_data(self, patientId: Optional[str] = None, api_version: str = "4.16.0") -> Dict[str, Any]:
        """
        Query the /graph endpoint for a specific connection.
        If no patientId is provided, it will attempt to fetch it using get_patient_id.

        Args:
            patientId (str, optional): The patient's ID. If not provided, it will be fetched automatically.
            api_version (str, optional): API version to use. Defaults to "4.16.0".

        Returns:
            dict: Graph data and metadata.

        Raises:
            LibreViewAPIError: If no graph data is returned or patientId cannot be determined.
        """
        if patientId is None:
            logger.debug("No patientId provided. Attempting to fetch the first patientId.")
            patientId = self.get_patient_id()
            if patientId is None:
                logger.error("Unable to fetch patientId. Cannot proceed with get_graph_data.")
                raise LibreViewAPIError("No patientId available to query graph data.")

        url: str = f"https://api.libreview.io/llu/connections/{patientId}/graph"
        response: requests.Response = self.request("GET", url, api_version=api_version)

        try:
            data: Dict[str, Any] = response.json()
        except ValueError:
            logger.error("Graph data response was not JSON.")
            raise LibreViewResponseError("Graph data response was not JSON.")

        if "data" not in data:
            logger.error(f"No graph data returned: {data}")
            raise LibreViewAPIError(f"No graph data returned: {data}")

        return data["data"]