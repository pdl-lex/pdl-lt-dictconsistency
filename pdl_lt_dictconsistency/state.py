import reflex as rx
from pathlib import Path
import pandas as pd

# Security-Limits
MAX_ZIP_EXTRACT_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB pro Datei


class FileState(rx.State):
    directory_path: str = ""
    upload_mode: str = ""
    session_dir: str = ""
    xml_files_data: list[dict] = []
    error_message: str = ""
    is_loading: bool = False

    @rx.var
    def file_count(self) -> int:
        return len(self.xml_files_data)

    @rx.var
    def has_files(self) -> bool:
        return len(self.xml_files_data) > 0

    @rx.var
    def xml_files_df(self) -> pd.DataFrame:
        """Computed var: DataFrame für rx.data_table"""
        if not self.xml_files_data:
            return pd.DataFrame()

        df = pd.DataFrame(self.xml_files_data)

        # set nicer headers
        df = df.rename(columns={
            "subdir": "Unterverzeichnis",
            "filename": "Dateiname",
            "size_kb": "Größe (KB)",
        })

        return df

    def set_directory_path(self, value: str):
        self.directory_path = value

    def set_upload_mode(self, value: str):
        self.upload_mode = value

    @rx.event
    def handle_key_down(self, key: str):
        if key == "Enter":
            return FileState.scan_xml_files

    def _reset_validation_results(self):
        """Setzt alle Validierungsergebnisse zurück (wird von Child-States aufgerufen)"""
        # Diese Methode kann von ValidatorState überschrieben werden
        pass

    def _is_valid_xml(self, file_path: Path) -> bool:
        """Prüft ob Datei wirklich XML ist (Magic Bytes)"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(100)
                return header.lstrip().startswith(b'<?xml') or header.lstrip().startswith(b'<')
        except Exception as e:
            print(f"Fehler {e} in: {file_path}")
            return False

    def _create_session_dir(self):
        """Erstellt Session-Verzeichnis falls nicht vorhanden"""
        import tempfile

        if not self.session_dir:
            session_id = self.router.session.client_token
            self.session_dir = str(Path(tempfile.gettempdir()) / f"reflex_upload_{session_id}")

        session_path = Path(self.session_dir)
        session_path.mkdir(parents=True, exist_ok=True)
        return session_path

    def _extract_zip(self, zip_path: Path, extract_to: Path):
        """Sicher: Entpackt ZIP mit Größen-Check und Path-Traversal-Schutz"""
        import zipfile

        xml_count = 0
        total_size = 0

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    # SECURITY: Path Traversal verhindern (Zip Slip)
                    if '..' in member or member.startswith('/') or member.startswith('\\'):
                        print(f"SECURITY: Gefährlicher Pfad übersprungen: {member}")
                        continue

                    # SECURITY: Größen-Check (Zip Bomb)
                    member_info = zip_ref.getinfo(member)
                    total_size += member_info.file_size
                    if total_size > MAX_ZIP_EXTRACT_SIZE:
                        raise ValueError(f"ZIP-Archiv zu groß (>{MAX_ZIP_EXTRACT_SIZE / 1024 / 1024:.0f}MB)")

                    # Nur XML-Dateien extrahieren
                    if member.lower().endswith('.xml'):
                        # Sicherer Extract-Pfad
                        target_path = extract_to / Path(member).name  # Nur Dateiname, kein Pfad

                        # Extrahieren
                        with zip_ref.open(member) as source, open(target_path, 'wb') as target:
                            target.write(source.read())

                        # SECURITY: Prüfen ob wirklich XML
                        if self._is_valid_xml(target_path):
                            xml_count += 1
                        else:
                            print(f"SECURITY: Fake-XML entfernt: {member}")
                            target_path.unlink()

        except zipfile.BadZipFile:
            raise ValueError("Ungültige oder beschädigte ZIP-Datei")

        return xml_count

    async def handle_upload(self, files: list[rx.UploadFile]):
        """Sicher: Verarbeitet hochgeladene Dateien mit Security-Checks"""
        print(f"handle_upload aufgerufen mit {len(files)} Dateien")

        self.is_loading = True
        self.error_message = ""
        self.xml_files_data = []
        self._reset_validation_results()
        yield

        try:
            # Session-Verzeichnis erstellen
            session_path = self._create_session_dir()
            print(f"Session-Pfad: {session_path}")

            # Session-Verzeichnis leeren (alte Uploads löschen)
            import shutil
            for item in session_path.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

            total_xml_files = 0

            for file in files:
                print(f"Verarbeite: {file.filename}")

                # SECURITY: Dateiname sanitizen (keine Pfad-Zeichen)
                safe_filename = Path(file.filename).name
                if not safe_filename:
                    print("SECURITY: Ungültiger Dateiname übersprungen")
                    continue

                file_path = session_path / safe_filename

                # Datei speichern
                content = await file.read()

                # SECURITY: Größen-Check
                if len(content) > MAX_FILE_SIZE:
                    self.error_message = f"Datei {safe_filename} zu groß (max {MAX_FILE_SIZE / 1024 / 1024:.0f}MB)"
                    continue

                with open(file_path, "wb") as f:
                    f.write(content)

                print(f"Gespeichert: {file_path}")

                # ZIP entpacken oder XML direkt verarbeiten
                if file.filename.lower().endswith('.zip'):
                    try:
                        xml_count = self._extract_zip(file_path, session_path)
                        total_xml_files += xml_count
                        file_path.unlink()  # ZIP nach Entpacken löschen
                    except ValueError as e:
                        self.error_message = str(e)
                        file_path.unlink()

                elif file.filename.lower().endswith('.xml'):
                    # SECURITY: Prüfen ob wirklich XML
                    if self._is_valid_xml(file_path):
                        total_xml_files += 1
                    else:
                        print(f"SECURITY: Fake-XML entfernt: {file.filename}")
                        file_path.unlink()
                        self.error_message = f"{file.filename} ist keine gültige XML-Datei"

            # Session-Verzeichnis scannen
            self.directory_path = str(session_path)

            # XML-Dateien direkt scannen
            files_data = []
            for file_path in session_path.rglob("*.xml"):
                try:
                    # SECURITY: Nochmal validieren
                    if not self._is_valid_xml(file_path):
                        file_path.unlink()
                        continue

                    size_bytes = file_path.stat().st_size
                    size_kb = round(size_bytes / 1024, 2)

                    files_data.append({
                        "subdir": ".",
                        "filename": file_path.name,
                        "size_kb": size_kb,
                    })
                except Exception:
                    continue

            self.xml_files_data = files_data
            print(f"Gefunden: {len(files_data)} XML-Dateien")

        except Exception as e:
            print(f"FEHLER: {e}")
            self.error_message = f"Fehler beim Upload: {str(e)}"
        finally:
            self.is_loading = False


    async def scan_xml_files(self):
        """Scannt Verzeichnis rekursiv nach XML-Dateien - mit sicherem Parser"""
        self.is_loading = True
        self.error_message = ""
        self.xml_files_data = []
        self._reset_validation_results()

        yield

        if not self.directory_path:
            self.error_message = "Bitte geben Sie einen Verzeichnispfad ein."
            self.is_loading = False
            return

        try:
            path = Path(self.directory_path).expanduser()

            if not path.exists():
                self.error_message = "Verzeichnis existiert nicht."
                self.is_loading = False
                return

            if not path.is_dir():
                self.error_message = "Pfad ist kein Verzeichnis."
                self.is_loading = False
                return

            # XML-Dateien rekursiv sammeln mit Metadaten
            files_data = []
            for file_path in path.rglob("*.xml"):
                try:
                    # SECURITY: Validiere XML
                    if not self._is_valid_xml(file_path):
                        continue

                    relative_path = file_path.relative_to(path)
                    subdir = str(relative_path.parent) if relative_path.parent != Path('.') else "."
                    size_bytes = file_path.stat().st_size
                    size_kb = round(size_bytes / 1024, 2)

                    files_data.append({
                        "subdir": subdir,
                        "filename": file_path.name,
                        "size_kb": size_kb,
                    })
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
