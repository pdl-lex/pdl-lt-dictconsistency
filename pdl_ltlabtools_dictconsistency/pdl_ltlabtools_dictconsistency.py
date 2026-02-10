import reflex as rx
from pathlib import Path
import pandas as pd
from lxml import etree
from lt_reflex_ag_grid_wrapper import ag_grid   

# Security-Limits
MAX_ZIP_EXTRACT_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB pro Datei

# ============ States ============

class FileState(rx.State):
    directory_path: str = ""
    upload_mode: str = ""
    session_dir: str = ""
    xml_files_data: list[dict] = []
    error_message: str = ""
    is_loading: bool = False

    # grid_api_path = ag_grid.api("path_input_grid")
    # grid_api_upload = ag_grid.api("path_upload_grid")

    # def export_csv(self, grid):
    #     # Accept either the API object itself or the name of an attribute on this state
    #     api = getattr(self, grid) if isinstance(grid, str) else grid
    #     print(f"Exportiere CSV mit API: {api}")
    #     return api.exportDataAsCsv()

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


class ValidatorState(FileState):
    """State für XML-Validierung - erbt von FileState um Zugriff auf xml_files_data zu haben"""
    wellformed_errors: list[dict] = []
    schema_errors: list[dict] = []
    is_validating: bool = False
    wellformed_validation_complete: bool = False
    schema_validation_complete: bool = False
    files_checked: int = 0
    files_with_wellformed_errors: int = 0
    files_with_schema_errors: int = 0

    # Validierungstyp
    validation_type: str = "Wohlgeformtheit (Well-formed XML)"

    # Schema-Fehler
    schema_error: str = ""

    @rx.var
    def wellformed_error_count(self) -> int:
        return len(self.wellformed_errors)

    @rx.var
    def schema_error_count(self) -> int:
        return len(self.schema_errors)

    @rx.var
    def has_wellformed_errors(self) -> bool:
        return len(self.wellformed_errors) > 0

    @rx.var
    def has_schema_errors(self) -> bool:
        return len(self.schema_errors) > 0

    @rx.var
    def can_validate(self) -> bool:
        """Prüft ob Dateien zum Validieren vorhanden sind"""
        return len(self.xml_files_data) > 0

    @rx.var
    def can_start_validation(self) -> bool:
        """Prüft ob Validierung gestartet werden kann"""
        return self.can_validate

    @rx.var
    def validation_type_label(self) -> str:
        """Gibt den Namen des Validierungstyps zurück"""
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            return "Wohlgeformtheit"
        return "TEI-Lex 0 Schema"

    @rx.var
    def wellformed_errors_df(self) -> pd.DataFrame:
        """DataFrame für Wohlgeformtheits-Fehler"""
        if not self.wellformed_errors:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.wellformed_errors)
        df = df.rename(columns={
            "subdir": "Unterverzeichnis",
            "filename": "Dateiname",
            "line": "Zeile",
            "column": "Spalte",
            "error": "Fehler",
        })
        return df

    @rx.var
    def schema_errors_df(self) -> pd.DataFrame:
        """DataFrame für Schema-Fehler"""
        if not self.schema_errors:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.schema_errors)
        df = df.rename(columns={
            "subdir": "Unterverzeichnis",
            "filename": "Dateiname",
            "line": "Zeile",
            "column": "Spalte",
            "error": "Fehler",
        })
        return df

    def set_validation_type(self, value: str):
        self.validation_type = value
        self.schema_error = ""

    def _get_schema_path(self) -> Path:
        """Gibt den Pfad zur Schema-Datei im App-Verzeichnis zurück"""
        return Path(__file__).parent / "teilex0.rng"

    def _load_rng_schema(self, schema_path: Path):
        """Lädt ein RelaxNG Schema"""
        with open(schema_path, "rb") as f:
            schema_doc = etree.parse(f)
        return etree.RelaxNG(schema_doc)
    
    def _reset_validation_results(self):
        """Setzt Validierungsergebnisse zurück wenn neue Daten geladen werden"""
        self.wellformed_errors = []
        self.schema_errors = []
        self.wellformed_validation_complete = False
        self.schema_validation_complete = False
        self.files_checked = 0
        self.files_with_wellformed_errors = 0
        self.files_with_schema_errors = 0
        self.schema_error = ""

    def reset_validation(self):
        """Setzt alle Validierungsergebnisse zurück"""
        self._reset_validation_results()

    async def validate_all_xml(self):
        """Validiert alle XML-Dateien"""
        self.is_validating = True
        
        # Nur die AKTUELL gewählte Validierung zurücksetzen
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            self.wellformed_validation_complete = False
            self.wellformed_errors = []
            self.files_with_wellformed_errors = 0
        else:
            self.schema_validation_complete = False
            self.schema_errors = []
            self.files_with_schema_errors = 0
        
        self.files_checked = 0
        self.schema_error = ""

        yield

        if not self.directory_path or not self.xml_files_data:
            self.is_validating = False
            return

        base_path = Path(self.directory_path).expanduser()
        wellformed_errors = []
        schema_errors = []

        # Schema laden falls TEI-Lex 0 Validierung
        rng_schema = None
        if self.validation_type == "TEI-Lex 0 Schema (RelaxNG)":
            try:
                schema_file = self._get_schema_path()
                if not schema_file.exists():
                    self.schema_error = f"Schema-Datei nicht gefunden: {schema_file}. Bitte 'teilex0.rng' im App-Verzeichnis ablegen."
                    self.is_validating = False
                    return
                rng_schema = self._load_rng_schema(schema_file)
            except Exception as e:
                self.schema_error = f"Fehler beim Laden des Schemas: {str(e)}"
                self.is_validating = False
                return

        for file_info in self.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            self.files_checked += 1
            has_wellformed_error = False
            has_schema_error = False

            try:
                # Versuche XML zu parsen (Wohlgeformtheit)
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                # Schema-Validierung falls aktiviert
                if rng_schema is not None:
                    if not rng_schema.validate(doc):
                        has_schema_error = True
                        for error in rng_schema.error_log:
                            schema_errors.append({
                                "subdir": subdir,
                                "filename": filename,
                                "line": error.line if error.line else 0,
                                "column": error.column if error.column else 0,
                                "error": error.message,
                            })

            except etree.XMLSyntaxError as e:
                has_wellformed_error = True
                wellformed_errors.append({
                    "subdir": subdir,
                    "filename": filename,
                    "line": e.lineno if e.lineno else 0,
                    "column": e.offset if e.offset else 0,
                    "error": str(e.msg) if e.msg else str(e),
                })
            except Exception as e:
                has_wellformed_error = True
                wellformed_errors.append({
                    "subdir": subdir,
                    "filename": filename,
                    "line": 0,
                    "column": 0,
                    "error": str(e),
                })

            if has_wellformed_error:
                self.files_with_wellformed_errors += 1
            if has_schema_error:
                self.files_with_schema_errors += 1

            # Alle 100 Dateien UI aktualisieren
            if self.files_checked % 100 == 0:
                if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
                    self.wellformed_errors = wellformed_errors.copy()
                else:
                    self.schema_errors = schema_errors.copy()
                yield

        # Ergebnisse speichern
        if self.validation_type == "Wohlgeformtheit (Well-formed XML)":
            self.wellformed_errors = wellformed_errors
            self.wellformed_validation_complete = True
        else:
            self.schema_errors = schema_errors
            self.schema_validation_complete = True
        
        self.is_validating = False

    def download_wellformed_errors_csv(self):
        """Erstellt CSV-Download der Wohlgeformtheits-Fehler"""
        if not self.wellformed_errors:
            return

        df = pd.DataFrame(self.wellformed_errors)
        csv_content = df.to_csv(index=False, sep=";")

        return rx.download(
            data=csv_content,
            filename="xml_wellformed_errors.csv",
        )

    def download_schema_errors_csv(self):
        """Erstellt CSV-Download der Schema-Fehler"""
        if not self.schema_errors:
            return

        df = pd.DataFrame(self.schema_errors)
        csv_content = df.to_csv(index=False, sep=";")

        return rx.download(
            data=csv_content,
            filename="xml_schema_errors.csv",
        )

