import reflex as rx
import base64
import io
from typing import TypedDict

from .settings import LLMSettingsState
from .components import (
    base_layout,
    page_container,
    page_heading,
    section_heading,
    error_callout,
    HEADING_SECTION,
    TEXT_MUTED,
    PANEL_BORDER,
    COLOR_DANGER,
    TEXT_RESULT,
)


# ============ Types ============


class OcrPage(TypedDict):
    thumb_url: str
    result: str


class OcrItem(TypedDict):
    name: str
    pages: list[OcrPage]
    status: str
    error: str
    _idx: int


# ============ Constants ============

MAX_FILES = 10
MAX_FILE_SIZE_MB = 5
THUMB_MAX_PX = 350  # Max thumbnail dimension in pixels

DEFAULT_OCR_PROMPT = (
    "Erkenne den gesamten Text in diesem Bild vollständig und originalgetreu. "
    "Gib nur den erkannten Text zurück, ohne Kommentare oder Erläuterungen. "
    "Behalte die ursprüngliche Struktur (Absätze, Zeilenumbrüche) soweit möglich bei."
)

ACCEPTED_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "application/pdf": [".pdf"],
}


# ============ State ============


class OCRState(rx.State):
    """State for OCR page: file upload, thumbnail display, LLM-based text recognition."""

    # Serialized to client.
    # Each item: {name, pages: [{thumb_url, result}], status, error, _idx}
    # status: "ready" | "processing" | "done" | "error"
    ocr_items: list[dict] = []

    is_processing: bool = False
    error_message: str = ""
    ocr_prompt: str = DEFAULT_OCR_PROMPT

    # Backend vars: server-side only, not serialized.
    # Parallel list to ocr_items: [{media_type, data_b64}] per page per file.
    _full_images: list[list[dict]] = []

    # ---- Computed vars ----

    @rx.var
    def has_items(self) -> bool:
        return len(self.ocr_items) > 0

    @rx.var
    def items_count(self) -> int:
        return len(self.ocr_items)

    @rx.var
    def any_ready(self) -> bool:
        return any(item.get("status") == "ready" for item in self.ocr_items)

    @rx.var
    def ocr_items_indexed(self) -> list[OcrItem]:
        """ocr_items with _idx injected, so rx.foreach callbacks can call remove_item."""
        return [{**item, "_idx": i} for i, item in enumerate(self.ocr_items)]

    # ---- Setters ----

    def set_ocr_prompt(self, value: str) -> None:
        self.ocr_prompt = value

    def clear_all(self) -> None:
        self.ocr_items = []
        self._full_images = []
        self.error_message = ""
        self.is_processing = False

    def remove_item(self, index: int) -> None:
        items = list(self.ocr_items)
        imgs = list(self._full_images)
        if 0 <= index < len(items):
            items.pop(index)
            imgs.pop(index)
        self.ocr_items = items
        self._full_images = imgs

    # ---- File processing helpers (backend only) ----

    def _make_thumbnail_url(self, img_bytes: bytes, media_type: str) -> str:
        """Resize image to thumbnail and return as base64 data URL."""
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        # Normalise mode for JPEG
        if img.mode in ("CMYK", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode == "RGBA" and media_type == "image/jpeg":
            img = img.convert("RGB")

        img.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX), Image.LANCZOS)

        buf = io.BytesIO()
        fmt = "JPEG" if media_type == "image/jpeg" else "PNG"
        save_kwargs = {"quality": 80} if fmt == "JPEG" else {}
        img.save(buf, format=fmt, **save_kwargs)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:{media_type};base64,{b64}"

    def _process_image_file(
        self, data: bytes, filename: str
    ) -> tuple[list[dict], list[dict]]:
        """Process JPG/PNG. Returns (state_pages, llm_pages)."""
        media_type = (
            "image/jpeg"
            if filename.lower().endswith((".jpg", ".jpeg"))
            else "image/png"
        )
        thumb_url = self._make_thumbnail_url(data, media_type)
        full_b64 = base64.b64encode(data).decode()
        return (
            [{"thumb_url": thumb_url, "result": ""}],
            [{"media_type": media_type, "data_b64": full_b64}],
        )

    def _process_pdf_file(
        self, data: bytes
    ) -> tuple[list[dict], list[dict]]:
        """Render each PDF page to PNG. Returns (state_pages, llm_pages)."""
        import fitz  # pymupdf

        doc = fitz.open(stream=data, filetype="pdf")
        state_pages: list[dict] = []
        llm_pages: list[dict] = []

        for page in doc:
            pix_full = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
            pix_thumb = page.get_pixmap(matrix=fitz.Matrix(72 / 72, 72 / 72))

            full_b64 = base64.b64encode(pix_full.tobytes("png")).decode()
            thumb_b64 = base64.b64encode(pix_thumb.tobytes("png")).decode()

            state_pages.append({
                "thumb_url": f"data:image/png;base64,{thumb_b64}",
                "result": "",
            })
            llm_pages.append({"media_type": "image/png", "data_b64": full_b64})

        return state_pages, llm_pages

    # ---- Upload handler ----

    async def handle_upload(self, files: list[rx.UploadFile]) -> None:
        """Process uploaded files, build thumbnails, prepare for OCR."""
        max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
        remaining = MAX_FILES - len(self.ocr_items)
        self.error_message = ""

        if remaining <= 0:
            self.error_message = f"Maximal {MAX_FILES} Dateien erlaubt."
            return

        for file in files[:remaining]:
            data = await file.read()
            filename = file.filename or "unbekannt"

            if len(data) > max_bytes:
                size_mb = round(len(data) / 1024 / 1024, 1)
                self.ocr_items = list(self.ocr_items) + [{
                    "name": filename,
                    "pages": [],
                    "status": "error",
                    "error": f"Datei zu groß ({size_mb} MB, max {MAX_FILE_SIZE_MB} MB)",
                }]
                self._full_images = list(self._full_images) + [[]]
                continue

            try:
                if filename.lower().endswith(".pdf"):
                    state_pages, llm_pages = self._process_pdf_file(data)
                else:
                    state_pages, llm_pages = self._process_image_file(data, filename)

                self.ocr_items = list(self.ocr_items) + [{
                    "name": filename,
                    "pages": state_pages,
                    "status": "ready",
                    "error": "",
                }]
                self._full_images = list(self._full_images) + [llm_pages]

            except Exception as e:
                self.ocr_items = list(self.ocr_items) + [{
                    "name": filename,
                    "pages": [],
                    "status": "error",
                    "error": f"Fehler beim Verarbeiten: {e}",
                }]
                self._full_images = list(self._full_images) + [[]]

    # ---- OCR ----

    async def run_ocr(self):
        """Send each file's pages to the LLM for text recognition."""
        settings = await self.get_state(LLMSettingsState)
        if not settings.has_active_llm:
            self.error_message = (
                "Kein LLM konfiguriert. Bitte zuerst unter LLM → Einstellungen verbinden."
            )
            return

        self.is_processing = True
        self.error_message = ""
        yield

        for i in range(len(self.ocr_items)):
            item = self.ocr_items[i]
            if item.get("status") != "ready":
                continue
            if i >= len(self._full_images) or not self._full_images[i]:
                continue

            # Mark as processing
            items = list(self.ocr_items)
            items[i] = {**items[i], "status": "processing"}
            self.ocr_items = items
            yield

            llm_pages = self._full_images[i]
            result_pages = [dict(p) for p in item.get("pages", [])]

            try:
                for j, llm_page in enumerate(llm_pages):
                    text = await self._call_llm_vision(
                        llm_page["data_b64"],
                        llm_page["media_type"],
                        self.ocr_prompt,
                        settings,
                    )
                    if j < len(result_pages):
                        result_pages[j] = {**result_pages[j], "result": text}

                    # Update UI progressively after each page
                    items = list(self.ocr_items)
                    items[i] = {**items[i], "pages": list(result_pages), "status": "processing"}
                    self.ocr_items = items
                    yield

                items = list(self.ocr_items)
                items[i] = {**items[i], "pages": result_pages, "status": "done"}
                self.ocr_items = items
                yield

            except Exception as e:
                err = str(e)
                if "ConnectError" in err or "Connection" in err:
                    msg = "Verbindung zum LLM fehlgeschlagen."
                elif "timeout" in err.lower():
                    msg = "Zeitüberschreitung – Bild möglicherweise zu groß."
                elif "404" in err:
                    msg = "Modell nicht gefunden."
                else:
                    msg = f"LLM-Fehler: {err}"

                items = list(self.ocr_items)
                items[i] = {**items[i], "status": "error", "error": msg}
                self.ocr_items = items
                yield

        self.is_processing = False

    # ---- LLM vision backends ----

    async def _call_llm_vision(
        self, image_b64: str, media_type: str, prompt: str, settings
    ) -> str:
        if settings.provider == "Anthropic":
            return await self._call_anthropic_vision(image_b64, media_type, prompt, settings)
        elif settings.provider == "Ollama":
            return await self._call_ollama_vision(image_b64, prompt, settings)
        else:
            return await self._call_openai_vision(image_b64, media_type, prompt, settings)

    async def _call_anthropic_vision(
        self, image_b64: str, media_type: str, prompt: str, settings
    ) -> str:
        import httpx

        payload = {
            "model": settings.selected_ocr_model,
            "max_tokens": 4096,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.server_url.rstrip('/')}/messages",
                json=payload,
                headers={
                    "x-api-key": settings.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return "".join(
                b.get("text", "")
                for b in data.get("content", [])
                if b.get("type") == "text"
            )

    async def _call_openai_vision(
        self, image_b64: str, media_type: str, prompt: str, settings
    ) -> str:
        import httpx

        payload = {
            "model": settings.selected_ocr_model,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        headers = {}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.server_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_ollama_vision(
        self, image_b64: str, prompt: str, settings
    ) -> str:
        import httpx

        payload = {
            "model": settings.selected_ocr_model,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.server_url.rstrip('/')}/chat",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")


# ============ UI Components ============


def render_page(page: OcrPage) -> rx.Component:
    """Thumbnail + OCR result for one page."""
    return rx.hstack(
        # Thumbnail
        rx.box(
            rx.image(
                src=page["thumb_url"],
                max_width="280px",
                max_height="420px",
                object_fit="contain",
                border="1px solid var(--gray-5)",
                border_radius="4px",
            ),
            flex_shrink="0",
        ),
        # OCR text
        rx.box(
            rx.cond(
                page["result"] != "",
                rx.box(
                    rx.text(
                        page["result"],
                        size="2",
                        white_space="pre-wrap",
                        font_family="monospace",
                    ),
                    padding="12px",
                    background_color="var(--gray-2)",
                    border="1px solid var(--gray-5)",
                    border_radius="4px",
                    width="100%",
                    max_height="420px",
                    overflow_y="auto",
                ),
                rx.center(
                    rx.text("– noch nicht analysiert –", size="2", color="var(--gray-9)"),
                    padding="20px",
                ),
            ),
            flex="1",
            min_width="0",
        ),
        spacing="4",
        align="start",
        width="100%",
    )


def ocr_item_card(item: OcrItem) -> rx.Component:
    """Card for one uploaded file with header, status, and page results."""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.icon("file-image", size=16, color=HEADING_SECTION),
                rx.text(item["name"], size="2", weight="bold"),
                rx.cond(
                    item["pages"].length() > 1,
                    rx.badge(item["pages"].length(), " Seiten", color_scheme="gray", size="1"),
                ),
                # Status
                rx.cond(
                    item["status"] == "done",
                    rx.hstack(
                        rx.icon("circle-check", size=14, color="green"),
                        rx.text("Fertig", size="1", color="green"),
                        spacing="1", align="center",
                    ),
                    rx.cond(
                        item["status"] == "processing",
                        rx.hstack(
                            rx.spinner(size="2"),
                            rx.text("Analysiere...", size="1", color=HEADING_SECTION),
                            spacing="1", align="center",
                        ),
                        rx.cond(
                            item["status"] == "error",
                            rx.hstack(
                                rx.icon("circle-x", size=14, color="red"),
                                rx.text("Fehler", size="1", color="red"),
                                spacing="1", align="center",
                            ),
                            rx.badge("Bereit", color_scheme="gray", size="1"),
                        ),
                    ),
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("x", size=14),
                    on_click=OCRState.remove_item(item["_idx"]),
                    variant="ghost",
                    size="1",
                    color_scheme="gray",
                    disabled=OCRState.is_processing,
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            # Error message
            rx.cond(
                item["error"] != "",
                rx.callout(item["error"], icon="circle-x", color_scheme="red", size="1"),
            ),
            # Pages
            rx.cond(
                item["pages"].length() > 0,
                rx.vstack(
                    rx.foreach(item["pages"], render_page),
                    spacing="5",
                    width="100%",
                ),
            ),
            spacing="3",
            width="100%",
        ),
        padding="16px",
        border=PANEL_BORDER,
        border_radius="8px",
        background_color="var(--gray-1)",
        width="100%",
    )


