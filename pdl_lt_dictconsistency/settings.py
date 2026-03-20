import reflex as rx

from .components import (
    base_layout,
    page_heading,
    section_heading,
    HEADING_SECTION,
    TEXT_MUTED,
    PANEL_BORDER,
)


# ============ Settings State ============


class LLMSettingsState(rx.State):
    """State for LLM connection settings.

    Supports any OpenAI-compatible server (LM Studio, Ollama, vLLM, etc.)
    and the Anthropic API.
    """

    # --- Provider & connection ---
    provider: str = "Keine"  # "Keine", "LM Studio", "Ollama", "OpenAI-kompatibel", "Anthropic"
    server_url: str = ""
    api_key: str = ""

    # --- Model ---
    available_models: list[str] = []
    selected_model: str = ""
    model_context_length: int = 0  # Max context in tokens (0 = unknown)

    # --- OCR Model (separate selection for vision tasks) ---
    selected_ocr_model: str = ""
    ocr_model_context_length: int = 0

    # Backend var: model metadata from API (maps model id -> context length)
    _model_context_map: dict[str, int] = {}

    # --- Status ---
    connection_status: str = ""  # "connected", "error", ""
    status_message: str = ""
    is_checking: bool = False

    # ---- Setters ----

    def set_provider(self, value: str) -> None:
        """Update provider and set sensible defaults."""
        self.provider = value
        self.connection_status = ""
        self.status_message = ""
        self.available_models = []
        self.selected_model = ""
        self.model_context_length = 0
        self.selected_ocr_model = ""
        self.ocr_model_context_length = 0
        self._model_context_map = {}

        if value == "LM Studio":
            self.server_url = "http://127.0.0.1:1234/v1"
            self.api_key = "lm-studio"
        elif value == "Ollama":
            self.server_url = "http://localhost:11434/api"
            self.api_key = "ollama"
        elif value == "OpenAI-kompatibel":
            self.server_url = "https://api.openai.com/v1"
            self.api_key = ""
        elif value == "Anthropic":
            self.server_url = "https://api.anthropic.com/v1"
            self.api_key = ""
        else:
            self.server_url = ""
            self.api_key = ""

    def set_server_url(self, value: str) -> None:
        """Update server URL and reset status."""
        self.server_url = value
        self.connection_status = ""
        self.status_message = ""
        self.available_models = []
        self.selected_model = ""
        self.selected_ocr_model = ""

    def set_api_key(self, value: str) -> None:
        """Update API key."""
        self.api_key = value

    def set_selected_model(self, value: str) -> None:
        """Update selected model and its context length."""
        self.selected_model = value
        # Look up context length from discovered metadata
        self.model_context_length = self._model_context_map.get(value, 0)
        # Fallback for known providers if API didn't report context length
        if self.model_context_length == 0:
            self.model_context_length = self._fallback_context_length(value)

    def set_selected_ocr_model(self, value: str) -> None:
        """Update selected OCR model and its context length."""
        self.selected_ocr_model = value
        self.ocr_model_context_length = self._model_context_map.get(value, 0)
        if self.ocr_model_context_length == 0:
            self.ocr_model_context_length = self._fallback_context_length(value)

    # ---- Connection test ----

    @rx.event
    async def check_connection(self):
        """Test connection and discover available models."""
        import httpx

        self.is_checking = True
        self.connection_status = ""
        self.status_message = ""
        self.available_models = []
        yield

        if not self.server_url:
            self.connection_status = "error"
            self.status_message = "Bitte Server-URL angeben."
            self.is_checking = False
            return

        is_local = self.provider in ("LM Studio", "Ollama")
        if not is_local and not self.api_key:
            self.connection_status = "error"
            self.status_message = "Bitte API-Schlüssel angeben."
            self.is_checking = False
            return

        try:
            headers = {}
            if self.api_key and self.provider == "Anthropic":
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                }
            elif self.api_key:
                headers = {"Authorization": f"Bearer {self.api_key}"}

            async with httpx.AsyncClient(timeout=15.0) as client:
                base = self.server_url.rstrip("/")

                if self.provider == "Ollama":
                    resp = await client.get(f"{base}/tags", headers=headers)
                else:
                    resp = await client.get(f"{base}/models", headers=headers)

                if resp.status_code == 200:
                    models = self._parse_models_response(resp.json())
                    self.available_models = sorted(models)
                    self.connection_status = "connected"

                    if models:
                        self.status_message = (
                            f"Verbunden – {len(models)} Modell(e) verfügbar"
                        )
                        if not self.selected_model:
                            first = sorted(models)[0]
                            self.selected_model = first
                            self.model_context_length = (
                                self._model_context_map.get(first, 0)
                                or self._fallback_context_length(first)
                            )
                        if not self.selected_ocr_model:
                            # Pre-select second model for OCR if available, else same as text
                            sorted_models = sorted(models)
                            ocr_default = sorted_models[1] if len(sorted_models) > 1 else sorted_models[0]
                            self.selected_ocr_model = ocr_default
                            self.ocr_model_context_length = (
                                self._model_context_map.get(ocr_default, 0)
                                or self._fallback_context_length(ocr_default)
                            )
                    else:
                        self.status_message = (
                            "Verbunden, aber keine Modelle gefunden."
                        )
                elif resp.status_code == 401:
                    self.connection_status = "error"
                    self.status_message = (
                        "Authentifizierung fehlgeschlagen. API-Schlüssel prüfen."
                    )
                else:
                    self.connection_status = "error"
                    self.status_message = (
                        f"Unerwartete Antwort (Status {resp.status_code})."
                    )

        except httpx.ConnectError:
            self.connection_status = "error"
            self.status_message = (
                f"Keine Verbindung zu {self.server_url}. "
                "Ist der Server gestartet?"
            )
        except httpx.TimeoutException:
            self.connection_status = "error"
            self.status_message = "Zeitüberschreitung."
        except Exception as e:
            self.connection_status = "error"
            self.status_message = f"Fehler: {str(e)}"
        finally:
            self.is_checking = False

    def _parse_models_response(self, data: dict) -> list[str]:
        """Extract model IDs and context lengths from API response."""
        models = []
        context_map = {}
        # OpenAI / LM Studio: {"data": [{"id": "...", "max_context_length": ...}]}
        if "data" in data:
            for m in data["data"]:
                mid = m.get("id", "")
                if mid:
                    models.append(mid)
                    # LM Studio provides max_context_length or loaded_context_length
                    ctx = m.get("loaded_context_length") or m.get("max_context_length", 0)
                    if ctx:
                        context_map[mid] = int(ctx)
        # Ollama: {"models": [{"name": "...", ...}]}
        elif "models" in data:
            for m in data["models"]:
                name = m.get("name", "")
                if name:
                    models.append(name)
        self._model_context_map = context_map
        return models

    @staticmethod
    def _fallback_context_length(model_name: str) -> int:
        """Estimate context length for known models when API doesn't report it."""
        name = model_name.lower()
        # Known context lengths for popular model families
        if "gpt-4o" in name or "gpt-4" in name:
            return 128_000
        if "gpt-3.5" in name:
            return 16_385
        if "gpt-5" in name:
            return 128_000
        if "claude" in name:
            return 200_000
        if "mistral" in name and "small" in name:
            return 128_000
        if "mistral" in name and "large" in name:
            return 128_000
        if "mistral" in name:
            return 32_000
        if "qwen" in name:
            return 128_000
        if "llama" in name and "70b" in name:
            return 128_000
        if "llama" in name:
            return 128_000
        if "gemma" in name:
            return 128_000
        # Conservative default
        return 32_000

    # ---- Computed vars ----

    @rx.var
    def active_model_display(self) -> str:
        """Human-readable LLM description for sidebar and other pages."""
        if self.connection_status == "connected" and self.selected_model:
            return self.selected_model
        if self.provider != "Keine":
            return f"{self.provider} (nicht verbunden)"
        return "Kein LLM konfiguriert"

    @rx.var
    def context_length_display(self) -> str:
        """Human-readable context length for the selected model."""
        if self.model_context_length > 0:
            return f"{self.model_context_length:,}".replace(",", ".")
        return "?"

    @rx.var
    def has_active_llm(self) -> bool:
        """Check if an LLM is configured and ready."""
        return (
            self.connection_status == "connected"
            and bool(self.selected_model)
        )

    @rx.var
    def is_local(self) -> bool:
        """Check if using a local server (no API key required)."""
        return self.provider in ("LM Studio", "Ollama")