class PathfinderState(FileState):
    """State für Pathfinder - erbt von FileState um Zugriff auf xml_files_data zu haben"""
    user_input: str = ""
    path_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    debug_output: str = ""

    # Dateivorschau
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    @rx.var
    def has_results(self) -> bool:
        return len(self.path_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.path_results)

    @rx.var
    def path_results_df(self) -> pd.DataFrame:
        if not self.path_results:
            return pd.DataFrame()
        return pd.DataFrame(self.path_results)

    @rx.var
    def preview_content_with_line_numbers(self) -> str:
        """Formatiert den Vorschau-Inhalt mit Zeilennummern und hebt die Zielzeile hervor"""
        if not self.preview_content:
            return ""

        lines = self.preview_content.split("\n")
        max_line_num = len(lines)
        num_width = len(str(max_line_num))

        html_lines = []
        for i, line in enumerate(lines, start=1):
            # HTML-Escaping für den Zeileninhalt
            escaped_line = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

            # Zielzeile hervorheben
            if i == self.preview_line:
                html_lines.append(
                    f'<div style="background-color: var(--yellow-3); border-left: 3px solid var(--yellow-9);">'
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f'<span>{escaped_line}</span>'
                    f'</div>'
                )
            else:
                html_lines.append(
                    f'<div>'
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f'<span>{escaped_line}</span>'
                    f'</div>'
                )

        return "\n".join(html_lines)

    @rx.event
    def handle_key_down(self, key: str):
        if key == "Enter":
            return PathfinderState.search_path

    @rx.event
    def set_text(self, value: str):
        self.user_input = value

    def _reset_validation_results(self):
        """Setzt Suchergebnisse zurück wenn neue Daten geladen werden"""
        self.path_results = []
        self.files_checked = 0
        self.debug_output = ""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0
        # user_input bleibt erhalten

    def open_file_preview(self, row_data: dict):
        """Öffnet Dateivorschau-Dialog für die ausgewählte Zeile"""
        try:
            subdir = row_data.get("subdir", ".")
            filename = row_data.get("filename", "")
            line = row_data.get("line", 0)

            if not filename:
                return

            # Vollständigen Dateipfad erstellen
            base_path = Path(self.directory_path).expanduser()
            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            # Datei lesen
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # State aktualisieren
            self.preview_filename = filename
            self.preview_content = content
            self.preview_line = line
            self.show_preview_dialog = True

        except Exception as e:
            print(f"Fehler beim Öffnen der Vorschau: {e}")
            self.error_message = f"Fehler beim Öffnen der Datei: {str(e)}"

    def close_preview(self):
        """Schließt den Vorschau-Dialog"""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0

    def open_selected_file(self):
        """Öffnet die ausgewählte Datei in der Vorschau"""
        if self.selected_rows and len(self.selected_rows) > 0:
            self.open_file_preview(self.selected_rows[0])

    def set_selected_rows(self, rows):
        """Speichert die ausgewählten Zeilen"""
        self.selected_rows = rows if rows else []

    def _parse_user_input(self):
        if "/" not in self.user_input:
            result = {"type": "simple", "elements": [self.user_input.lower().strip()]}

        elif "*" not in self.user_input:
            result = {"type": "path", "elements": self.user_input.lower().strip().split("/")}

        else:
            result = {"type": "wildcard", "elements": self.user_input.lower().strip().split("/")}

        self.debug_output = str(result)
        return result

    def _build_xpath(self, search_params):
        if search_params["type"] == "simple":
            tag = search_params["elements"][0]
            return f"//*[local-name()='{tag}']"

        elif search_params["type"] == "path":
            path_parts = []
            for elem in search_params["elements"]:
                path_parts.append(f"*[local-name()='{elem}']")  # ← Kein Leerzeichen!
            xpath = "//" + "/".join(path_parts)  # ← Auch // am Anfang!
            return xpath

        elif search_params["type"] == "wildcard":
            path_parts = []
            for elem in search_params["elements"]:
                if elem == "*":
                    path_parts.append("*")
                else:
                    path_parts.append(f"*[local-name()='{elem}']")  # ← Kein Leerzeichen!
            xpath = "//" + "//".join(path_parts)  # ← // zwischen Wildcard-Teilen!
            return xpath

        return None

    async def search_path(self):
        self.is_searching = True
        self.debug_output = ""
        self.path_results= []
        self.files_checked = 0
        self.error_message = ""
        yield

        search_params = self._parse_user_input()

        if search_params is None:
            self.is_searching = False
            return

        base_path = Path(self.directory_path).expanduser()
        results = []
        # tag_name = search_params["elements"][0]

        for file_info in self.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir  == "" ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            self.files_checked += 1

            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                xpath = self._build_xpath(search_params)
                elements = doc.xpath(xpath)

                for elem in elements:
                    path_parts = []
                    current = elem

                    # generate the full path, walking up from the current element to the top (via .getparent)
                    # etree.QName(current).localname: get the localname, i.e. the tag
                    # insert(0, ...):  reverse insertion order, so the path starts at the top
                    while current is not None:
                        path_parts.insert(0, etree.QName(current).localname)
                        current = current.getparent()
                    full_path = "/".join(path_parts)

                    text_content = (elem.text or "").strip()
                    if len(text_content) > 100:
                        text_content = text_content[:100] + "..."

                    results.append({
                        "subdir": subdir,
                        "filename": filename,
                        "line": elem.sourceline or 0,
                        # "element": tag_name,
                        "full_path": full_path,
                        "text_content": text_content,
                    })



            except Exception as e:
                print(e)
                continue

            if self.files_checked % 10 == 0:
                self.path_results = results
                yield  # update UI

        self.path_results = results
        self.debug_output = f"{len(results)} Vorkommen gefunden"
        self.is_searching = False


class TagContentState(FileState):
    """State für Tag-Inhalts-Suche - erbt von FileState um Zugriff auf xml_files_data zu haben"""
    search_mode: str = "Einzelner Tag"
    single_tag_input: str = ""
    search_text: str = ""
    include_whitespace: bool = True

    # Alle gefundenen Tags aus den Dokumenten
    all_tags: list[str] = []
    # Tags die durchsucht werden sollen
    included_tags: list[str] = []
    # Tags die ausgeschlossen wurden
    excluded_tags: list[str] = []

    content_results: list[dict] = []
    files_checked: int = 0
    is_searching: bool = False
    is_loading_tags: bool = False
    tag_not_found: bool = False  # Für "Einzelner Tag" Modus: Tag existiert gar nicht

    # Dateivorschau
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    @rx.var
    def has_results(self) -> bool:
        return len(self.content_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.content_results)

    @rx.var
    def content_results_df(self) -> pd.DataFrame:
        if not self.content_results:
            return pd.DataFrame()
        return pd.DataFrame(self.content_results)

    @rx.var
    def preview_content_with_line_numbers(self) -> str:
        """Formatiert den Vorschau-Inhalt mit Zeilennummern und hebt die Zielzeile hervor"""
        if not self.preview_content:
            return ""

        lines = self.preview_content.split("\n")
        max_line_num = len(lines)
        num_width = len(str(max_line_num))

        html_lines = []
        for i, line in enumerate(lines, start=1):
            # HTML-Escaping für den Zeileninhalt
            escaped_line = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

            # Zielzeile hervorheben
            if i == self.preview_line:
                html_lines.append(
                    f'<div style="background-color: var(--yellow-3); border-left: 3px solid var(--yellow-9);">'
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f'<span>{escaped_line}</span>'
                    f'</div>'
                )
            else:
                html_lines.append(
                    f'<div>'
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f'<span>{escaped_line}</span>'
                    f'</div>'
                )

        return "\n".join(html_lines)

    def set_search_mode(self, value: str):
        self.search_mode = value

    def set_single_tag_input(self, value: str):
        self.single_tag_input = value

    def set_search_text(self, value: str):
        self.search_text = value

    def set_include_whitespace(self, value: bool):
        self.include_whitespace = value

    def insert_space(self):
        """Fügt ein Leerzeichen zum Suchtext hinzu"""
        self.search_text += " "

    def insert_linebreak(self):
        """Fügt einen Zeilenumbruch zum Suchtext hinzu"""
        self.search_text += "\n"

    def _reset_validation_results(self):
        """Setzt Ergebnisse und abgeleitete Daten zurück wenn neue Daten geladen werden"""
        # Nur Ergebnisse und abgeleitete Daten zurücksetzen, NICHT Benutzereingaben
        self.all_tags = []
        self.included_tags = []
        self.excluded_tags = []
        self.content_results = []
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0
        # search_text, single_tag_input, search_mode, include_whitespace bleiben erhalten

    def open_file_preview(self, row_data: dict):
        """Öffnet Dateivorschau-Dialog für die ausgewählte Zeile"""
        try:
            subdir = row_data.get("subdir", ".")
            filename = row_data.get("filename", "")
            line = row_data.get("line", 0)

            if not filename:
                return

            # Vollständigen Dateipfad erstellen
            base_path = Path(self.directory_path).expanduser()
            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            # Datei lesen
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # State aktualisieren
            self.preview_filename = filename
            self.preview_content = content
            self.preview_line = line
            self.show_preview_dialog = True

        except Exception as e:
            print(f"Fehler beim Öffnen der Vorschau: {e}")
            self.error_message = f"Fehler beim Öffnen der Datei: {str(e)}"

    def close_preview(self):
        """Schließt den Vorschau-Dialog"""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0

    def open_selected_file(self):
        """Öffnet die ausgewählte Datei in der Vorschau"""
        if self.selected_rows and len(self.selected_rows) > 0:
            self.open_file_preview(self.selected_rows[0])

    def set_selected_rows(self, rows):
        """Speichert die ausgewählten Zeilen"""
        self.selected_rows = rows if rows else []

    def exclude_tag(self, tag: str):
        """Verschiebt Tag von included zu excluded"""
        if tag in self.included_tags:
            self.included_tags.remove(tag)
            self.excluded_tags.append(tag)
            self.excluded_tags.sort()

    def include_tag(self, tag: str):
        """Verschiebt Tag von excluded zu included"""
        if tag in self.excluded_tags:
            self.excluded_tags.remove(tag)
            self.included_tags.append(tag)
            self.included_tags.sort()

    async def load_all_tags(self):
        """Lädt alle einzigartigen Tags aus allen XML-Dateien"""
        self.is_loading_tags = True
        self.all_tags = []
        self.included_tags = []
        self.excluded_tags = []
        self.error_message = ""
        yield

        if not self.directory_path or not self.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_loading_tags = False
            return

        base_path = Path(self.directory_path).expanduser()
        tags_set = set()

        for file_info in self.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                # Alle Tags im Dokument sammeln
                for elem in doc.iter():
                    # Nur echte Elemente verarbeiten (keine Kommentare, PIs, etc.)
                    if isinstance(elem.tag, str):
                        try:
                            tag_name = etree.QName(elem).localname
                            tags_set.add(tag_name)
                        except:
                            continue

            except Exception as e:
                print(f"Fehler beim Laden von Tags aus {filename}: {e}")
                continue

        # Sortierte Liste erstellen
        self.all_tags = sorted(list(tags_set))
        self.included_tags = self.all_tags.copy()
        self.is_loading_tags = False

    def _get_element_text(self, elem, include_whitespace: bool) -> str:
        """Extrahiert Text aus Element (ohne Child-Element-Text)"""
        text = elem.text or ""

        if not include_whitespace:
            # Leerzeichen und Zeilenumbrüche entfernen
            text = text.strip()
            text = " ".join(text.split())

        return text

    def _format_text_with_visible_whitespace(self, text: str) -> str:
        """Macht Leerzeichen und Zeilenumbrüche sichtbar"""
        # Ersetze Leerzeichen durch ·
        text = text.replace(" ", "·")
        # Ersetze Zeilenumbrüche durch ↵
        text = text.replace("\n", "↵\n")
        text = text.replace("\r", "↵")
        return text

    async def search_tag_content(self):
        """Sucht nach Tag-Inhalten basierend auf den Suchkriterien"""
        self.is_searching = True
        self.content_results = []
        self.files_checked = 0
        self.error_message = ""
        self.tag_not_found = False
        yield

        if not self.directory_path or not self.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_searching = False
            return

        # Tags bestimmen
        is_single_tag_mode = False
        if self.search_mode == "Einzelner Tag":
            if not self.single_tag_input.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_searching = False
                return
            tags_to_search = [self.single_tag_input.strip()]
            is_single_tag_mode = True
        else:  # Mehrere Tags
            if not self.included_tags:
                self.error_message = "Keine Tags zum Durchsuchen ausgewählt."
                self.is_searching = False
                return
            tags_to_search = self.included_tags

        base_path = Path(self.directory_path).expanduser()
        results = []
        tag_found_in_documents = False  # Tracker für einzelnen Tag

        for file_info in self.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            self.files_checked += 1

            try:
                with open(file_path, "rb") as f:
                    doc = etree.parse(f)

                # Für jeden zu durchsuchenden Tag
                for tag_name in tags_to_search:
                    xpath = f"//*[local-name()='{tag_name}']"
                    elements = doc.xpath(xpath)

                    # Im Einzeltag-Modus: Prüfen ob Tag überhaupt existiert
                    if is_single_tag_mode and len(elements) > 0:
                        tag_found_in_documents = True

                    for elem in elements:
                        # Text des Elements (ohne Child-Element-Text)
                        elem_text = self._get_element_text(elem, self.include_whitespace)

                        # Ignoriere Formatierungs-Whitespace (Einrückung nach Zeilenumbrüchen)
                        # aber behalte echten Whitespace-Inhalt (ohne Newlines)
                        if self.include_whitespace and elem_text:
                            # Wenn Text mit Newline beginnt und nur Whitespace enthält → Formatierung
                            if elem_text.startswith("\n") and not elem_text.strip():
                                continue

                        # Prüfen ob Kriterien erfüllt sind
                        match = False

                        if self.search_text:  # Nicht .strip() verwenden!
                            # Suche nach bestimmtem Text
                            search_term = self.search_text

                            if not self.include_whitespace:
                                # Normalisiere Suchterm und Element-Text
                                search_term_normalized = " ".join(search_term.split())
                                if search_term_normalized and search_term_normalized in elem_text:
                                    match = True
                            else:
                                # Exakte Suche mit Whitespace
                                if search_term in elem_text:
                                    match = True
                        else:
                            # Suche nach nicht-leeren Tags
                            if elem_text:
                                match = True

                        if match:
                            # Text für Anzeige vorbereiten
                            display_text = elem_text
                            if len(display_text) > 200:
                                display_text = display_text[:200] + "..."

                            # Whitespace sichtbar machen
                            display_text = self._format_text_with_visible_whitespace(display_text)

                            results.append({
                                "subdir": subdir,
                                "filename": filename,
                                "line": elem.sourceline or 0,
                                "tag": tag_name,
                                "text": display_text,
                            })

            except Exception as e:
                print(f"Fehler beim Durchsuchen von {filename}: {e}")
                continue

            # UI alle 10 Dateien aktualisieren
            if self.files_checked % 10 == 0:
                self.content_results = results.copy()
                yield

        self.content_results = results

        # Im Einzeltag-Modus: Prüfen ob Tag gar nicht existiert
        if is_single_tag_mode and not tag_found_in_documents:
            self.tag_not_found = True

        self.is_searching = False


