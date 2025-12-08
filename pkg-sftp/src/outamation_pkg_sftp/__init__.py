import os
import tempfile
import time
from typing import Optional, Dict, Tuple, List, Any
import asyncio
import json
import hmac
import hashlib
import requests
import paramiko

from outamation_pkg_logger import setup_logging, trace

logger = setup_logging(console_level="INFO", rotation="20 MB", retention="30 days")


class SftpService:
    def __init__(self):
        """Initialize the SFTP service with an empty connection pool."""
        self._sftp_connections: Dict[
            str, Tuple[paramiko.SFTPClient, paramiko.Transport]
        ] = {}

    @trace
    def get_sftp_connection(
        self, client_config: Dict[str, Any]
    ) -> Tuple[Optional[paramiko.SFTPClient], Optional[paramiko.Transport]]:
        project_id = str(client_config.get("project_id", ""))
        if not project_id:
            logger.error("project_id is required in client_config")
            return None, None

        conn_info = self._sftp_connections.get(project_id)

        # Check if existing connection is active
        if conn_info and conn_info[1].is_active():
            logger.info(f"[{project_id}] Using existing SFTP connection.")
            return conn_info[0], conn_info[1]

        # Close stale connection if exists
        if conn_info:
            try:
                conn_info[0].close()
                conn_info[1].close()
                logger.info(f"[{project_id}] Closed stale SFTP connection.")
            except Exception as e:
                logger.error(f"[{project_id}] Error closing stale SFTP connection: {e}")
            finally:
                del self._sftp_connections[project_id]

        # Create new connection
        try:
            transport = paramiko.Transport(
                (client_config["sftp_host"], int(client_config["sftp_port"]))
            )
            transport.use_compression(False)
            transport.connect(
                username=client_config["sftp_user"], password=client_config["sftp_pass"]
            )
            transport.set_keepalive(30)
            sftp = paramiko.SFTPClient.from_transport(transport)
            self._sftp_connections[project_id] = (sftp, transport)
            logger.info(f"[{project_id}] New SFTP connection established.")
            return sftp, transport
        except Exception as e:
            logger.error(f"[{project_id}] Failed to establish SFTP connection: {e}")
            return None, None

    @trace
    def close_all_connections(self):
        """Close all active SFTP connections in the pool."""
        for project_id, (sftp, transport) in list(self._sftp_connections.items()):
            try:
                sftp.close()
                transport.close()
                logger.info(f"[{project_id}] SFTP connection closed.")
            except Exception as e:
                logger.error(f"[{project_id}] Failed to close SFTP connection: {e}")
        self._sftp_connections.clear()

    @trace
    async def connect_to_sftp(
        self, client_config: Dict[str, Any]
    ) -> Tuple[Optional[paramiko.SFTPClient], Optional[paramiko.Transport]]:
        """
        Create a new SFTP connection without using the connection pool.

        Args:
            client_config: Dictionary containing connection details

        Returns:
            Tuple of (SFTPClient, Transport) or (None, None) if connection fails
        """
        try:
            transport = paramiko.Transport(
                (client_config["sftp_host"], int(client_config["sftp_port"]))
            )
            transport.connect(
                username=client_config["sftp_user"], password=client_config["sftp_pass"]
            )
            transport.set_keepalive(30)
            sftp = paramiko.SFTPClient.from_transport(transport)
            logger.info(
                f"[{client_config.get('project_id', 'N/A')}] New SFTP connection established."
            )
            return sftp, transport
        except Exception as e:
            logger.error(
                f"[{client_config.get('project_id', 'N/A')}] Failed to connect to SFTP: {e}"
            )
            return None, None

    @trace
    def create_sftp_connection(
        self, host: str, port: int, username: str, password: str
    ) -> Tuple[Optional[paramiko.SFTPClient], Optional[paramiko.Transport]]:
        """
        Establish a new SFTP connection using the provided credentials.

        Args:
            host: SFTP server hostname
            port: SFTP server port
            username: SFTP username
            password: SFTP password

        Returns:
            Tuple of (SFTPClient, Transport) or (None, None) on failure
        """
        try:
            transport = paramiko.Transport((host, int(port)))
            transport.use_compression(False)
            transport.connect(username=username, password=password)
            transport.set_keepalive(30)
            sftp = paramiko.SFTPClient.from_transport(transport)
            logger.info(f"New SFTP connection established to {host}:{port}.")
            return sftp, transport
        except Exception as e:
            logger.error(f"Failed to establish SFTP connection to {host}:{port}: {e}")
            return None, None

    @trace
    def is_file_fully_uploaded(
        self, sftp: paramiko.SFTPClient, filepath: str, delay: float = 1.2
    ) -> bool:
        """
        Check if a file is fully uploaded by comparing file sizes after a delay.

        Args:
            sftp: Active SFTP client
            filepath: Remote file path
            delay: Time to wait between size checks (default: 1.2 seconds)

        Returns:
            True if file size is stable, False otherwise
        """
        try:
            size1 = sftp.stat(filepath).st_size
            time.sleep(delay)
            size2 = sftp.stat(filepath).st_size
            return size1 == size2
        except IOError:
            return False

    @trace
    async def upload_file_to_folder(
        self, path: str, project_id: str, file_path: str, project_config: Dict[str, Any]
    ) -> bool:
        """
        Upload a file to a remote SFTP folder.

        Args:
            path: Remote directory path
            project_id: Project identifier
            file_path: Local file path to upload
            project_config: Project configuration with SFTP credentials

        Returns:
            True if upload successful, False otherwise
        """
        if not project_config:
            logger.error(f"[{project_id}] Project configuration not found.")
            return False

        sftp, _ = self.get_sftp_connection(project_config)
        if not sftp:
            logger.error(f"[{project_id}] SFTP client not initialized.")
            return False

        try:
            # Create directory if it doesn't exist
            try:
                sftp.stat(path)
            except FileNotFoundError:
                sftp.mkdir(path)
                logger.info(f"[{project_id}] Created directory: {path}")

            # Upload file
            remote_path = os.path.join(path, os.path.basename(file_path)).replace(
                "\\", "/"
            )
            sftp.put(file_path, remote_path)
            logger.info(f"[{project_id}] Uploaded file to SFTP: {remote_path}")
            return True
        except Exception as e:
            logger.error(f"[{project_id}] Failed to upload to SFTP: {e}")
            return False

    @trace
    async def get_file_from_sftp(
        self, path: str, client_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        Download a file from SFTP to a temporary local directory.

        Args:
            path: Remote file path
            client_config: Client configuration with SFTP credentials

        Returns:
            Local file path if successful, None otherwise
        """
        sftp, _ = self.get_sftp_connection(client_config)
        if not sftp:
            logger.error(
                f"[{client_config.get('project_id', 'N/A')}] SFTP client not initialized."
            )
            return None

        try:
            file_name = os.path.basename(path)
            tmp_dir = tempfile.mkdtemp()
            local_path = os.path.join(tmp_dir, file_name)
            sftp.get(remotepath=path, localpath=local_path)
            logger.info(
                f"[{client_config.get('project_id', 'N/A')}] Downloaded file from SFTP: {path} -> {local_path}"
            )
            return local_path
        except Exception as e:
            logger.error(
                f"[{client_config.get('project_id', 'N/A')}] Couldn't get the file: {e}"
            )
            return None

    @trace
    async def remove_file_from_path(
        self, file_path: str, client_config: Dict[str, Any]
    ) -> bool:
        """
        Remove a file from the remote SFTP server.

        Args:
            file_path: Remote file path to remove
            client_config: Client configuration with SFTP credentials

        Returns:
            True if removal successful, False otherwise
        """
        sftp, _ = self.get_sftp_connection(client_config)
        if not sftp:
            logger.error(
                f"[{client_config.get('project_id', 'N/A')}] SFTP client not initialized."
            )
            return False

        try:
            sftp.remove(file_path)
            logger.info(
                f"[{client_config.get('project_id', 'N/A')}] Removed file: {file_path}"
            )
            return True
        except Exception as e:
            logger.error(
                f"[{client_config.get('project_id', 'N/A')}] Could not remove the file: {e}"
            )
            return False

    @trace
    async def call_api_for_files(
        self,
        project_config: Dict[str, Any],
        files: List[Dict[str, str]],
        uploaded_by: str,
        source: str,
        api_url: Optional[str] = None,
        profile_code: Optional[str] = None,
    ) -> bool:
        """
        Call an API endpoint with batch file information using HMAC authentication.

        Args:
            project_config: Project configuration containing secret and project_id
            files: List of file dictionaries with backup_path information
            uploaded_by: Name/identifier of the uploader
            source: Source of the files (e.g., "SFTP DROP")
            api_url: API endpoint URL (defaults to DOC_AI_API_URL env var)
            profile_code: Profile code for processing (defaults to PROFILE_CODE env var)

        Returns:
            True if API call successful, False otherwise
        """
        if not api_url:
            api_url = os.getenv("DOC_AI_API_URL")
        if not profile_code:
            profile_code = os.getenv("PROFILE_CODE", "")

        secret = project_config.get("secret")
        project_id = str(project_config.get("project_id", ""))
        MAX_RETRIES = 5
        RETRY_DELAY = 2

        if not secret:
            logger.error(
                f"[{project_id}] API secret not found in project configuration."
            )
            return False

        if not api_url:
            logger.error(f"[{project_id}] API URL is not set.")
            return False

        # Prepare batch data
        batch = [
            {
                "profileName": profile_code,
                "sftp_document_path": file["backup_path"],
                "MD5_checksum": "",
                "rotate_pages": False,
                "skip_text": False,
            }
            for file in files
        ]

        body = {"batch": batch, "uploaded_by": uploaded_by, "source": source}
        body_str = json.dumps(body, separators=(",", ":"))
        timestamp = str(int(time.time()))
        message = f"{timestamp}.{body_str}"
        signature = hmac.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

        headers = {
            "x-hmac-timestamp": timestamp,
            "x-hmac-signature": signature,
            "x-project-id": project_id,
            "Content-Type": "application/json",
        }

        # Retry logic
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"[{project_id}] Calling API for {len(files)} files. Attempt {attempt}/{MAX_RETRIES}"
                )
                response = requests.post(
                    url=api_url, data=body_str, headers=headers, timeout=(5, 30)
                )
                response.raise_for_status()
                logger.info(
                    f"[{project_id}] API call successful. Status: {response.status_code}, Response: {response.text}"
                )
                return True
            except requests.exceptions.RequestException as e:
                logger.error(f"[{project_id}] API call failed (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    logger.info(f"[{project_id}] Retrying in {RETRY_DELAY} seconds...")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logger.error(f"[{project_id}] All retry attempts failed.")
                    return False

        return False

    @trace
    async def poll_sftp_for_project(
        self,
        project_config: Dict[str, Any],
        interval: int,
        api_url: str,
        sftp: Optional[paramiko.SFTPClient] = None,
        source_files_dir: Optional[str] = None,
        in_progress_dir: Optional[str] = None,
    ):
        """
        Poll an SFTP directory for new PDF files and process them in batches.

        Args:
            project_config: Project configuration with path and credentials
            interval: Polling interval in seconds (not used in current implementation)
            api_url: API endpoint for file processing
            sftp: Optional pre-existing SFTP client (creates new if not provided)
            source_files_dir: Source directory name (defaults to SOURCE_FILES env var)
            in_progress_dir: In-progress directory name (defaults to IN_Progress_Path env var)
        """
        project_config["project_id"] = str(project_config.get("project_id", ""))
        project_id = project_config["project_id"]

        if not source_files_dir:
            source_files_dir = os.getenv("SOURCE_FILES", "input")
        if not in_progress_dir:
            in_progress_dir = os.getenv("IN_Progress_Path", "in_progress")

        # Get or create SFTP connection
        if not sftp:
            sftp, _ = self.get_sftp_connection(project_config)

        if not sftp:
            logger.error(f"[{project_id}] SFTP client not initialized.")
            return

        try:
            # Ensure base directory exists
            base_path = project_config.get("path", "")
            try:
                sftp.stat(base_path)
            except FileNotFoundError:
                logger.info(f"[{project_id}] Creating base directory: {base_path}")
                sftp.mkdir(base_path)

            # Define input and backup directories
            input_dir = f"{base_path}/{source_files_dir}"
            backup_dir = f"{base_path}/{in_progress_dir}/{time.strftime('%m%d%Y')}"

            # Create directories if they don't exist
            for directory in [input_dir, backup_dir]:
                try:
                    sftp.stat(directory)
                except FileNotFoundError:
                    logger.info(f"[{project_id}] Creating directory: {directory}")
                    # Create parent directories recursively if needed
                    parts = directory.split("/")
                    current_path = ""
                    for part in parts:
                        if not part:
                            continue
                        current_path = (
                            f"{current_path}/{part}" if current_path else part
                        )
                        try:
                            sftp.stat(current_path)
                        except FileNotFoundError:
                            sftp.mkdir(current_path)

            # Process files
            batch = []

            try:
                for attr in sftp.listdir_iter(input_dir, read_aheads=1):
                    try:
                        # Filter PDF files only
                        if not attr.filename.lower().endswith(".pdf"):
                            continue
                    except Exception as e:
                        logger.error(
                            f"[{project_id}] Error checking file extension: {e}"
                        )
                        continue

                    src_path = f"{input_dir}/{attr.filename}"

                    # Wait for file to be fully uploaded
                    try:
                        if not self.is_file_fully_uploaded(sftp, src_path):
                            logger.debug(
                                f"[{project_id}] File still uploading: {attr.filename}"
                            )
                            continue
                    except Exception as e:
                        logger.error(
                            f"[{project_id}] Error checking if file is fully uploaded: {e}"
                        )
                        continue

                    # Move file to backup directory
                    backup_path = f"{backup_dir}/{attr.filename}"
                    try:
                        # Remove existing backup file if any
                        try:
                            sftp.remove(backup_path)
                            logger.debug(
                                f"[{project_id}] Removed existing backup file: {backup_path}"
                            )
                        except FileNotFoundError:
                            pass

                        sftp.rename(src_path, backup_path)
                        logger.info(
                            f"[{project_id}] Moved file to backup: {attr.filename}"
                        )

                        batch.append(
                            {"filename": attr.filename, "backup_path": backup_path}
                        )

                        # Process batch when 5 files collected
                        if len(batch) == 5:
                            logger.info(
                                f"[{project_id}] Processing batch of 5 files and making API call"
                            )
                            success = await self.call_api_for_files(
                                project_config,
                                batch,
                                uploaded_by="Scheduler",
                                source="SFTP DROP",
                                api_url=api_url,
                            )
                            if not success:
                                logger.error(
                                    f"[{project_id}] Failed to send API request after retries."
                                )
                            batch.clear()

                    except Exception as e:
                        logger.error(
                            f"[{project_id}] Error moving file {attr.filename}: {e}"
                        )
                        continue

                # Process remaining files (< 5)
                if batch:
                    logger.info(
                        f"[{project_id}] Processing leftover {len(batch)} files and making API call"
                    )
                    success = await self.call_api_for_files(
                        project_config,
                        batch,
                        uploaded_by="Scheduler",
                        source="SFTP DROP",
                        api_url=api_url,
                    )
                    if not success:
                        logger.error(
                            f"[{project_id}] Failed to send API request after retries."
                        )
                    batch.clear()

            except Exception as e:
                logger.error(f"[{project_id}] Error processing files: {e}")

        except Exception as e:
            logger.error(f"[{project_id}] Error during SFTP polling: {e}")
            self.close_all_connections()


# Package exports
__all__ = ["SftpService"]

# Package metadata
__version__ = "0.1.0"
__author__ = "Outamation Team"
__description__ = "A robust asynchronous SFTP client utility package built on Paramiko"