# ============ Status Indicator ============


def status_badge(status: rx.Var[str], message: rx.Var[str]) -> rx.Component:
    """Colored status indicator with message."""
    return rx.cond(
        status != "",
        rx.hstack(
            rx.cond(
                status == "connected",
                rx.icon("circle-check", size=16, color="green"),
                rx.icon("circle-x", size=16, color="red"),
            ),
            rx.text(message, size="2"),
            spacing="2",
            align="center",
        ),
    )


# ============ Connection Section ============


def connection_settings_section() -> rx.Component:
    """Unified LLM connection configuration."""
    return rx.vstack(
        section_heading("LLM-Verbindung", margin_top="0px"),
        rx.text(
            "Verbinden Sie ein lokales oder cloudbasiertes Sprachmodell. "
            "Unterstützt werden LM Studio, Ollama, OpenAI-kompatible Server "
            "und die Anthropic-API.",
            size="2",
            color=TEXT_MUTED,
            style={"font_style": "italic"},
        ),
        # Provider selection
        rx.text("Anbieter:", size="2", weight="bold", margin_top="10px"),
        rx.select(
            ["Keine", "LM Studio", "Ollama", "OpenAI-kompatibel", "Anthropic"],
            value=LLMSettingsState.provider,
            on_change=LLMSettingsState.set_provider,
            width="100%",
        ),
        # Configuration (only when provider selected)
        rx.cond(
            LLMSettingsState.provider != "Keine",
            rx.vstack(
                # Server URL
                rx.text("Server-URL:", size="2", weight="bold"),
                rx.input(
                    value=LLMSettingsState.server_url,
                    placeholder="http://127.0.0.1:1234/api/v1",
                    on_change=LLMSettingsState.set_server_url,
                    width="100%",
                ),
                # API Key
                rx.text(
                    rx.cond(
                        LLMSettingsState.is_local,
                        "API-Schlüssel (optional für lokale Server):",
                        "API-Schlüssel:",
                    ),
                    size="2",
                    weight="bold",
                ),
                rx.input(
                    value=LLMSettingsState.api_key,
                    placeholder=rx.cond(
                        LLMSettingsState.is_local,
                        "beliebiger Wert",
                        "sk-...",
                    ),
                    on_change=LLMSettingsState.set_api_key,
                    type="password",
                    width="100%",
                ),
                # Test button
                rx.button(
                    rx.cond(
                        LLMSettingsState.is_checking,
                        rx.hstack(
                            rx.spinner(size="3"),
                            rx.text("Prüfe..."),
                            spacing="2",
                        ),
                        rx.text("Verbindung testen"),
                    ),
                    on_click=LLMSettingsState.check_connection,
                    variant="solid",
                    disabled=LLMSettingsState.is_checking,
                ),
                # Status
                status_badge(
                    LLMSettingsState.connection_status,
                    LLMSettingsState.status_message,
                ),
                # Model selection (only after successful connection)
                rx.cond(
                    LLMSettingsState.connection_status == "connected",
                    rx.vstack(
                        rx.text("Modell (Text / Chat):", size="2", weight="bold"),
                        rx.cond(
                            LLMSettingsState.available_models.length() > 0,
                            rx.select(
                                LLMSettingsState.available_models,
                                value=LLMSettingsState.selected_model,
                                on_change=LLMSettingsState.set_selected_model,
                                width="100%",
                            ),
                            rx.input(
                                value=LLMSettingsState.selected_model,
                                placeholder="Modellname eingeben...",
                                on_change=LLMSettingsState.set_selected_model,
                                width="100%",
                            ),
                        ),
                        rx.text("Modell (OCR / Bilderkennung):", size="2", weight="bold"),
                        rx.cond(
                            LLMSettingsState.available_models.length() > 0,
                            rx.select(
                                LLMSettingsState.available_models,
                                value=LLMSettingsState.selected_ocr_model,
                                on_change=LLMSettingsState.set_selected_ocr_model,
                                width="100%",
                            ),
                            rx.input(
                                value=LLMSettingsState.selected_ocr_model,
                                placeholder="Modellname eingeben...",
                                on_change=LLMSettingsState.set_selected_ocr_model,
                                width="100%",
                            ),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                # Active status summary
                rx.cond(
                    LLMSettingsState.has_active_llm,
                    rx.callout(
                        rx.vstack(
                            rx.text(
                                "Text/Chat: ",
                                rx.text.strong(LLMSettingsState.selected_model),
                                " (Kontext: ",
                                LLMSettingsState.context_length_display,
                                " Tokens)",
                            ),
                            rx.text(
                                "OCR: ",
                                rx.text.strong(LLMSettingsState.selected_ocr_model),
                            ),
                            spacing="1",
                        ),
                        icon="check",
                        color_scheme="green",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
        ),
        spacing="3",
        width="100%",
        padding="15px",
        border=PANEL_BORDER,
        border_radius="5px",
    )


# ============ Page ============


def settings_page() -> rx.Component:
    """Page layout for LLM settings."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("EINSTELLUNGEN"),
                rx.text(
                    "Konfigurieren Sie hier die Verbindung zu einem Sprachmodell (LLM). "
                    "Ein LLM kann für erweiterte Konsistenzprüfungen und Textanalysen "
                    "verwendet werden.",
                ),
                connection_settings_section(),
                spacing="5",
            ),
        )
    )