def upload_section() -> rx.Component:
    """File drop zone."""
    return rx.vstack(
        section_heading("Dateien hochladen"),
        rx.upload(
            rx.vstack(
                rx.icon("upload", size=32, color="var(--gray-8)"),
                rx.text(
                    "JPG, PNG oder PDF hier ablegen",
                    size="3",
                    weight="bold",
                    color="var(--gray-11)",
                ),
                rx.text(
                    f"oder klicken zum Auswählen  ·  max. {MAX_FILES} Dateien  ·  max. {MAX_FILE_SIZE_MB} MB pro Datei",
                    size="1",
                    color="var(--gray-9)",
                ),
                align="center",
                spacing="2",
                padding="30px",
            ),
            id="ocr_upload",
            accept=ACCEPTED_TYPES,
            max_files=MAX_FILES,
            multiple=True,
            on_drop=OCRState.handle_upload(rx.upload_files(upload_id="ocr_upload")),
            border="2px dashed var(--gray-7)",
            border_radius="8px",
            cursor="pointer",
            width="100%",
            _hover={
                "border_color": "var(--accent-9)",
                "background_color": "var(--accent-2)",
            },
        ),
        spacing="3",
        width="100%",
    )


def controls_section() -> rx.Component:
    """Prompt editor and action buttons."""
    return rx.vstack(
        section_heading("OCR-Prompt"),
        rx.text(
            "Dieser Prompt wird mit jedem Bild an das LLM gesendet. "
            "Für spezialisierte Handschriften oder Fachsprache hier anpassen.",
            size="1",
            color=TEXT_MUTED,
        ),
        rx.el.textarea(
            value=OCRState.ocr_prompt,
            on_change=OCRState.set_ocr_prompt,
            rows=3,
            style={
                "width": "100%",
                "padding": "10px",
                "border": PANEL_BORDER,
                "border_radius": "5px",
                "resize": "vertical",
                "font_family": "inherit",
                "font_size": "13px",
            },
        ),
        rx.hstack(
            # Active LLM indicator
            rx.cond(
                LLMSettingsState.has_active_llm,
                rx.hstack(
                    rx.icon("circle-check", size=14, color="green"),
                    rx.text(LLMSettingsState.selected_ocr_model, size="2", color=TEXT_RESULT),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.icon("circle-x", size=14, color="red"),
                    rx.text("Kein LLM konfiguriert", size="2", color=COLOR_DANGER),
                    rx.text("·", size="2", color=TEXT_MUTED),
                    rx.link("→ Einstellungen", href="/settings", size="2"),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.spacer(),
            rx.button(
                rx.hstack(rx.icon("trash-2", size=14), rx.text("Alles löschen"), spacing="2"),
                on_click=OCRState.clear_all,
                variant="ghost",
                color_scheme="red",
                size="2",
                disabled=OCRState.is_processing | ~OCRState.has_items,
            ),
            rx.button(
                rx.cond(
                    OCRState.is_processing,
                    rx.hstack(rx.spinner(size="3"), rx.text("Analysiere..."), spacing="2"),
                    rx.hstack(rx.icon("scan-text", size=14), rx.text("OCR starten"), spacing="2"),
                ),
                on_click=OCRState.run_ocr,
                variant="solid",
                disabled=OCRState.is_processing | ~OCRState.any_ready,
                size="2",
            ),
            width="100%",
            align="center",
            spacing="3",
        ),
        error_callout(OCRState.error_message),
        spacing="3",
        width="100%",
    )


# ============ Page ============


def ocr_query_page() -> rx.Component:
    """Page layout for LLM-based OCR."""
    return base_layout(
        page_container(
            rx.vstack(
                page_heading("TEXTERKENNUNG (OCR)"),
                rx.callout(
                    rx.vstack(
                        rx.text(
                            "Für die Texterkennung wird ein multimodales (vision-fähiges) Sprachmodell benötigt.",
                            size="2",
                            weight="bold",
                        ),
                        rx.text(
                            "Geeignete Modelle: GPT-4o, Claude 3 / 3.5 / 3.7, LLaVA, Gemma 3, Pixtral, Qwen-VL …  "
                            "Das Modell wird unter LLM → Einstellungen ausgewählt.",
                            size="2",
                            color=TEXT_MUTED,
                        ),
                        spacing="1",
                    ),
                    icon="info",
                    color_scheme="blue",
                ),
                upload_section(),
                rx.cond(
                    OCRState.has_items,
                    rx.vstack(
                        controls_section(),
                        rx.divider(),
                        section_heading("Ergebnisse"),
                        rx.text(
                            OCRState.items_count,
                            " Datei(en)",
                            size="2",
                            color=HEADING_SECTION,
                            weight="bold",
                        ),
                        rx.foreach(OCRState.ocr_items_indexed, ocr_item_card),
                        spacing="4",
                        width="100%",
                    ),
                ),
                spacing="5",
            ),
        )
    )