class UniquenessState(FileState):
    """State für Einmaligkeitsprüfungen - prüft ob Tags, Inhalte oder Attribute innerhalb von Dokumenten einmalig sind"""
    check_mode: str = "Tag"  # "Tag", "Tag-Inhalt", "Tag & Attribut", "Attribut"
    tag_name: str = ""
    tag_content: str = ""
    attribute_name: str = ""

    uniqueness_results: list[dict] = []
    files_checked: int = 0
    is_checking: bool = False

    # Dateivorschau
    show_preview_dialog: bool = False
    preview_filename: str = ""
    preview_content: str = ""
    preview_line: int = 0
    selected_rows: list[dict] = []

    @rx.var
    def has_results(self) -> bool:
        return len(self.uniqueness_results) > 0

    @rx.var
    def results_count(self) -> int:
        return len(self.uniqueness_results)

    @rx.var
    def preview_content_with_line_numbers(self) -> str:
        """Formatiert den Vorschau-Inhalt mit Zeilennummern und hebt die Zielzeile hervor"""
        if not self.preview_content:
            return ""

        lines = self.preview_content.split("\n")
        max_line_num = len(lines)
        num_width = len(str(max_line_num))

        html_lines = []
        for i, line in enumerate(lines, start=1):
            # HTML-Escaping für den Zeileninhalt
            escaped_line = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

            # Zielzeile hervorheben
            if i == self.preview_line:
                html_lines.append(
                    f'<div style="background-color: var(--yellow-3); border-left: 3px solid var(--yellow-9);">'
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f'<span>{escaped_line}</span>'
                    f'</div>'
                )
            else:
                html_lines.append(
                    f'<div>'
                    f'<span style="color: var(--gray-11); margin-right: 1em; user-select: none; display: inline-block; width: {num_width}ch; text-align: right;">{i}</span>'
                    f'<span>{escaped_line}</span>'
                    f'</div>'
                )

        return "\n".join(html_lines)

    def set_check_mode(self, value: str):
        self.check_mode = value

    def set_tag_name(self, value: str):
        self.tag_name = value

    def set_tag_content(self, value: str):
        self.tag_content = value

    def set_attribute_name(self, value: str):
        self.attribute_name = value

    def _reset_validation_results(self):
        """Setzt Ergebnisse zurück wenn neue Daten geladen werden"""
        self.uniqueness_results = []
        self.files_checked = 0
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0

    def open_file_preview(self, row_data: dict):
        """Öffnet Dateivorschau-Dialog für die ausgewählte Zeile"""
        try:
            subdir = row_data.get("subdir", ".")
            filename = row_data.get("filename", "")
            line = row_data.get("line", 0)

            if not filename:
                return

            # Vollständigen Dateipfad erstellen
            base_path = Path(self.directory_path).expanduser()
            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            # Datei lesen
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # State aktualisieren
            self.preview_filename = filename
            self.preview_content = content
            self.preview_line = line
            self.show_preview_dialog = True

        except Exception as e:
            print(f"Fehler beim Öffnen der Vorschau: {e}")
            self.error_message = f"Fehler beim Öffnen der Datei: {str(e)}"

    def close_preview(self):
        """Schließt den Vorschau-Dialog"""
        self.show_preview_dialog = False
        self.preview_filename = ""
        self.preview_content = ""
        self.preview_line = 0

    def open_selected_file(self):
        """Öffnet die ausgewählte Datei in der Vorschau"""
        if self.selected_rows and len(self.selected_rows) > 0:
            self.open_file_preview(self.selected_rows[0])

    def set_selected_rows(self, rows):
        """Speichert die ausgewählten Zeilen"""
        self.selected_rows = rows if rows else []

    def _get_attribute_value(self, elem, attr_name: str):
        """Holt Attributwert, unterstützt auch Namespace-Attribute wie xml:id"""

        # Durchsuche alle Attribute des Elements
        for attr_key, attr_value in elem.attrib.items():
            # Fall 1: Direkter Match (z.B. "type" == "type")
            if attr_key == attr_name:
                return attr_value

            # Fall 2: Namespace-Match (z.B. "{http://...}id" == "xml:id")
            if "}" in attr_key and ":" in attr_name:
                # Extrahiere Namespace und lokalen Namen aus dem Schlüssel
                namespace_uri = attr_key.split("}", 1)[0] + "}"  # z.B. "{http://www.w3.org/XML/1998/namespace}"
                local_name = attr_key.split("}", 1)[1]            # z.B. "id"

                # Extrahiere Präfix und lokalen Namen aus der Eingabe
                prefix, local_input = attr_name.split(":", 1)

                # Prüfe ob lokale Namen übereinstimmen
                if local_name == local_input:
                    # Prüfe bekannte Namespace-Präfixe
                    if prefix == "xml" and "XML/1998/namespace" in namespace_uri:
                        return attr_value

        return None

    async def check_uniqueness(self):
        """Führt Einmaligkeitsprüfung basierend auf dem gewählten Modus durch"""
        self.is_checking = True
        self.uniqueness_results = []
        self.files_checked = 0
        self.error_message = ""
        yield

        if not self.directory_path or not self.xml_files_data:
            self.error_message = "Keine XML-Dateien geladen."
            self.is_checking = False
            return

        # Validierung der Eingaben
        if self.check_mode == "Tag":
            if not self.tag_name.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_checking = False
                return
        elif self.check_mode == "Tag-Inhalt":
            if not self.tag_name.strip():
                self.error_message = "Bitte geben Sie einen Tag-Namen ein."
                self.is_checking = False
                return
        elif self.check_mode == "Tag & Attribut":
            if not self.tag_name.strip() or not self.attribute_name.strip():
                self.error_message = "Bitte geben Sie Tag-Namen und Attribut-Namen ein."
                self.is_checking = False
                return
        elif self.check_mode == "Attribut":
            if not self.attribute_name.strip():
                self.error_message = "Bitte geben Sie einen Attribut-Namen ein."
                self.is_checking = False
                return

        base_path = Path(self.directory_path).expanduser()
        results = []

        for file_info in self.xml_files_data:
            subdir = file_info["subdir"]
            filename = file_info["filename"]

            if subdir == ".":
                file_path = base_path / filename
            else:
                file_path = base_path / subdir / filename

            self.files_checked += 1

            try:
                # Parser ohne DTD/ID-Validierung, damit auch Dokumente mit ID-Duplikaten geparst werden können
                parser = etree.XMLParser(
                    dtd_validation=False,
                    load_dtd=False,
                    no_network=True,
                    resolve_entities=False
                )
                with open(file_path, "rb") as f:
                    doc = etree.parse(f, parser)

                # Je nach Modus unterschiedliche Prüfung
                if self.check_mode == "Tag":
                    # Prüfe ob Tag mehrfach vorkommt
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    if len(elements) > 1:
                        # Tag kommt mehrfach vor - Fehler!
                        first_line = elements[0].sourceline or 0
                        results.append({
                            "subdir": subdir,
                            "filename": filename,
                            "line": first_line,
                            "error_type": f"Tag '{self.tag_name.strip()}' kommt {len(elements)}x vor",
                            "details": f"Erwartet: 1x, Gefunden: {len(elements)}x",
                        })

                elif self.check_mode == "Tag-Inhalt":
                    # Prüfe ob Tag-Inhalte einmalig sind
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    # Sammle alle Inhalte
                    content_map = {}  # content -> [line_numbers]
                    for elem in elements:
                        content = (elem.text or "").strip()
                        if content:
                            line = elem.sourceline or 0
                            if content not in content_map:
                                content_map[content] = []
                            content_map[content].append(line)

                    # Prüfe auf Duplikate
                    for content, lines in content_map.items():
                        if len(lines) > 1:
                            # Inhalt kommt mehrfach vor
                            preview_text = content if len(content) <= 50 else content[:50] + "..."
                            results.append({
                                "subdir": subdir,
                                "filename": filename,
                                "line": lines[0],
                                "error_type": f"Inhalt '{preview_text}' in Tag '{self.tag_name.strip()}' kommt {len(lines)}x vor",
                                "details": f"Zeilen: {', '.join(map(str, lines))}",
                            })

                elif self.check_mode == "Tag & Attribut":
                    # Prüfe ob Attributwerte im Tag einmalig sind
                    xpath = f"//*[local-name()='{self.tag_name.strip()}']"
                    elements = doc.xpath(xpath)

                    # Sammle alle Attributwerte
                    attr_map = {}  # attr_value -> [line_numbers]
                    for elem in elements:
                        attr_value = self._get_attribute_value(elem, self.attribute_name.strip())
                        if attr_value:
                            line = elem.sourceline or 0
                            if attr_value not in attr_map:
                                attr_map[attr_value] = []
                            attr_map[attr_value].append(line)

                    # Prüfe auf Duplikate
                    for attr_value, lines in attr_map.items():
                        if len(lines) > 1:
                            results.append({
                                "subdir": subdir,
                                "filename": filename,
                                "line": lines[0],
                                "error_type": f"Attribut '{self.attribute_name.strip()}' mit Wert '{attr_value}' in Tag '{self.tag_name.strip()}' kommt {len(lines)}x vor",
                                "details": f"Zeilen: {', '.join(map(str, lines))}",
                            })

                elif self.check_mode == "Attribut":
                    # Prüfe ob Attributwerte über alle Tags einmalig sind
                    # Hole alle Elemente (wegen Namespace-Attributen kann XPath nicht verwendet werden)
                    all_elements = doc.xpath("//*")

                    # Sammle alle Attributwerte
                    attr_map = {}  # attr_value -> [(tag_name, line_number)]
                    for elem in all_elements:
                        attr_value = self._get_attribute_value(elem, self.attribute_name.strip())
                        if attr_value:
                            line = elem.sourceline or 0
                            tag_name = etree.QName(elem).localname
                            if attr_value not in attr_map:
                                attr_map[attr_value] = []
                            attr_map[attr_value].append((tag_name, line))

                    # Prüfe auf Duplikate
                    for attr_value, occurrences in attr_map.items():
                        if len(occurrences) > 1:
                            tag_list = ", ".join([f"{tag}:{line}" for tag, line in occurrences])
                            results.append({
                                "subdir": subdir,
                                "filename": filename,
                                "line": occurrences[0][1],
                                "error_type": f"Attribut '{self.attribute_name.strip()}' mit Wert '{attr_value}' kommt {len(occurrences)}x vor",
                                "details": f"In: {tag_list}",
                            })

            except Exception as e:
                print(f"Fehler in {filename}: {e}")
                continue

            # UI alle 10 Dateien aktualisieren
            if self.files_checked % 10 == 0:
                self.uniqueness_results = results.copy()
                yield

        self.uniqueness_results = results
        self.is_checking = False


