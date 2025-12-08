# Outamation SFTP Package

A robust asynchronous SFTP client utility package built on Paramiko for Outamation projects. Provides connection pooling, file operations, and batch processing capabilities.

## Features

- **Connection Pooling**: Efficiently reuses SFTP connections per project
- **Automatic Reconnection**: Detects and reconnects stale connections
- **File Operations**: Upload, download, and remove files from SFTP servers
- **Batch Processing**: Process multiple files with automatic API integration
- **Upload Detection**: Waits for files to be fully uploaded before processing
- **Retry Logic**: Built-in retry mechanism for API calls

## Installation

Install from the local repository:

```bash
pip install -e pkg-sftp/
```

Or install as a dependency in your `pyproject.toml`:

```toml
dependencies = [
    "outamation_pkg_sftp @ file:///path/to/core-libs-python/pkg-sftp"
]
```

## Dependencies

- `paramiko==3.0.0` - SFTP client library
- `python-dotenv==1.0.0` - Environment variable management
- `requests==2.31.0` - HTTP library for API calls
- `outamation_pkg_logger` (optional) - Logging utilities

## Quick Start

### Basic SFTP Connection

```python
from outamation_pkg_sftp import SftpService
import asyncio

async def main():
    # Initialize the service
    sftp_service = SftpService()
    
    # Configure connection
    client_config = {
        "project_id": "my_project",
        "sftp_host": "sftp.example.com",
        "sftp_port": "22",
        "sftp_user": "username",
        "sftp_pass": "password"
    }
    
    # Connect to SFTP server
    sftp, transport = await sftp_service.connect_to_sftp(client_config)
    
    if sftp:
        print("Connected successfully!")
        # Close when done
        sftp_service.close_all_connections()

asyncio.run(main())
```

### Using Connection Pool

The connection pool automatically reuses connections for the same `project_id`:

```python
from outamation_pkg_sftp import SftpService

sftp_service = SftpService()

# First call creates a new connection
sftp1, transport1 = sftp_service.get_sftp_connection(client_config)

# Second call reuses the existing connection (same project_id)
sftp2, transport2 = sftp_service.get_sftp_connection(client_config)

# sftp1 and sftp2 are the same connection
assert sftp1 == sftp2
```

### Upload a File

```python
success = await sftp_service.upload_file_to_folder(
    path="/remote/directory",
    project_id="my_project",
    file_path="/local/path/document.pdf",
    project_config=client_config
)

if success:
    print("File uploaded successfully!")
```

### Download a File

```python
local_path = await sftp_service.get_file_from_sftp(
    path="/remote/directory/document.pdf",
    client_config=client_config
)

if local_path:
    print(f"File downloaded to: {local_path}")
    # Process the file...
```

### Remove a File

```python
success = await sftp_service.remove_file_from_path(
    file_path="/remote/directory/document.pdf",
    client_config=client_config
)

if success:
    print("File removed successfully!")
```

## Advanced Usage

### Polling for Files with Batch Processing

Monitor an SFTP directory for new PDF files and process them in batches:

```python
import os

# Set environment variables for directory structure
os.environ["SOURCE_FILES"] = "input"
os.environ["IN_Progress_Path"] = "in_progress"
os.environ["PROFILE_CODE"] = "my_profile"
os.environ["DOC_AI_API_URL"] = "https://api.example.com/process"

project_config = {
    "project_id": "my_project",
    "sftp_host": "sftp.example.com",
    "sftp_port": "22",
    "sftp_user": "username",
    "sftp_pass": "password",
    "path": "/base/directory",
    "secret": "your_api_secret"
}

# Poll SFTP and process files in batches of 5
await sftp_service.poll_sftp_for_project(
    project_config=project_config,
    interval=60,  # Not currently used
    api_url="https://api.example.com/process"
)
```

This will:
1. Monitor `/base/directory/input` for new PDF files
2. Wait for files to be fully uploaded
3. Move files to `/base/directory/in_progress/MMDDYYYY/`
4. Process files in batches of 5
5. Call the API with HMAC authentication for each batch

### Call API for Files

Send file information to an API endpoint with HMAC authentication:

```python
files = [
    {"filename": "doc1.pdf", "backup_path": "/backup/doc1.pdf"},
    {"filename": "doc2.pdf", "backup_path": "/backup/doc2.pdf"}
]

success = await sftp_service.call_api_for_files(
    project_config=project_config,
    files=files,
    uploaded_by="Admin",
    source="Manual Upload",
    api_url="https://api.example.com/process",
    profile_code="my_profile"
)
```

### Check if File is Fully Uploaded

