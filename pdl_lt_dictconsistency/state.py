import reflex as rx
from pathlib import Path

from .datasources_config import INDEX_DIR, load_datasources

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

    # --- "Vorliegende Daten" mode ---
    data_folders: list[str] = []
    selected_data_folder: str = ""
    # Visible tree items (dirs always, files of expanded dirs)
    data_tree: list[dict] = []
    tree_search: str = ""
    # Backend-only: never serialized to client
    _datasources: list[dict] = []        # loaded from datasources.json
    _dir_tree: list[dict] = []           # dirs from _dirs.json (tiny)
    _file_cache: dict[str, list] = {}    # dir_path → file items (lazy loaded)
    _selected_paths: list[str] = []
    _expanded_paths: list[str] = []

    @rx.var
    def file_count(self) -> int:
        return len(self.xml_files_data)

    @rx.var
    def has_files(self) -> bool:
        return len(self.xml_files_data) > 0

    @rx.var
    def has_data_tree(self) -> bool:
        return len(self.data_tree) > 0

    def set_directory_path(self, value: str) -> None:
        """Update the directory path input."""
        self.directory_path = value

    def set_upload_mode(self, value: str) -> None:
        self.upload_mode = value
        if value == "Vorliegende Daten":
            self._refresh_data_folders()

    @rx.event
    def handle_key_down(self, key: str) -> None:
        """Trigger directory scan on Enter key."""
        if key == "Enter":
            return FileState.scan_xml_files

    # ---- "Vorliegende Daten" helpers ----

    def _refresh_data_folders(self) -> None:
        self._datasources = load_datasources()
        self.data_folders = [s["name"] for s in self._datasources]
        self.selected_data_folder = ""
        self._reset_tree_state()

    def _get_source(self, name: str) -> dict | None:
        if not self._datasources:
            self._datasources = load_datasources()
        return next((s for s in self._datasources if s["name"] == name), None)

    def _reset_tree_state(self) -> None:
        self.data_tree = []
        self.tree_search = ""
        self._dir_tree = []
        self._file_cache = {}
        self._selected_paths = []
        self._expanded_paths = []

    def set_selected_data_folder(self, value: str) -> None:
        self.selected_data_folder = value
        self._reset_tree_state()

    # ---- index helpers ----

    def _index_base(self) -> Path:
        src = self._get_source(self.selected_data_folder)
        if src is None:
            return INDEX_DIR / self.selected_data_folder
        return INDEX_DIR / src["key"]

    def _file_json_path(self, dir_path: str) -> Path:
        """Return the path to the per-dir file JSON."""
        parts = dir_path.split("/")
        p = self._index_base()
        for part in parts[:-1]:
            p = p / part
        return p / f"{parts[-1]}.json"

    def _load_dir_files(self, dir_path: str) -> list[dict]:
        """Load and cache file items for one directory. Returns the items."""
        import json
        if dir_path in self._file_cache:
            return self._file_cache[dir_path]
        json_path = self._file_json_path(dir_path)
        items: list[dict] = []
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    items = json.load(f)
            except Exception:
                items = []
        new_cache = dict(self._file_cache)
        new_cache[dir_path] = items
        self._file_cache = new_cache
        return items

    def _load_all_file_caches(self) -> None:
        """Load file JSONs for every dir not yet cached (needed for full-text search)."""
        for item in self._dir_tree:
            if item["path"] not in self._file_cache:
                self._load_dir_files(item["path"])

    # ---- tree building ----

    def _rebuild_visible_tree(self) -> None:
        """Build data_tree: all visible dirs + files of expanded dirs."""
        expanded = set(self._expanded_paths)
        selected = set(self._selected_paths)
        visible: list[dict] = []
        for item in self._dir_tree:
            parts = item["path"].split("/")
            if len(parts) > 1:
                if not all("/".join(parts[:i]) in expanded for i in range(1, len(parts))):
                    continue
            is_expanded = item["path"] in expanded
            visible.append({
                "path": item["path"],
                "name": item["name"],
                "is_dir": True,
                "depth": item["depth"],
                "selected": item["path"] in selected,
                "expanded": is_expanded,
                "file_count": item.get("file_count", 0),
            })
            if is_expanded:
                for f in self._file_cache.get(item["path"], []):
                    visible.append({
                        "path": f["path"],
                        "name": f["name"],
                        "is_dir": False,
                        "depth": f["depth"],
                        "selected": f["path"] in selected,
                        "expanded": False,
                        "file_count": 0,
                    })
        self.data_tree = visible

    # ---- public events ----

    def set_tree_search(self, value: str) -> None:
        self.tree_search = value
        if not value:
            self._rebuild_visible_tree()
            return
        self._load_all_file_caches()
        search_lower = value.lower()
        visible_paths: set[str] = set()
        # Search dirs
        for item in self._dir_tree:
            if search_lower in item["name"].lower():
                visible_paths.add(item["path"])
                parts = item["path"].split("/")
                for i in range(1, len(parts)):
                    visible_paths.add("/".join(parts[:i]))
        # Search files
        for files in self._file_cache.values():
            for f in files:
                if search_lower in f["name"].lower():
                    visible_paths.add(f["path"])
                    parts = f["path"].split("/")
                    for i in range(1, len(parts)):
                        visible_paths.add("/".join(parts[:i]))
        selected = set(self._selected_paths)
        result: list[dict] = []
        for item in self._dir_tree:
            if item["path"] not in visible_paths:
                continue
            result.append({
                "path": item["path"], "name": item["name"], "is_dir": True,
                "depth": item["depth"], "selected": item["path"] in selected,
                "expanded": False, "file_count": item.get("file_count", 0),
            })
        for files in self._file_cache.values():
            for f in files:
                if f["path"] in visible_paths:
                    result.append({
                        "path": f["path"], "name": f["name"], "is_dir": False,
                        "depth": f["depth"], "selected": f["path"] in selected,
                        "expanded": False, "file_count": 0,
                    })
        result.sort(key=lambda x: x["path"])
        self.data_tree = result

    def toggle_expand(self, path: str) -> None:
        expanded = set(self._expanded_paths)
        if path in expanded:
            expanded = {p for p in expanded if p != path and not p.startswith(path + "/")}
        else:
            expanded.add(path)
            self._load_dir_files(path)
        self._expanded_paths = list(expanded)
        if not self.tree_search:
            self._rebuild_visible_tree()

    def select_all(self) -> None:
        self._load_all_file_caches()
        all_paths: set[str] = {item["path"] for item in self._dir_tree}
        for files in self._file_cache.values():
            for f in files:
                all_paths.add(f["path"])
        self._selected_paths = list(all_paths)
        self.data_tree = [{**item, "selected": True} for item in self.data_tree]

    def deselect_all(self) -> None:
        self._selected_paths = []
        self.data_tree = [{**item, "selected": False} for item in self.data_tree]

    def select_filtered_only(self) -> None:
        visible_file_paths = {item["path"] for item in self.data_tree if not item["is_dir"]}
        self._selected_paths = list(visible_file_paths)
        self.data_tree = [
            {**item, "selected": item["path"] in visible_file_paths}
            for item in self.data_tree
        ]

    def set_tree_item_selected(self, item_path: str, selected: bool) -> None:
        """Set selection; for dirs, load file JSONs and propagate to all file descendants."""
        is_dir = any(d["path"] == item_path for d in self._dir_tree)
        affected: set[str] = {item_path}
        if is_dir:
            prefix = item_path + "/"
            # Collect all descendant dirs
            desc_dirs = [d["path"] for d in self._dir_tree if d["path"].startswith(prefix)]
            for dp in [item_path] + desc_dirs:
                for f in self._load_dir_files(dp):
                    affected.add(f["path"])
        current = set(self._selected_paths)
        if selected:
            current |= affected
        else:
            current -= affected
        self._selected_paths = list(current)
        self.data_tree = [
            {**item, "selected": item["path"] in current}
            if item["path"] in affected else item
            for item in self.data_tree
        ]

    async def list_data_folder(self):
        import json

        if not self.selected_data_folder:
            return
        self.is_loading = True
        self.error_message = ""
        self._reset_tree_state()
        yield
        try:
            dirs_file = self._index_base() / "_dirs.json"
            if not dirs_file.exists():
                self.error_message = (
                    f"Kein Index für '{self.selected_data_folder}' vorhanden. "
                    "Bitte führen Sie 'python index_data.py' im Projektverzeichnis aus."
                )
                return
            with open(dirs_file, encoding="utf-8") as f:
                self._dir_tree = json.load(f)
            self._rebuild_visible_tree()
            if not self._dir_tree:
                self.error_message = "Index ist leer."
        except Exception as e:
            self.error_message = f"Fehler beim Laden des Index: {str(e)}"
        finally:
            self.is_loading = False

    async def load_selected_files(self):
        if not self.selected_data_folder:
            return
        self.is_loading = True
        self.error_message = ""
        self.xml_files_data = []
        yield
        try:
            src = self._get_source(self.selected_data_folder)
            if src is None:
                self.error_message = "Datenquelle nicht gefunden."
                return
            folder = Path(src["path"])
            selected = set(self._selected_paths)
            # Ensure all selected dirs have their files loaded
            for item in self._dir_tree:
                if item["path"] in selected and item["path"] not in self._file_cache:
                    self._load_dir_files(item["path"])
            files_data: list[dict] = []
            for files in self._file_cache.values():
                for f in files:
                    if f["path"] not in selected:
                        continue
                    if not f["path"].lower().endswith(".xml"):
                        continue
                    rel = Path(f["path"])
                    subdir = str(rel.parent) if str(rel.parent) != "." else "."
                    files_data.append({
                        "subdir": subdir,
                        "filename": f["name"],
                        "size_kb": f.get("size_kb", 0.0),
                    })
            self.directory_path = str(folder)
            self.xml_files_data = files_data
            if not files_data:
                self.error_message = "Keine XML-Dateien in der Auswahl gefunden."
        except Exception as e:
            self.error_message = f"Fehler: {str(e)}"
        finally:
            self.is_loading = False

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