# === Komponenten ===

def pathfinder_input() -> rx.Component:

    column_defs = [
        ag_grid.column_def(
            field="filename",
            header_name="Dateiname",
            # width=300,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="subdir",
            header_name="Unterverzeichnis",
            # width=150,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="line",
            header_name="Zeile",
            # width=100,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="full_path",
            header_name="XPath",
            # width=100,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="text_content",
            header_name="Inhalt",
            # width=100,
            sortable=True,
            filter=True,
        ),
    ]

    return rx.vstack(
        
        
        rx.text("Bitte geben Sie einen einzelnen XML-Tag oder einen Pfad (ohne Anführungszeichen) ein, nach dem gesucht werden soll."),
        rx.text(
            "Beispiel: 'bedeutung' sucht nach allen Vorkommen des Tags 'bedeutung'",
            size="1",
            color="var(--grey-11)",
            font_family="monospace",
        ),

        rx.text(
           "Beispiel: 'sense/sense' sucht nach allen Stellen, in denen ein sense-Tag innerhalb eines sense-Tags auftaucht (ohne weitere Verschachtelung)",
            size="1",
            color="var(--grey-11)",
            font_family="monospace",
        ),
        
        rx.text(
           "Beispiel: 'sense/*/bibl' sucht nach allen Stellen, in denen ein bibl-Tag innerhalb eines sense-Tags auftaucht. Das * bedeutet, dass noch andere Ebenen dazwischen vorkommen können. Es wird also auch sense/cit/bibl gefunden.",
            size="1",
            color="var(--grey-11)",
            font_family="monospace",
        ),

        rx.hstack(
            rx.input(
                value=PathfinderState.user_input,
                placeholder="Tag oder Pfad eingeben...",
                on_change=PathfinderState.set_text,
                on_key_down=PathfinderState.handle_key_down,
                disabled=PathfinderState.is_searching,
                width="100%",
            ),
            rx.button(
                rx.cond(
                    PathfinderState.is_searching,
                    rx.hstack(
                        rx.spinner(size="3"),
                        rx.text("Suchen..."),
                        spacing="2",
                    ),
                    rx.text("Suchen"),
                ),
                on_click=PathfinderState.search_path,
                variant="solid",
                disabled=PathfinderState.is_searching,
                color_scheme="jade",
            ),
            width="100%",
        ),
        
        rx.cond(
            PathfinderState.is_searching,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    "Durchsuche XML-Dateien nach angegebenem Pfad.",
                    color_scheme="jade",
                ),
                spacing="2",
                align="center",
            ),
        ),
        
        rx.cond(
            PathfinderState.error_message != "",
            rx.callout(
                PathfinderState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),
        
        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),

        rx.cond(
            PathfinderState.has_results,
            rx.vstack(
                rx.text(
                    PathfinderState.results_count, " Pfade gefunden",
                    color="var(--jade-11)",
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                        id="path_results_grid",
                        row_data=PathfinderState.path_results,
                        column_defs=column_defs,
                        default_col_def={"flex": 1, "minWidth": 50},
                        pagination=True,
                        pagination_page_size=25,
                        pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                        resizable=True,
                        csv_export_params={"fileName": "xml_files.csv", "allColumns": True, "columnSeparator": ";", "exportMode": "csv"},
                        dom_layout="autoHeight", #options: "autoHeight", "normal", "print"
                        height="None",
                        column_size ="sizeToFit",
                        row_selection={"mode": "singleRow"},
                        on_selection_changed=PathfinderState.set_selected_rows,
                    ),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("file-text", size=16),
                            rx.text("Datei öffnen"),
                            spacing="2",
                        ),
                        on_click=PathfinderState.open_selected_file,
                        variant="outline",
                        color_scheme="jade",
                        disabled=PathfinderState.selected_rows.length() == 0,
                    ),
                    rx.text(
                        "Wählen Sie eine Zeile aus und klicken Sie auf 'Datei öffnen'.",
                        size="1",
                        color="gray",
                        font_style="italic",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),

            rx.text(
                PathfinderState.debug_output,
                color="var(--jade-11)",
                size="2",
            ),
        ),

        # Dateivorschau-Dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(
                            PathfinderState.preview_filename,
                        ),
                        rx.spacer(),
                        rx.dialog.close(
                            rx.icon_button(
                                rx.icon("x"),
                                variant="ghost",
                                on_click=PathfinderState.close_preview,
                            ),
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.dialog.description(
                        "Treffer in Zeile: ",
                        PathfinderState.preview_line,
                    ),
                    rx.box(
                        rx.html(
                            PathfinderState.preview_content_with_line_numbers,
                        ),
                        width="100%",
                        height="500px",
                        overflow_y="scroll",
                        padding="10px",
                        background_color="var(--gray-2)",
                        border="1px solid var(--gray-6)",
                        border_radius="4px",
                        font_family="monospace",
                        font_size="12px",
                        line_height="1.5",
                    ),
                    rx.hstack(
                        rx.button(
                            "Schließen",
                            on_click=PathfinderState.close_preview,
                            variant="solid",
                            color_scheme="jade",
                        ),
                        width="100%",
                        justify="end",
                    ),
                    spacing="3",
                    width="100%",
                ),
                max_width="900px",
                width="90vw",
            ),
            open=PathfinderState.show_preview_dialog,
        ),

        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def tag_content_input() -> rx.Component:
    """UI für Tag-Inhalts-Suche"""

    column_defs = [
        ag_grid.column_def(
            field="filename",
            header_name="Dateiname",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="subdir",
            header_name="Unterverzeichnis",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="line",
            header_name="Zeile",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="tag",
            header_name="Tag",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="text",
            header_name="Inhalt",
            sortable=True,
            filter=True,
        ),
    ]

    return rx.vstack(
        # Warnung wenn keine Dateien geladen
        rx.cond(
            ~TagContentState.has_files,
            rx.callout(
                "Bitte zuerst unter 'Daten' ein Verzeichnis scannen oder Dateien hochladen.",
                icon="triangle-alert",
                color_scheme="red",
            ),
        ),

        rx.heading("Suchmodus", size="3", color="var(--jade-11)", margin_top="20px"),

        # Modus-Auswahl
        rx.radio_group(
            ["Einzelner Tag", "Mehrere Tags"],
            value=TagContentState.search_mode,
            on_change=TagContentState.set_search_mode,
            direction="row",
            spacing="4",
            color_scheme="jade",
        ),

        # Einzelner Tag Modus
        rx.cond(
            TagContentState.search_mode == "Einzelner Tag",
            rx.vstack(
                rx.text("Geben Sie den Tag-Namen ein (ohne Klammern):", size="2"),
                rx.input(
                    value=TagContentState.single_tag_input,
                    placeholder="z.B. entry oder sense",
                    on_change=TagContentState.set_single_tag_input,
                    width="100%",
                    color_scheme="jade",
                ),
                spacing="2",
                width="100%",
            ),
        ),

        # Mehrere Tags Modus
        rx.cond(
            TagContentState.search_mode == "Mehrere Tags",
            rx.vstack(
                # Button zum Laden der Tags
                rx.cond(
                    (TagContentState.all_tags.length() == 0) & ~TagContentState.is_loading_tags,
                    rx.button(
                        "Tags aus Dokumenten laden",
                        on_click=TagContentState.load_all_tags,
                        variant="solid",
                        color_scheme="jade",
                    ),
                ),

                # Ladeanzeige
                rx.cond(
                    TagContentState.is_loading_tags,
                    rx.hstack(
                        rx.spinner(),
                        rx.callout(
                            "Lade Tags aus allen Dokumenten...",
                            color_scheme="jade",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),

                # Durchsuchte Tags
                rx.cond(
                    TagContentState.included_tags.length() > 0,
                    rx.vstack(
                        rx.heading("Durchsuchte Tags", size="2", color="var(--jade-11)"),
                        rx.text("Klicken Sie auf das X, um Tags auszuschließen:", size="1", color="gray"),
                        rx.box(
                            rx.foreach(
                                TagContentState.included_tags,
                                lambda tag: rx.badge(
                                    rx.hstack(
                                        rx.text(tag),
                                        rx.icon(
                                            "x",
                                            size=14,
                                            cursor="pointer",
                                            on_click=TagContentState.exclude_tag(tag),
                                        ),
                                        spacing="1",
                                    ),
                                    color_scheme="jade",
                                    margin="2px",
                                ),
                            ),
                            display="flex",
                            flex_wrap="wrap",
                            gap="5px",
                            padding="10px",
                            border="1px solid var(--gray-6)",
                            border_radius="4px",
                            min_height="50px",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),

                # Ausgeschlossene Tags
                rx.cond(
                    TagContentState.excluded_tags.length() > 0,
                    rx.vstack(
                        rx.heading("Ausgeschlossene Tags", size="2", color="var(--red-11)"),
                        rx.text("Klicken Sie auf einen Tag, um ihn wieder hinzuzufügen:", size="1", color="gray"),
                        rx.box(
                            rx.foreach(
                                TagContentState.excluded_tags,
                                lambda tag: rx.badge(
                                    tag,
                                    color_scheme="red",
                                    cursor="pointer",
                                    on_click=TagContentState.include_tag(tag),
                                    margin="2px",
                                ),
                            ),
                            display="flex",
                            flex_wrap="wrap",
                            gap="5px",
                            padding="10px",
                            border="1px solid var(--gray-6)",
                            border_radius="4px",
                            min_height="50px",
                        ),
                        spacing="2",
                        width="100%",
                        margin_top="10px",
                    ),
                ),

                spacing="3",
                width="100%",
            ),
        ),

        rx.heading("Suchoptionen", size="3", color="var(--jade-11)", margin_top="20px"),

        # Whitespace-Option
        rx.checkbox(
            "Leerzeichen und Zeilenumbrüche in der Suche berücksichtigen",
            checked=TagContentState.include_whitespace,
            on_change=TagContentState.set_include_whitespace,
            color_scheme="jade",
        ),

        # Text-Suche
        rx.vstack(
            rx.text("Suchtext (optional):", size="2"),
            rx.text(
                "Leer lassen, um alle nicht-leeren Tags zu finden.",
                size="1",
                color="gray",
                font_style="italic",
            ),
            rx.hstack(
                rx.input(
                    value=TagContentState.search_text,
                    placeholder="Text zum Suchen eingeben...",
                    on_change=TagContentState.set_search_text,
                    flex="1",
                    color_scheme="jade",
                    font_family="monospace",
                ),
                rx.button(
                    "·",
                    on_click=TagContentState.insert_space,
                    variant="outline",
                    color_scheme="gray",
                    size="2",
                    title="Leerzeichen einfügen",
                ),
                rx.button(
                    "↵",
                    on_click=TagContentState.insert_linebreak,
                    variant="outline",
                    color_scheme="gray",
                    size="2",
                    title="Zeilenumbruch einfügen",
                ),
                width="100%",
                spacing="2",
            ),
            # Visuelle Darstellung mit sichtbaren Whitespace-Zeichen
            rx.cond(
                TagContentState.search_text != "",
                rx.box(
                    rx.text(
                        "Vorschau: ",
                        TagContentState.search_text.replace(" ", "·").replace("\n", "↵\n").replace("\r", "↵"),
                        size="1",
                        font_family="monospace",
                        color="var(--jade-11)",
                    ),
                    padding="5px 10px",
                    background_color="var(--gray-3)",
                    border="1px solid var(--gray-6)",
                    border_radius="4px",
                    width="100%",
                ),
            ),
            spacing="1",
            width="100%",
        ),

        # Suchen-Button
        rx.button(
            rx.cond(
                TagContentState.is_searching,
                rx.hstack(
                    rx.spinner(size="3"),
                    rx.text("Suchen..."),
                    spacing="2",
                ),
                rx.text("Suchen"),
            ),
            on_click=TagContentState.search_tag_content,
            variant="solid",
            color_scheme="jade",
            disabled=TagContentState.is_searching | ~TagContentState.has_files,
            margin_top="10px",
        ),

        # Suchanzeige
        rx.cond(
            TagContentState.is_searching,
            rx.hstack(
                rx.spinner(),
                rx.text(
                    "Durchsuche ",
                    TagContentState.files_checked,
                    " / ",
                    TagContentState.file_count,
                    " Dateien...",
                    color="var(--jade-11)",
                ),
                spacing="2",
                align="center",
            ),
        ),

        # Fehleranzeige
        rx.cond(
            TagContentState.error_message != "",
            rx.callout(
                TagContentState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),

        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),

        # Ergebnisse
        rx.cond(
            TagContentState.has_results,
            rx.vstack(
                rx.text(
                    TagContentState.results_count, " Treffer gefunden",
                    color="var(--jade-11)",
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                    id="tag_content_grid",
                    row_data=TagContentState.content_results,
                    column_defs=column_defs,
                    default_col_def={"flex": 1, "minWidth": 50},
                    pagination=True,
                    pagination_page_size=25,
                    pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                    resizable=True,
                    csv_export_params={"fileName": "tag_content_results.csv", "allColumns": True, "columnSeparator": ";", "exportMode": "csv"},
                    dom_layout="autoHeight",
                    height="None",
                    column_size="sizeToFit",
                    row_selection={"mode": "singleRow"},
                    on_selection_changed=TagContentState.set_selected_rows,
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("file-text", size=16),
                            rx.text("Datei öffnen"),
                            spacing="2",
                        ),
                        on_click=TagContentState.open_selected_file,
                        variant="outline",
                        color_scheme="jade",
                        disabled=TagContentState.selected_rows.length() == 0,
                    ),
                    rx.text(
                        "Wählen Sie eine Zeile aus und klicken Sie auf 'Datei öffnen'.",
                        size="1",
                        color="gray",
                        font_style="italic",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),
            rx.cond(
                ~TagContentState.is_searching,
                rx.cond(
                    TagContentState.tag_not_found,
                    rx.callout(
                        ["Der Tag '", TagContentState.single_tag_input, "' wurde in keinem Dokument gefunden."],
                        icon="circle-x",
                        color_scheme="red",
                    ),
                    rx.callout(
                        "Keine Treffer gefunden.",
                        icon="info",
                        color_scheme="gray",
                    ),
                ),
            ),
        ),

        # Dateivorschau-Dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(
                            TagContentState.preview_filename,
                        ),
                        rx.spacer(),
                        rx.dialog.close(
                            rx.icon_button(
                                rx.icon("x"),
                                variant="ghost",
                                on_click=TagContentState.close_preview,
                            ),
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.dialog.description(
                        "Treffer in Zeile: ",
                        TagContentState.preview_line,
                    ),
                    rx.box(
                        rx.html(
                            TagContentState.preview_content_with_line_numbers,
                        ),
                        width="100%",
                        height="500px",
                        overflow_y="scroll",
                        padding="10px",
                        background_color="var(--gray-2)",
                        border="1px solid var(--gray-6)",
                        border_radius="4px",
                        font_family="monospace",
                        font_size="12px",
                        line_height="1.5",
                    ),
                    rx.hstack(
                        rx.button(
                            "Schließen",
                            on_click=TagContentState.close_preview,
                            variant="solid",
                            color_scheme="jade",
                        ),
                        width="100%",
                        justify="end",
                    ),
                    spacing="3",
                    width="100%",
                ),
                max_width="900px",
                width="90vw",
            ),
            open=TagContentState.show_preview_dialog,
        ),

        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def uniqueness_check() -> rx.Component:
    """UI für Einmaligkeitsprüfung"""

    column_defs = [
        ag_grid.column_def(
            field="filename",
            header_name="Dateiname",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="subdir",
            header_name="Unterverzeichnis",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="line",
            header_name="Zeile",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="error_type",
            header_name="Fehlertyp",
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="details",
            header_name="Details",
            sortable=True,
            filter=True,
        ),
    ]

    return rx.vstack(
        rx.heading("Einmaligkeitsprüfung", size="4", color="var(--jade-11)"),
        rx.text(
            "Prüft, ob Tags, Inhalte oder Attribute innerhalb eines Dokuments einmalig sind.",
            size="2",
            color="var(--gray-11)",
        ),

        rx.spacer(height="20px"),

        # Modus-Auswahl
        rx.heading("Prüfmodus", size="3", color="var(--jade-11)"),
        rx.radio(
            ["Tag", "Tag-Inhalt", "Tag & Attribut", "Attribut"],
            value=UniquenessState.check_mode,
            on_change=UniquenessState.set_check_mode,
            direction="column",
            spacing="2",
        ),

        rx.spacer(height="20px"),

        # Eingabefelder basierend auf Modus
        rx.cond(
            UniquenessState.check_mode == "Tag",
            rx.vstack(
                rx.text("Tag-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.tag_name,
                    placeholder="z.B. title",
                    on_change=UniquenessState.set_tag_name,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),

        rx.cond(
            UniquenessState.check_mode == "Tag-Inhalt",
            rx.vstack(
                rx.text("Tag-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.tag_name,
                    placeholder="z.B. author",
                    on_change=UniquenessState.set_tag_name,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),

        rx.cond(
            UniquenessState.check_mode == "Tag & Attribut",
            rx.vstack(
                rx.text("Tag-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.tag_name,
                    placeholder="z.B. entry",
                    on_change=UniquenessState.set_tag_name,
                    width="100%",
                ),
                rx.text("Attribut-Name:", weight="bold", size="2", margin_top="10px"),
                rx.input(
                    value=UniquenessState.attribute_name,
                    placeholder="z.B. xml:id",
                    on_change=UniquenessState.set_attribute_name,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),

        rx.cond(
            UniquenessState.check_mode == "Attribut",
            rx.vstack(
                rx.text("Attribut-Name:", weight="bold", size="2"),
                rx.input(
                    value=UniquenessState.attribute_name,
                    placeholder="z.B. xml:id",
                    on_change=UniquenessState.set_attribute_name,
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
        ),

        rx.spacer(height="20px"),

        # Prüfen-Button
        rx.button(
            rx.cond(
                UniquenessState.is_checking,
                rx.hstack(
                    rx.spinner(size="3"),
                    rx.text("Prüfe..."),
                    spacing="2",
                ),
                rx.text("Prüfung starten"),
            ),
            on_click=UniquenessState.check_uniqueness,
            variant="solid",
            color_scheme="jade",
            disabled=UniquenessState.is_checking,
        ),

        rx.cond(
            UniquenessState.is_checking,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    f"Durchsuche Dokumente... ({UniquenessState.files_checked} geprüft)",
                    color_scheme="jade",
                ),
                spacing="2",
                align="center",
            ),
        ),

        rx.cond(
            UniquenessState.error_message != "",
            rx.callout(
                UniquenessState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),

        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),

        rx.cond(
            UniquenessState.has_results,
            rx.vstack(
                rx.text(
                    UniquenessState.results_count, " Fehler gefunden",
                    color="var(--red-11)",
                    size="2",
                    weight="bold",
                ),
                ag_grid(
                    id="uniqueness_results_grid",
                    row_data=UniquenessState.uniqueness_results,
                    column_defs=column_defs,
                    default_col_def={"flex": 1, "minWidth": 50},
                    pagination=True,
                    pagination_page_size=25,
                    pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                    resizable=True,
                    csv_export_params={"fileName": "uniqueness_errors.csv", "allColumns": True, "columnSeparator": ";", "exportMode": "csv"},
                    dom_layout="autoHeight",
                    height="None",
                    column_size="sizeToFit",
                    row_selection={"mode": "singleRow"},
                    on_selection_changed=UniquenessState.set_selected_rows,
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("file-text", size=16),
                            rx.text("Datei öffnen"),
                            spacing="2",
                        ),
                        on_click=UniquenessState.open_selected_file,
                        variant="outline",
                        color_scheme="jade",
                        disabled=UniquenessState.selected_rows.length() == 0,
                    ),
                    rx.text(
                        "Wählen Sie eine Zeile aus und klicken Sie auf 'Datei öffnen'.",
                        size="1",
                        color="gray",
                        font_style="italic",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="3",
                width="100%",
            ),
            rx.callout(
                "Keine Fehler gefunden - alle geprüften Elemente sind einmalig.",
                icon="check",
                color_scheme="jade",
            ),
        ),

        # Dateivorschau-Dialog
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.dialog.title(
                            UniquenessState.preview_filename,
                        ),
                        rx.spacer(),
                        rx.dialog.close(
                            rx.icon_button(
                                rx.icon("x"),
                                variant="ghost",
                                on_click=UniquenessState.close_preview,
                            ),
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.dialog.description(
                        "Zeile: ",
                        UniquenessState.preview_line,
                    ),
                    rx.box(
                        rx.html(
                            UniquenessState.preview_content_with_line_numbers,
                        ),
                        width="100%",
                        height="500px",
                        overflow_y="scroll",
                        padding="10px",
                        background_color="var(--gray-2)",
                        border="1px solid var(--gray-6)",
                        border_radius="4px",
                        font_family="monospace",
                        font_size="12px",
                        line_height="1.5",
                    ),
                    rx.hstack(
                        rx.button(
                            "Schließen",
                            on_click=UniquenessState.close_preview,
                            variant="solid",
                            color_scheme="jade",
                        ),
                        width="100%",
                        justify="end",
                    ),
                    spacing="3",
                    width="100%",
                ),
                max_width="900px",
                width="90vw",
            ),
            open=UniquenessState.show_preview_dialog,
        ),

        rx.spacer(height="30px"),
        spacing="4",
        width="100%",
    )


def select_data_input_method() -> rx.Component:
    
    column_defs = [
        ag_grid.column_def(
            field="filename",
            header_name="Dateiname",
            # width=300,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="subdir",
            header_name="Unterverzeichnis",
            # width=150,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="size_kb",
            header_name="Dateigröße (KB)",
            # width=100,
            sortable=True,
            filter=True,
        ),
    ]

    return rx.vstack(
        
        rx.vstack(
            rx.heading("Modus", size="3", color="var(--jade-11)"),
            rx.text("Wie möchten Sie XML-Dateien bereitstellen?"),
            rx.spacer(height="30px"),
            rx.text("Die Option 'Verzeichnispfad' durchsucht ein Verzeichnis und eignet sich besonders bei lokaler Installation. Die Option 'Datei-Upload' ermöglicht das Hochladen von XML-Dateien oder ZIP-Archiven.", color="gray", style={'font_style': 'italic'}),
            rx.text("Bei der 'Datei-Upload'-Methode werden die Dateien in einem temporären Verzeichnis gespeichert und verarbeitet. Dieses Verzeichnis wird automatisch bereinigt, wenn die Session endet.", color="gray", style={'font_style': 'italic'}),
            rx.text("Aus Sicherheitsgründen bestehen diverse Beschränkungen beim Hochladen von Dateien (max. Dateigröße, max. Anzahl Dateien, keine ausführbaren Dateien etc.).", color="gray", style={'font_style': 'italic'}),
            rx.spacer(height="30px"),
            rx.radio_group(
                ["Verzeichnispfad", "Datei-Upload"],
                value=FileState.upload_mode,
                on_change=FileState.set_upload_mode,
                direction="row",
                spacing="4",
                color_scheme="jade",
            ),
            align_items="start",
            spacing="2",
        ),
        
        # Bedingte Anzeige: Pfad-Input ODER Upload
        rx.cond(
            FileState.upload_mode == "Verzeichnispfad",
            path_input_section(column_defs),
            #rx.text("Bitte Eingabemethode auswählen.")
        ),
        
        rx.cond(
            FileState.upload_mode == "Datei-Upload",
            upload_section(column_defs),
            #rx.text("Bitte Eingabemethode auswählen.")
        ),
        
        spacing="4",
        width="100%",
    )




def path_input_section(column_defs) -> rx.Component:
        
        return rx.vstack(

            rx.heading("Verzeichnispfad", size="3", color="var(--jade-11)", margin_top="30px"),
                       
            rx.text(
                "Bitte geben Sie den vollständigen Pfad zu Ihrem XML-Verzeichnis ein:",
            ),
            rx.text(
                "Beispiel: /home/user/dokumente/xml oder C:\\Users\\Name\\Documents\\XML",
                size="2",
                color="var(--jade-11)",
                font_family="monospace",
            ),
            
            rx.text(
                "Tip: Pfad aus der Adresszeile des Explorers/Finders etc. kopieren und hier einfügen.",
                size="2",
                color="var(--jade-11)",
                font_family="monospace",
            ),

            rx.hstack(
                rx.input(
                    value=FileState.directory_path,
                    placeholder="Pfad zum XML-Verzeichnis eingeben...",
                    on_change=FileState.set_directory_path,
                    on_key_down=FileState.handle_key_down,
                    disabled=FileState.is_loading,
                    width="100%",
                    color_scheme="jade",
                ),
                rx.button(
                    rx.cond(
                        FileState.is_loading,
                        rx.hstack(
                            rx.spinner(size="3"),
                            rx.text("Durchsuche..."),
                            spacing="2",
                        ),
                        rx.text("Durchsuchen"),
                    ),
                    on_click=[ValidatorState.reset_validation, FileState.scan_xml_files],
                    variant="solid",
                    color_scheme="jade",
                    disabled=FileState.is_loading,
                ),
                width="100%",
            ),
            
            rx.cond(
                FileState.is_loading,
                rx.hstack(
                    rx.spinner(),
                    rx.callout(
                        "Durchsuche Verzeichnis rekursiv nach XML-Dateien...",
                        color_scheme="jade",
                    ),
                    spacing="2",
                    align="center",
                ),
            ),
            
            rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),

            rx.cond(
                FileState.error_message != "",
                rx.callout(
                    FileState.error_message,
                    icon="message-circle-warning",
                    color_scheme="red",
                ),
            ),

            rx.cond(
                FileState.has_files,
                rx.vstack(
                    rx.text(
                        FileState.file_count, " XML-Dateien gefunden",
                        color="var(--jade-11)",
                        size="2",
                        weight="bold",
                    ),

                    ag_grid(
                        id="path_input_grid",
                        row_data=FileState.xml_files_data,
                        column_defs=column_defs,                        
                        default_col_def={"flex": 1, "minWidth": 50},
                        pagination=True,
                        pagination_page_size=25,
                        pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                        resizable=True,
                        csv_export_params={"fileName": "xml_files.csv", "allColumns": True, "columnSeparator": ";", "exportMode": "csv"},
                        dom_layout="autoHeight", #options: "autoHeight", "normal", "print"
                        height="None",
                        column_size ="sizeToFit",
                    ),
                    rx.spacer(height="30px"),
                    #rx.text("Tipp: Klicken Sie auf das Download-Symbol oben rechts in der Tabelle, um die Dateiliste als CSV-Datei herunterzuladen.", color="gray", size="2"),
                    spacing="3",
                    width="100%",
                ),
            ),
            spacing="4",
            width="100%",
        )

def upload_section(column_defs) -> rx.Component:
    return rx.vstack(
        rx.text(
            "Laden Sie eine oder mehrere XML-Dateien oder ein ZIP-Archiv hoch:",
            size="2",
            color="gray",
        ),
        
        rx.upload(
            rx.vstack(
                rx.button(
                    "Dateien auswählen",
                    color_scheme="jade",
                    variant="outline",
                ),
                rx.text(
                    "Oder Dateien hier hinziehen",
                    size="1",
                    color="gray",
                ),
                # Status-Anzeige
                rx.cond(
                    rx.selected_files("file_upload"),
                    rx.vstack(
                        rx.text("Bereit zum Hochladen.", weight="bold", size="2", color_scheme="jade"),
                    ),
                    rx.text("Keine Dateien ausgewählt", size="1", color="gray"),
                ),
                align="center",
            ),
            id="file_upload",
            accept={
                "application/xml": [".xml"],
                "application/zip": [".zip"],
            },
            multiple=True,
            max_files=100,
            max_size=MAX_FILE_SIZE,
            border="1px dotted var(--gray-6)",
            padding="60px",
            background_color="var(--gray-3)",
            border_radius="6px",
            width="100%",
            disabled=FileState.is_loading,
            color_scheme="jade",
        ),

        
        # Upload-Button
        rx.button(
            "Hochladen & Verarbeiten",
            on_click=[ValidatorState.reset_validation, FileState.handle_upload(rx.upload_files(upload_id="file_upload"))],
            variant="solid",
            color_scheme="jade",
            disabled=FileState.is_loading,
        ),
        
        rx.cond(
            FileState.is_loading,
            rx.hstack(
                rx.spinner(),
                rx.callout(
                    "Lade Dateien hoch und verarbeite...",
                    color_scheme="jade",
                ),
                spacing="2",
                align="center",
            ),
        ),

        rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),

        rx.cond(
            FileState.error_message != "",
            rx.callout(
                FileState.error_message,
                icon="message-circle-warning",
                color_scheme="red",
            ),
        ),
        
        rx.cond(
            FileState.has_files,
            rx.vstack(
                rx.text(
                    FileState.file_count, " XML-Dateien gefunden",
                    color="var(--jade-11)",
                    size="2",
                    weight="bold",
                ),

                ag_grid(
                    id="upload_grid",
                    row_data=FileState.xml_files_data,
                    column_defs=column_defs,                        
                    default_col_def={"flex": 1, "minWidth": 50},
                    pagination=True,
                    pagination_page_size=25,
                    pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                    resizable=True,
                    csv_export_params={"fileName": "xml_files.csv", "allColumns": True, "columnSeparator": ";", "exportMode": "csv"},
                    dom_layout="autoHeight", #options: "autoHeight", "normal", "print"
                    height="None",
                    column_size ="sizeToFit",
                ),
                rx.spacer(height="30px"),
                rx.text("Tipp: Klicken Sie auf das Download-Symbol oben rechts in der Tabelle, um die Dateiliste als CSV-Datei herunterzuladen.", color="gray", size="2"),
                spacing="3",
                width="100%",
                padding_bottom="20px",
            ),
        ),

    spacing="3",
    width="100%",
)

# ============ Sidebar Komponenten ============

def sidebar_item(text: str, url: str, icon: str = "chevron-right"):
    return rx.link(
        rx.hstack(
            rx.icon(
                tag=icon,
                size=16,
                color="var(--jade-12)"
            ),
            rx.text(text, color="var(--gray-12)"),
            spacing="2",
            vertical_align="bottom",
        ),
        href=url,
        width="100%",
    )

def sidebar_left() -> rx.Component:
    return rx.vstack(
        # rx.heading("Menü", size="6"),
        # rx.divider(),
        # https://reflex.dev/docs/library/data-display/icon/#icons-list
        sidebar_item("Home", "/", "home"),
        sidebar_item("Daten", "/data", "files"),
        sidebar_item("XML/TL0 Validator", "/validator", "file-check"),
        sidebar_item("Tag- und Pfadsuche", "/pathfinder", "search-code"),
        sidebar_item("Inhalt / Leere Tags", "/tag-content", "text-search"),
        sidebar_item("Einmaligkeit", "/uniqueness", "shield-check"),
        rx.spacer(),
        rx.text("Version 0.1", size="1", color="gray"),
        width="250px",
        #height="100vh",
        padding="20px",
        spacing="3",
        # bg="var(--gray-2)",
        border_radius="4px",
        border="1px solid var(--gray-4)",
        box_shadow="0 4px 12px rgba(0, 0, 0, 0.1)",
        margin_left="20px",
        margin_right="20px",
        margin_bottom="20px",
        # position="fixed",
        left="0",
        top="100",
    )

def sidebar_right() -> rx.Component:
    return rx.vstack(
        rx.heading("Übersicht", size="3"),
        rx.spacer(),
        rx.text("Daten-Modus", size="2", weight="bold"),
        rx.text(FileState.upload_mode, size="2"),
        rx.text("Daten-Verzeichnis", size="2", weight="bold"),
        rx.tooltip(
            rx.text(FileState.directory_path, size="2", max_width="100px", overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
            content=FileState.directory_path,
        ),
        rx.text("Anzahl XML-Dateien", size="2", weight="bold"),
        rx.text(FileState.file_count, size="2"),
        width="250px",
        padding="20px",
        spacing="2",
        # bg="var(--gray-2)",
        border_radius="4px",
        border="1px solid var(--gray-4)",
        box_shadow="0 4px 12px rgba(0, 0, 0, 0.1)",
        margin_left="20px",
        margin_right="20px",
        margin_bottom="20px",
        left="0",
        top="100",
    )

# ============ Base Layout ============

def base_layout(content: rx.Component) -> rx.Component:
    return rx.vstack(  # container for header and main content
                rx.box( # outer box for padding
                    rx.box( # inner box for header styling
                        rx.hstack( # header content, with the color mode button
                            rx.text("LT Wörterbuch-Konsistenz-Prüfer", size="4", weight="bold"),
                            rx.spacer(),  # moves the button to the right
                            rx.color_mode.button(),
                            width="100%",
                            align_items="center",
                        ),
                        padding="20px",
                        background_color="#003835",
                        color="white",
                        width="100%",
                        border_radius="4px",
                        box_shadow="0 4px 12px rgba(0, 56, 53, 0.3)",
                    ),
                    padding="20px",  # padding around the header box (white margin)
                    width="100%",
                ),
                rx.hstack(
                    sidebar_left(),
                    rx.box(
                        content,
                        width="60%",
                    ),
                    sidebar_right(),
                    width="100%",
                ),
                max_width="1400px",
            )   

# ============ Pages ============

def index() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("Start", size="4", color="var(--jade-12)"),
                rx.text(
                    "Dieses Werkzeug bietet verschiedene Möglichkeiten zur Konsistenzprüfung von Wörterbüchern auf XML-Basis. Es funktioniert mit beliebigen XML-Schemata, aber am besten mit TEI-Lex 0.",
                ),
                rx.text(
                    "Schritte:",
                ),
                rx.list(
                    rx.list.item(
                        rx.icon("arrow_up_narrow_wide", color="var(--jade-11)", margin_right="10px"),
                        "Datenimport: Verzeichnis angeben oder XML-Dateien/ZIP-Archive hochladen.",
                        margin_top="0px"
                    ),
                    rx.list.item(
                        rx.icon("check_line", color="var(--jade-11)", margin_right="10px"),
                        "Verschiedene Konsistenzprüfungen durchführen",
                        margin_top="20px"
                    ),
                    rx.list.item(
                        rx.icon("expand", color="var(--jade-11)", margin_right="10px"), 
                        "Ergebnisse exportieren und weiterverarbeiten",
                        margin_top="20px"
                    ),
                    list_style_type="none",
                ),
                spacing="5",
                justify="center",
            ),
        )
    )

def data_page() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("Daten", size="4", color="var(--jade-12)"),
                select_data_input_method(),
                spacing="4",
            ),
        )
    )

