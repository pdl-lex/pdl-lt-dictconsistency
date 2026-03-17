import reflex as rx
from pathlib import Path

# Security limits
MAX_ZIP_EXTRACT_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB per file


class FileState(rx.State):
    """Base state for file management. Holds loaded XML file metadata."""

    directory_path: str = ""
    upload_mode: str = "Verzeichnispfad"
    session_dir: str = ""
    xml_files_data: list[dict] = []
    error_message: str = ""
    is_loading: bool = False

    @rx.var
    def file_count(self) -> int:
        """Return number of loaded XML files."""
        return len(self.xml_files_data)

    @rx.var
    def has_files(self) -> bool:
        """Check if any XML files are loaded."""
        return len(self.xml_files_data) > 0

    def set_directory_path(self, value: str) -> None:
        """Update the directory path input."""
        self.directory_path = value

    def set_upload_mode(self, value: str) -> None:
        """Switch between directory path and file upload mode."""
        self.upload_mode = value

    @rx.event
    def handle_key_down(self, key: str) -> None:
        """Trigger directory scan on Enter key."""
        if key == "Enter":
            return FileState.scan_xml_files

    def _is_valid_xml(self, file_path: Path) -> bool:
        """Check if file starts with XML content (magic bytes)."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(100)
                return header.lstrip().startswith(
                    b"<?xml"
                ) or header.lstrip().startswith(b"<")
        except Exception as e:
            print(f"Error in: {file_path}: {e}")
            return False

    def _create_session_dir(self) -> Path:
        """Create and return session-specific temp directory."""
        import tempfile

        if not self.session_dir:
            session_id = self.router.session.client_token
            self.session_dir = str(
                Path(tempfile.gettempdir()) / f"reflex_upload_{session_id}"
            )

        session_path = Path(self.session_dir)
        session_path.mkdir(parents=True, exist_ok=True)
        return session_path

    def _extract_zip(self, zip_path: Path, extract_to: Path) -> int:
        """Extract XML files from ZIP with size and path traversal protection."""
        import zipfile

        xml_count = 0
        total_size = 0

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for member in zip_ref.namelist():
                    # SECURITY: prevent path traversal (Zip Slip)
                    if (
                        ".." in member
                        or member.startswith("/")
                        or member.startswith("\\")
                    ):
                        print(f"SECURITY: dangerous path skipped: {member}")
                        continue

                    # SECURITY: size check (zip bomb protection)
                    member_info = zip_ref.getinfo(member)
                    total_size += member_info.file_size
                    if total_size > MAX_ZIP_EXTRACT_SIZE:
                        raise ValueError(
                            f"ZIP too large (>{MAX_ZIP_EXTRACT_SIZE / 1024 / 1024:.0f}MB)"
                        )

                    # Only extract XML files
                    if member.lower().endswith(".xml"):
                        # Preserve relative path structure within extract dir
                        member_path = Path(member)
                        target_path = extract_to / member_path

                        # SECURITY: verify resolved path stays inside extract dir
                        if not target_path.resolve().is_relative_to(
                            extract_to.resolve()
                        ):
                            print(f"SECURITY: path escape attempt: {member}")
                            continue

                        # Create subdirectories as needed
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        with zip_ref.open(member) as source, open(
                            target_path, "wb"
                        ) as target:
                            target.write(source.read())

                        # SECURITY: verify actual XML content
                        if self._is_valid_xml(target_path):
                            xml_count += 1
                        else:
                            print(f"SECURITY: fake XML removed: {member}")
                            target_path.unlink()

        except zipfile.BadZipFile:
            raise ValueError("Ungültige oder beschädigte ZIP-Datei")

        return xml_count

    async def handle_upload(self, files: list[rx.UploadFile]):
        """Process uploaded files with security checks."""
        import shutil

        print(f"handle_upload called with {len(files)} files")

        self.is_loading = True
        self.error_message = ""
        self.xml_files_data = []
        yield

        try:
            session_path = self._create_session_dir()
            print(f"Session path: {session_path}")

            # Clear previous uploads
            for item in session_path.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

            total_xml_files = 0

            for file in files:
                print(f"Processing: {file.filename}")

                # SECURITY: sanitize filename
                safe_filename = Path(file.filename).name
                if not safe_filename:
                    print("SECURITY: invalid filename skipped")
                    continue

                file_path = session_path / safe_filename
                content = await file.read()

                # SECURITY: size check
                if len(content) > MAX_FILE_SIZE:
                    self.error_message = f"Datei {safe_filename} zu groß (max {MAX_FILE_SIZE / 1024 / 1024:.0f}MB)"
                    continue

                with open(file_path, "wb") as f:
                    f.write(content)

                print(f"Saved: {file_path}")

                if file.filename.lower().endswith(".zip"):
                    try:
                        xml_count = self._extract_zip(file_path, session_path)
                        total_xml_files += xml_count
                        file_path.unlink()
                    except ValueError as e:
                        self.error_message = str(e)
                        file_path.unlink()

                elif file.filename.lower().endswith(".xml"):
                    # SECURITY: verify actual XML content
                    if self._is_valid_xml(file_path):
                        total_xml_files += 1
                    else:
                        print(f"SECURITY: fake XML removed: {file.filename}")
                        file_path.unlink()
                        self.error_message = (
                            f"{file.filename} ist keine gültige XML-Datei"
                        )

            self.directory_path = str(session_path)

            # Scan session directory for XML files
            files_data: list[dict] = []
            for file_path in session_path.rglob("*.xml"):
                try:
                    if not self._is_valid_xml(file_path):
                        file_path.unlink()
                        continue

                    relative_path = file_path.relative_to(session_path)
                    subdir = (
                        str(relative_path.parent)
                        if relative_path.parent != Path(".")
                        else "."
                    )
                    size_bytes = file_path.stat().st_size
                    size_kb = round(size_bytes / 1024, 2)

                    files_data.append(
                        {
                            "subdir": subdir,
                            "filename": file_path.name,
                            "size_kb": size_kb,
                        }
                    )
                except Exception:
                    continue

            self.xml_files_data = files_data
            print(f"Found: {len(files_data)} XML files")

        except Exception as e:
            print(f"ERROR: {e}")
            self.error_message = f"Fehler beim Upload: {str(e)}"
        finally:
            self.is_loading = False

    async def scan_xml_files(self):
        """Recursively scan directory for XML files."""
        self.is_loading = True
        self.error_message = ""
        self.xml_files_data = []

        # Validate input before yield so all error paths are covered by finally
        if not self.directory_path:
            self.error_message = "Bitte geben Sie einen Verzeichnispfad ein."
            self.is_loading = False
            return

        path = Path(self.directory_path).expanduser()

        if not path.exists():
            self.error_message = "Verzeichnis existiert nicht."
            self.is_loading = False
            return

        if not path.is_dir():
            self.error_message = "Pfad ist kein Verzeichnis."
            self.is_loading = False
            return

        yield

        try:
            files_data: list[dict] = []
            for file_path in path.rglob("*.xml"):
                try:
                    if not self._is_valid_xml(file_path):
                        continue

                    relative_path = file_path.relative_to(path)
                    subdir = (
                        str(relative_path.parent)
                        if relative_path.parent != Path(".")
                        else "."
                    )
                    size_bytes = file_path.stat().st_size
                    size_kb = round(size_bytes / 1024, 2)

                    files_data.append(
                        {
                            "subdir": subdir,
                            "filename": file_path.name,
                            "size_kb": size_kb,
                        }
                    )
                except Exception as e:
                    print(e)
                    continue

            self.xml_files_data = files_data

            if len(files_data) == 0:
                self.error_message = "Keine XML-Dateien im Verzeichnis gefunden."

        except PermissionError:
            self.error_message = "Keine Berechtigung für dieses Verzeichnis."
        except Exception as e:
            self.error_message = f"Fehler: {str(e)}"
        finally:
            self.is_loading = False