```python
sftp, _ = sftp_service.get_sftp_connection(client_config)

is_ready = sftp_service.is_file_fully_uploaded(
    sftp=sftp,
    filepath="/remote/directory/document.pdf",
    delay=1.2  # Wait time in seconds between checks
)

if is_ready:
    print("File is fully uploaded and ready for processing")
```

## Configuration

### Client Configuration Dictionary

```python
client_config = {
    "project_id": str,      # Unique identifier for the project
    "sftp_host": str,       # SFTP server hostname or IP
    "sftp_port": str|int,   # SFTP server port (default: 22)
    "sftp_user": str,       # SFTP username
    "sftp_pass": str,       # SFTP password
    "path": str,            # Base path on SFTP server (optional)
    "secret": str           # API secret for HMAC auth (optional)
}
```

### Environment Variables

```bash
# For polling functionality
SOURCE_FILES=input                      # Source directory name
IN_Progress_Path=in_progress           # In-progress directory name
PROFILE_CODE=default_profile           # Profile code for API calls
DOC_AI_API_URL=https://api.example.com # API endpoint URL

# For logging (if using outamation_pkg_logger)
LOG_LEVEL=INFO                         # Logging level
```

## API Reference

### `SftpService`

Main service class for SFTP operations.

#### Methods

##### `__init__()`
Initialize the SFTP service with an empty connection pool.

##### `get_sftp_connection(client_config: Dict) -> Tuple[SFTPClient, Transport]`
Get or create an SFTP connection from the connection pool.

##### `close_all_connections()`
Close all active SFTP connections in the pool.

##### `connect_to_sftp(client_config: Dict) -> Tuple[SFTPClient, Transport]`
Create a new SFTP connection without using the connection pool.

##### `create_sftp_connection(host: str, port: int, username: str, password: str) -> Tuple[SFTPClient, Transport]`
Establish a new SFTP connection using the provided credentials.

##### `is_file_fully_uploaded(sftp: SFTPClient, filepath: str, delay: float = 1.2) -> bool`
Check if a file is fully uploaded by comparing file sizes after a delay.

##### `upload_file_to_folder(path: str, project_id: str, file_path: str, project_config: Dict) -> bool`
Upload a file to a remote SFTP folder.

##### `get_file_from_sftp(path: str, client_config: Dict) -> Optional[str]`
Download a file from SFTP to a temporary local directory.

##### `remove_file_from_path(file_path: str, client_config: Dict) -> bool`
Remove a file from the remote SFTP server.

##### `call_api_for_files(project_config: Dict, files: List[Dict], uploaded_by: str, source: str, api_url: str = None, profile_code: str = None) -> bool`
Call an API endpoint with batch file information using HMAC authentication.

##### `poll_sftp_for_project(project_config: Dict, interval: int, api_url: str, sftp: SFTPClient = None, source_files_dir: str = None, in_progress_dir: str = None)`
Poll an SFTP directory for new PDF files and process them in batches.

## Error Handling

The package includes comprehensive error handling and logging:

```python
from outamation_pkg_sftp import SftpService

sftp_service = SftpService()

try:
    sftp, transport = await sftp_service.connect_to_sftp(client_config)
    if not sftp:
        print("Failed to connect to SFTP server")
        return
    
    # Perform operations...
    success = await sftp_service.upload_file_to_folder(...)
    if not success:
        print("Upload failed")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    sftp_service.close_all_connections()
```

## Best Practices

1. **Reuse Connections**: Use `get_sftp_connection()` with the same `project_id` to reuse connections
2. **Close Connections**: Always call `close_all_connections()` when done
3. **Handle Errors**: Check return values for `None` or `False` to detect failures
4. **Environment Variables**: Use environment variables for configuration in production
5. **Logging**: Install `outamation_pkg_logger` for better logging support

## Troubleshooting

### Connection Issues

```python
# Check if connection is active
sftp, transport = sftp_service.get_sftp_connection(client_config)
if transport and transport.is_active():
    print("Connection is active")
else:
    print("Connection is not active")
```

### File Upload Verification

```python
# Verify file exists after upload
sftp, _ = sftp_service.get_sftp_connection(client_config)
try:
    stat = sftp.stat("/remote/path/file.pdf")
    print(f"File size: {stat.st_size} bytes")
except FileNotFoundError:
    print("File not found")
```

## License

Proprietary - Outamation

## Contributing

This package is part of the Outamation core libraries. For contributions or issues, please contact the development team.

## Changelog

### Version 0.1.0
- Initial release
- Connection pooling support
- File upload, download, and removal operations
- Batch processing with API integration
- HMAC authentication for API calls