def validator_page() -> rx.Component:

    column_defs = [
        ag_grid.column_def(
            field="filename",
            header_name="Dateiname",
            # width=300,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="subdir",
            header_name="Unterverzeichnis",
            # width=150,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="line",
            header_name="Zeile",
            # width=100,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="column",
            header_name="Spalte",
            # width=100,
            sortable=True,
            filter=True,
        ),
        ag_grid.column_def(
            field="error",
            header_name="Fehler",
            # width=100,
            sortable=True,
            filter=True,
        ),
    ]

    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("XML-Validator", size="4", color="var(--jade-12)"),
                rx.text("Prüft XML-Dateien auf Wohlgeformtheit oder gegen ein TEI-Lex 0 Schema."),
                rx.text("Wenn beide Validierungstypen durchgeführt werden sollen, muss die Validierung zweimal gestartet werden (jeweils für einen Typ). Es werden dann beide Ergebnisse untereinander angezeigt."),

                # Warnung wenn keine Dateien geladen
                rx.cond(
                    ~ValidatorState.can_validate,
                    rx.callout(
                        "Bitte zuerst unter 'Konfiguration' ein Verzeichnis scannen.",
                        icon="triangle-alert",
                        color_scheme="red",
                    ),
                ),

                rx.heading("Validierungstyp", size="3", color="var(--jade-11)", margin_top="30px"),

                # Validierungsoptionen
                rx.cond(
                    ValidatorState.can_validate,
                    rx.vstack(
                        # Validierungstyp auswählen

                        rx.radio_group(
                            ["Wohlgeformtheit (Well-formed XML)", "TEI-Lex 0 Schema (RelaxNG)"],
                            value=ValidatorState.validation_type,
                            on_change=ValidatorState.set_validation_type,
                            direction="row",
                            color_scheme="jade",
                        ),

                        # Buttons
                        rx.hstack(
                            rx.button(
                                rx.cond(
                                    ValidatorState.is_validating,
                                    rx.hstack(
                                        rx.spinner(size="3"),
                                        rx.text("Validiere..."),
                                        spacing="2",
                                        color_scheme="jade",
                                    ),
                                    rx.hstack(
                                        rx.icon("play", size=16),
                                        rx.text("Validierung starten"),
                                        spacing="2",
                                        color_scheme="jade",
                                    ),
                                ),
                                on_click=ValidatorState.validate_all_xml,
                                variant="solid",
                                color_scheme="jade",
                                disabled=~ValidatorState.can_start_validation | ValidatorState.is_validating,
                            ),
                        
                        )
                    )
                ),

                rx.heading("Ergebnisse", size="3", color="var(--jade-11)", margin_top="30px"),



                # Schema-Datei-Fehler anzeigen
                rx.cond(
                    ValidatorState.schema_error != "",
                    rx.callout(
                        ValidatorState.schema_error,
                        icon="circle-alert",
                        color_scheme="red",
                    ),
                ),

                # CSV Download - Wohlgeformtheit
                rx.cond(
                    ValidatorState.has_wellformed_errors,
                    rx.button(
                        rx.hstack(
                            rx.icon("download", size=16),
                            rx.text("CSV Wohlgeformtheit"),
                            spacing="2",
                        ),
                        on_click=ValidatorState.download_wellformed_errors_csv,
                        variant="outline",
                        color_scheme="jade",
                    ),
                ),
                
                # CSV Download - Schema
                rx.cond(
                    ValidatorState.has_schema_errors,
                    rx.button(
                        rx.hstack(
                            rx.icon("download", size=16),
                            rx.text("CSV Schema"),
                            spacing="2",
                        ),
                        on_click=ValidatorState.download_schema_errors_csv,
                        variant="outline",
                        color_scheme="jade",
                    ),
                ),
                spacing="3",
            ),

            # Fortschritt während Validierung
            rx.cond(
                ValidatorState.is_validating,
                rx.hstack(
                    rx.spinner(),
                    rx.text(
                        "Geprüft: ", ValidatorState.files_checked,
                        " / ", ValidatorState.file_count,
                        " Dateien (", ValidatorState.validation_type_label, ")",
                        color="var(--jade-11)",
                    ),
                    spacing="2",
                    align="center",
                ),
            ),

            # Ergebnis nach Validierung - Wohlgeformtheit
            rx.cond(
                ValidatorState.wellformed_validation_complete,
                rx.cond(
                    ValidatorState.has_wellformed_errors,
                    rx.callout(
                        [ValidatorState.files_with_wellformed_errors,
                         " von ",
                         ValidatorState.files_checked,
                         " Dateien haben Wohlgeformtheits-Fehler (",
                         ValidatorState.wellformed_error_count,
                         " Fehler insgesamt)"],
                        icon="circle-alert",
                        color_scheme="red",
                        margin_top="20px",
                    ),
                    rx.callout(
                        ["Alle ",
                         ValidatorState.files_checked,
                         " Dateien sind wohlgeformt."],
                        icon="check-check",
                        color_scheme="jade",
                        margin_top="20px",
                    ),
                ),
            ),

            # Ergebnis nach Validierung - Schema
            rx.cond(
                ValidatorState.schema_validation_complete,
                rx.cond(
                    ValidatorState.has_schema_errors,
                    rx.callout(
                        [ValidatorState.files_with_schema_errors,
                         " von ",
                         ValidatorState.files_checked,
                         " Dateien haben Schema-Fehler (",
                         ValidatorState.schema_error_count,
                         " Fehler insgesamt)."],
                        icon="circle-alert",
                        color_scheme="red",
                        margin_top="20px",
                    ),
                    rx.callout(
                        ["Alle ",
                         ValidatorState.files_checked,
                         " Dateien sind schema-valide."],
                        icon="check-check",
                        color_scheme="jade",
                        margin_top="20px",
                    ),
                ),
            ),

            # Fehler-Tabelle Wohlgeformtheit
            rx.cond(
                ValidatorState.has_wellformed_errors,
                rx.vstack(
                    rx.heading("Fehler Wohlgeformtheit", size="2", color="var(--jade-12)", margin_top="30px"),
                    ag_grid(
                        id="xml_error_grid",
                        row_data=ValidatorState.wellformed_errors,
                        column_defs=column_defs,                        
                        default_col_def={"flex": 1, "minWidth": 50},
                        pagination=True,
                        pagination_page_size=25,
                        pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                        resizable=True,
                        csv_export_params={"fileName": "xml_files.csv", "allColumns": True, "columnSeparator": ";", "exportMode": "csv"},
                        dom_layout="autoHeight", #options: "autoHeight", "normal", "print"
                        height="None",
                        column_size ="sizeToFit",
                    ),

                    spacing="2",
                    width="100%",
                ),
            ),

            # Fehler-Tabelle Schema
            rx.cond(
                ValidatorState.has_schema_errors,
                rx.vstack(
                    rx.heading("Fehler Schema", size="2", color="var(--jade-12)", margin_top="30px"),
                    ag_grid(
                        id="schema_error_grid",
                        row_data=ValidatorState.schema_errors,
                        column_defs=column_defs,                        
                        default_col_def={"flex": 1, "minWidth": 50},
                        pagination=True,
                        pagination_page_size=25,
                        pagination_page_size_selector=[5, 10, 25, 50, 100, 250],
                        resizable=True,
                        csv_export_params={"fileName": "xml_files.csv", "allColumns": True, "columnSeparator": ";", "exportMode": "csv"},
                        dom_layout="autoHeight", #options: "autoHeight", "normal", "print"
                        height="None",
                        column_size ="sizeToFit",
                    ),
                    spacing="2",
                    width="100%",
                ),
            ),

            rx.spacer(height="30px"),

            spacing="4",
            width="100%",
        ),
    ),


                            

def pathfinder_page() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("Tag- und Pfadsuche", size="4", color="var(--jade-12)"),
                pathfinder_input(),
                spacing="4",
            ),
        )
    )

def tag_content_page() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("Inhalt / Leere Tags", size="4", color="var(--jade-12)"),
                rx.text("Durchsuchen Sie Tags nach bestimmten Inhalten oder finden Sie nicht-leere Tags."),
                tag_content_input(),
                spacing="4",
            ),
        )
    )

def uniqueness_page() -> rx.Component:
    return base_layout(
        rx.container(
            rx.vstack(
                rx.heading("Einmaligkeit", size="4", color="var(--jade-12)"),
                uniqueness_check(),
                spacing="4",
            ),
        )
    )

# ============ App ============

app = rx.App()
app.add_page(index)
app.add_page(data_page, route="/data")
app.add_page(validator_page, route="/validator")
app.add_page(pathfinder_page, route="/pathfinder")
app.add_page(tag_content_page, route="/tag-content")
app.add_page(uniqueness_page, route="/uniqueness")

# TODO: Uniqueness funktioniert noch nicht richtig, checken
# TODO: Wurden alte Funktionen beschädigt?
# TODO: Aufteilung der Datei in kleinere Files.

""" 

Neue FUnktionen

Uniqueness & Identifikatoren

Eindeutigkeit von IDs: Jeder Eintrag/jedes Element mit @xml:id sollte unique sein
Duplikate bei Lemmata: Prüfung, ob Stichwörter mehrfach vorkommen (kann gewollt sein bei Homographen, aber sollte dokumentiert sein)
ID-Konventionen: Einheitliches Format für IDs (z.B. entry_0001 vs e0001 vs gemischte Formate)

Referenz-Integrität

Broken References: Interne Verweise (@target, @corresp) zeigen auf nicht-existierende IDs
Bidirektionale Verweise: Bei gegenseitigen Verweisen sollten beide Richtungen existieren
Orphaned Entries: Einträge, auf die nie verwiesen wird (je nach Konzept relevant)

Kontrollierte Vokabulare

Wortarten: <gram type="pos"> sollte aus festem Set stammen (noun, verb, adj, ...)
Sprachcodes: @xml:lang sollte valide ISO 639 Codes verwenden
Domänen/Fachgebiete: Falls verwendet, aus kontrollierter Liste
Status-Angaben: z.B. "veraltet", "regional", "umgangssprachlich" einheitlich

Strukturelle Konsistenz

Element-Reihenfolge: Gleiche Elemente sollten in gleicher Sequenz erscheinen (z.B. immer erst <form>, dann <gramGrp>, dann <sense>)
Verschachtelungstiefe: Ungewöhnlich tiefe/flache Strukturen aufspüren
Pflicht-Kindelemente: Bestimmte Elemente sollten immer Kinder haben (z.B. <sense> sollte <def> enthalten)

Inhaltliche Muster

Leere vs. fehlende Elemente: Unterscheidung zwischen <def/> und gar keinem <def>
Text-Längen: Extrem kurze/lange Definitionen, Beispiele etc.
Sonderzeichen: Inkonsistente Verwendung von Gedankenstrichen, Anführungszeichen
Datumsformate: Falls Daten vorkommen, einheitliches Format

Metadaten-Qualität

Bearbeiter-Namen: Einheitliche Schreibweise von Autorennamen
Versionierung: @resp, @cert konsistent verwendet
Zeitstempel: @when, @notBefore in validen Formaten

Stilistische Konsistenz (komplexer)

Kapitalisierung: Definitionen einheitlich mit Großbuchstaben beginnen (oder nicht)
Interpunktion: Definitionen enden auf Punkt (oder nicht)
Abkürzungen: "z.B." vs "z. B." vs "zum Beispiel"
Beispiel-Formatierung: Kursiv, Anführungszeichen, etc.

Quantitative Metriken

Vollständigkeitsgrad: Wie viele Einträge haben alle empfohlenen Felder?
Ausreißer-Erkennung: Einträge mit ungewöhnlich vielen/wenigen Sinnen, Beispielen etc.
Coverage: Welche Buchstaben/Bereiche sind unterrepräsentiert?

Praktische Umsetzung
Für den Anfang würde ich empfehlen:

ID-Duplikate (einfach, hoher Wert)
Broken References (wichtig für Navigation)
Kontrollierte Vokabulare für Wortarten (häufiger Fehler)
Leere Pflicht-Elemente (habt ihr schon ansatzweise)


 """