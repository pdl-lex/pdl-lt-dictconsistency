import reflex as rx
from pathlib import Path

from .state import FileState
from .settings import LLMSettingsState
from .components import (
    base_layout,
    page_heading,
    section_heading,
    no_files_warning,
    error_callout,
    HEADING_SECTION,
    TEXT_MUTED,
    TEXT_RESULT,
    PANEL_BORDER,
    PANEL_PADDING,
    COLOR_DANGER,
)


# ============ Constants ============

# Rough estimate: 1 token ≈ 4 chars for European languages
CHARS_PER_TOKEN = 4

# Reserve tokens for system prompt + LLM response
RESPONSE_RESERVE_TOKENS = 4_096
# Fraction of context to use as warning threshold
WARN_THRESHOLD = 0.75


# ============ File Selection Column Defs ============

LLM_FILE_COLUMN_DEFS = [
    {
        "field": "filename",
        "headerName": "Dateiname",
        "sortable": True,
        "filter": True,
        "checkboxSelection": True,
        "headerCheckboxSelection": True,
    },
    {
        "field": "subdir",
        "headerName": "Unterverzeichnis",
        "sortable": True,
        "filter": True,
    },
    {
        "field": "size_kb",
        "headerName": "Größe (KB)",
        "sortable": True,
        "filter": True,
    },
]


# ============ State ============


class LLMQueryState(rx.State):
    """State for LLM query page: file selection, chat, and LLM communication."""

    # File selection
    selected_files: list[dict] = []

    # Display history: shown in the chat UI (compact, no file dumps)
    chat_messages: list[dict] = []

    # Backend var: full API history including file context (not shown in UI)
    _api_messages: list[dict] = []

    # Current input
    user_input: str = ""

    # Status
    is_sending: bool = False
    error_message: str = ""

    # Token tracking
    _selected_files_char_count: int = 0
    tokens_used_last: int = 0       # Tokens used in last API call (from usage)
    tokens_used_total: int = 0      # Total tokens used in current history

    # System prompt
    system_prompt: str = (
        "Du bist ein Assistent für die Analyse von Wörterbuch-XML-Dateien "
        "(TEI-Lex 0 Format). Du hilfst bei der Konsistenzprüfung, "
        "Fehlersuche und linguistischen Analyse der Wörterbucheinträge. "
        "Antworte auf Deutsch, es sei denn, der Benutzer fragt auf einer "
        "anderen Sprache."
    )

    # Backend var: cached directory for file reading
    _directory_path: str = ""

    def set_user_input(self, value: str) -> None:
        """Update user input field."""
        self.user_input = value

    def set_system_prompt(self, value: str) -> None:
        """Update system prompt."""
        self.system_prompt = value

    async def handle_file_selection(self, rows: list[dict], _a, _b) -> None:
        """Handle AG Grid row selection changes (multi-select with checkboxes)."""
        self.selected_files = rows
        # Estimate character count for token budget display
        file_state = await self.get_state(FileState)
        base_path = Path(file_state.directory_path)
        total_chars = 0
        for row in rows:
            try:
                subdir = row.get("subdir", ".")
                filename = row.get("filename", "")
                if subdir and subdir != ".":
                    file_path = base_path / subdir / filename
                else:
                    file_path = base_path / filename
                if file_path.exists():
                    total_chars += file_path.stat().st_size
            except Exception:
                continue
        self._selected_files_char_count = total_chars

    @rx.var
    def selected_file_count(self) -> int:
        """Number of selected files."""
        return len(self.selected_files)

    @rx.var
    def estimated_file_tokens(self) -> int:
        """Rough token estimate for selected files."""
        return self._selected_files_char_count // CHARS_PER_TOKEN

    @rx.var
    def context_budget(self) -> int:
        """Available token budget (model context - response reserve)."""
        from .settings import LLMSettingsState
        # Can't await get_state in computed var, so we access via substates
        # For now use a reasonable default; real value comes from settings
        # This is recalculated in the template using LLMSettingsState directly
        return 0  # placeholder, actual display uses LLMSettingsState.model_context_length

    @rx.var
    def token_budget_display(self) -> str:
        """Human-readable token budget display."""
        file_est = self._selected_files_char_count // CHARS_PER_TOKEN
        history_est = self.tokens_used_total

        if file_est == 0 and history_est == 0:
            return "Keine Dateien ausgewählt"

        parts = []
        if file_est > 0:
            parts.append(f"Dateien: ~{file_est:,}".replace(",", "."))
        if history_est > 0:
            parts.append(f"Verlauf: {history_est:,}".replace(",", "."))

        return " + ".join(parts) + " Tokens"

    @rx.var
    def total_estimated_tokens(self) -> int:
        """Total estimated tokens: files + history."""
        return (self._selected_files_char_count // CHARS_PER_TOKEN) + self.tokens_used_total

    @rx.var
    def has_messages(self) -> bool:
        """Check if chat has any messages."""
        return len(self.chat_messages) > 0

    async def _read_selected_files(self) -> str:
        """Read content of selected files and format as context block."""
        file_state = await self.get_state(FileState)
        base_path = Path(file_state.directory_path)
        parts = []

        for row in self.selected_files:
            subdir = row.get("subdir", ".")
            filename = row.get("filename", "")
            if subdir and subdir != ".":
                file_path = base_path / subdir / filename
            else:
                file_path = base_path / filename

            try:
                content = file_path.read_text(encoding="utf-8")
                parts.append(
                    f'<file name="{filename}" path="{subdir}/{filename}">\n'
                    f"{content}\n"
                    f"</file>"
                )
            except Exception as e:
                parts.append(
                    f'<file name="{filename}" error="true">\n'
                    f"Fehler beim Lesen: {e}\n"
                    f"</file>"
                )

        if not parts:
            return ""

        return (
            "<context>\n"
            "Die folgenden XML-Dateien wurden vom Benutzer ausgewählt:\n\n"
            + "\n\n".join(parts)
            + "\n</context>"
        )

    def _build_messages_for_api(
        self, user_message: str, file_context: str
    ) -> list[dict]:
        """Build the messages array for the LLM API call.

        Uses _api_messages as history (contains full file context from earlier turns).
        Only adds file context to the current message if files are selected AND
        this is the first message or the file selection changed.
        """
        messages = []

        # System prompt
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Full API history from previous turns (already contains file contexts)
        for msg in self._api_messages:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Current user message with file context
        if file_context:
            full_user_message = f"{file_context}\n\n{user_message}"
        else:
            full_user_message = user_message

        messages.append({"role": "user", "content": full_user_message})

        return messages, full_user_message

    async def _call_llm(self, messages: list[dict]) -> tuple[str, int]:
        """Route to the correct LLM backend. Returns (response_text, total_tokens)."""
        settings = await self.get_state(LLMSettingsState)

        if settings.provider == "Anthropic":
            return await self._call_anthropic(messages, settings)
        elif settings.provider == "Ollama":
            return await self._call_ollama(messages, settings)
        else:
            return await self._call_openai_compatible(messages, settings)

    async def _call_openai_compatible(
        self, messages: list[dict], settings
    ) -> tuple[str, int]:
        """Call an OpenAI-compatible chat completions endpoint.
        Returns (response_text, total_tokens)."""
        import httpx

        url = f"{settings.server_url.rstrip('/')}/chat/completions"

        payload = {
            "model": settings.selected_model,
            "messages": messages,
        }

        headers = {}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            total_tokens = data.get("usage", {}).get("total_tokens", 0)
            return text, total_tokens

    async def _call_ollama(self, messages: list[dict], settings) -> tuple[str, int]:
        """Call the Ollama-native chat endpoint.
        Returns (response_text, total_tokens)."""
        import httpx

        url = f"{settings.server_url.rstrip('/')}/chat"

        payload = {
            "model": settings.selected_model,
            "messages": messages,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("message", {}).get("content", "")
            # Ollama: prompt_eval_count + eval_count
            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)
            return text, prompt_tokens + completion_tokens

    async def _call_anthropic(self, messages: list[dict], settings) -> tuple[str, int]:
        """Call the Anthropic messages API.
        Returns (response_text, total_tokens)."""
        import httpx

        url = f"{settings.server_url.rstrip('/')}/messages"

        system_text = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                api_messages.append(msg)

        payload = {
            "model": settings.selected_model,
            "max_tokens": 4096,
            "messages": api_messages,
        }
        if system_text:
            payload["system"] = system_text

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "x-api-key": settings.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
            content_blocks = data.get("content", [])
            text = "".join(
                block.get("text", "") for block in content_blocks
                if block.get("type") == "text"
            )
            usage = data.get("usage", {})
            total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            return text, total_tokens

    @rx.event
    async def handle_key_down(self, key: str) -> None:
        """Send message on Enter (without Shift)."""
        if key == "Enter":
            return LLMQueryState.send_message

    @rx.event
    async def send_message(self) -> None:
        """Send user message to LLM with selected file context."""
        if not self.user_input.strip():
            return

        settings = await self.get_state(LLMSettingsState)

        # Check LLM is configured
        llm_active = (
            settings.connection_status == "connected"
            and bool(settings.selected_model)
        )

        if not llm_active:
            self.error_message = (
                "Kein LLM konfiguriert. Bitte unter 'Einstellungen' eine "
                "Verbindung einrichten."
            )
            return

        user_text = self.user_input.strip()
        self.user_input = ""
        self.error_message = ""
        self.is_sending = True

        # Add user message to display chat (compact, no file dump)
        display_msg = user_text
        if self.selected_files:
            filenames = [f.get("filename", "?") for f in self.selected_files]
            if len(filenames) <= 3:
                file_hint = ", ".join(filenames)
            else:
                file_hint = f"{', '.join(filenames[:3])} (+{len(filenames)-3})"
            display_msg = f"[{file_hint}]\n{user_text}"

        self.chat_messages = self.chat_messages + [
            {"role": "user", "content": display_msg}
        ]
        yield

        try:
            # Read file contents
            file_context = await self._read_selected_files()

            # Build API messages (includes full history + file context)
            messages, full_user_msg = self._build_messages_for_api(
                user_text, file_context
            )

            # Call LLM (auto-routes to correct backend)
            response_text, total_tokens = await self._call_llm(messages)

            # Track token usage
            if total_tokens > 0:
                self.tokens_used_last = total_tokens
                self.tokens_used_total = total_tokens  # total_tokens includes full history

            # Store in API history (full content for future context)
            self._api_messages = self._api_messages + [
                {"role": "user", "content": full_user_msg},
                {"role": "assistant", "content": response_text},
            ]

            # Store in display chat (shown in UI)
            self.chat_messages = self.chat_messages + [
                {"role": "assistant", "content": response_text}
            ]

        except Exception as e:
            error_str = str(e)
            # Provide helpful error messages
            if "ConnectError" in error_str or "Connection" in error_str:
                self.error_message = (
                    "Verbindung zum LLM fehlgeschlagen. "
                    "Ist der Server gestartet?"
                )
            elif "404" in error_str:
                self.error_message = (
                    "Modell nicht gefunden. Bitte in den Einstellungen prüfen."
                )
            elif "timeout" in error_str.lower():
                self.error_message = (
                    "Zeitüberschreitung. Die Anfrage war möglicherweise zu groß."
                )
            else:
                self.error_message = f"LLM-Fehler: {error_str}"
        finally:
            self.is_sending = False

    def clear_chat(self) -> None:
        """Clear chat history (both display and API)."""
        self.chat_messages = []
        self._api_messages = []
        self.tokens_used_last = 0
        self.tokens_used_total = 0
        self.error_message = ""


# ============ UI Components ============


def file_selection_section() -> rx.Component:
    """AG Grid with multi-select checkboxes for file selection."""
    from pdl_lt_reflex_aggrid_wrapper import ag_grid

    return rx.vstack(
        section_heading("Dateiauswahl", margin_top="0px"),
        rx.text(
            "Wählen Sie die XML-Dateien aus, die als Kontext an das LLM "
            "gesendet werden sollen:",
            size="2",
            color=TEXT_MUTED,
            style={"font_style": "italic"},
        ),
        # Token budget indicator
        rx.hstack(
            rx.icon("file-text", size=14, color=HEADING_SECTION),
            rx.text(
                LLMQueryState.selected_file_count,
                " Datei(en) ausgewählt",
                size="2",
                weight="bold",
            ),
            rx.text("  ·  ", size="2", color=TEXT_MUTED),
            rx.icon("coins", size=14, color=HEADING_SECTION),
            rx.text(
                LLMQueryState.token_budget_display,
                size="2",
            ),
            rx.text("  ·  ", size="2", color=TEXT_MUTED),
            rx.text(
                "Kontext: ",
                LLMSettingsState.context_length_display,
                " Tokens",
                size="2",
                color=TEXT_MUTED,
            ),
            spacing="2",
            align="center",
        ),
        # Over-budget warning (total estimated > model context - reserve)
        rx.cond(
            (LLMSettingsState.model_context_length > 0)
            & (
                LLMQueryState.total_estimated_tokens
                > (LLMSettingsState.model_context_length - RESPONSE_RESERVE_TOKENS)
            ),
            rx.callout(
                "Die geschätzte Token-Anzahl (Dateien + Verlauf) überschreitet "
                "das Kontextfenster des Modells. Bitte reduzieren Sie die Auswahl "
                "oder leeren Sie den Chat-Verlauf.",
                icon="triangle-alert",
                color_scheme="red",
            ),
        ),
        rx.cond(
            (LLMSettingsState.model_context_length > 0)
            & (
                LLMQueryState.total_estimated_tokens
                > (LLMSettingsState.model_context_length * WARN_THRESHOLD)
            )
            & (
                LLMQueryState.total_estimated_tokens
                <= (LLMSettingsState.model_context_length - RESPONSE_RESERVE_TOKENS)
            ),
            rx.callout(
                "Die Auswahl nähert sich dem Kontext-Limit des Modells.",
                icon="info",
                color_scheme="orange",
            ),
        ),
        # File grid
        ag_grid(
            id="llm_file_select_grid",
            row_data=FileState.xml_files_data,
            column_defs=LLM_FILE_COLUMN_DEFS,
            default_col_def={"flex": 1, "minWidth": 50},
            pagination=True,
            pagination_page_size=15,
            pagination_page_size_selector=[10, 15, 25, 50, 100],
            resizable=True,
            dom_layout="autoHeight",
            height="None",
            column_size="sizeToFit",
            row_selection={"mode": "multiRow"},
            on_selection_changed=LLMQueryState.handle_file_selection,
        ),
        spacing="3",
        width="100%",
    )


def chat_message_bubble(msg: dict) -> rx.Component:
    """Render a single chat message bubble."""
    is_user = msg["role"] == "user"

    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon(
                    rx.cond(is_user, "user", "bot"),
                    size=14,
                    color=rx.cond(is_user, HEADING_SECTION, "green"),
                ),
                rx.text(
                    rx.cond(is_user, "Sie", "LLM"),
                    size="1",
                    weight="bold",
                    color=rx.cond(is_user, HEADING_SECTION, "green"),
                ),
                spacing="1",
                align="center",
            ),
            rx.markdown(
                msg["content"],
                size="2",
            ),
            spacing="1",
            width="100%",
        ),
        padding="12px",
        border_radius="8px",
        background_color=rx.cond(
            is_user,
            "var(--accent-3)",
            "var(--gray-3)",
        ),
        width="100%",
    )


def chat_section() -> rx.Component:
    """Chat interface with message history and input."""
    return rx.vstack(
        section_heading("Chat"),
        # Active LLM display
        rx.hstack(
            rx.cond(
                LLMSettingsState.has_active_llm,
                rx.hstack(
                    rx.icon("circle-check", size=14, color="green"),
                    rx.text(
                        LLMSettingsState.active_model_display,
                        size="2",
                        color=TEXT_RESULT,
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.icon("circle-x", size=14, color="red"),
                    rx.text(
                        "Kein LLM konfiguriert",
                        size="2",
                        color=COLOR_DANGER,
                    ),
                    rx.link(
                        "→ Einstellungen",
                        href="/settings",
                        size="2",
                    ),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.spacer(),
            rx.cond(
                LLMQueryState.has_messages,
                rx.button(
                    rx.hstack(
                        rx.icon("trash-2", size=14),
                        rx.text("Chat leeren"),
                        spacing="2",
                    ),
                    on_click=LLMQueryState.clear_chat,
                    variant="ghost",
                    size="1",
                    color_scheme="red",
                ),
            ),
            width="100%",
            align="center",
        ),
        # Error display
        error_callout(LLMQueryState.error_message),
        # Message history
        rx.box(
            rx.cond(
                LLMQueryState.has_messages,
                rx.vstack(
                    rx.foreach(
                        LLMQueryState.chat_messages,
                        chat_message_bubble,
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("message-square-plus", size=32, color="var(--gray-7)"),
                        rx.text(
                            "Stellen Sie eine Frage zu den ausgewählten Dateien...",
                            size="2",
                            color=TEXT_MUTED,
                        ),
                        align="center",
                        spacing="2",
                    ),
                    padding="40px",
                ),
            ),
            width="100%",
            max_height="500px",
            overflow_y="auto",
            padding="10px",
            border=PANEL_BORDER,
            border_radius="5px",
            background_color="var(--gray-2)",
        ),
        # Sending indicator
        rx.cond(
            LLMQueryState.is_sending,
            rx.hstack(
                rx.spinner(size="3"),
                rx.text("LLM verarbeitet Anfrage...", size="2", color=TEXT_MUTED),
                spacing="2",
                align="center",
            ),
        ),
        # Input area
        rx.hstack(
            rx.el.textarea(
                value=LLMQueryState.user_input,
                placeholder="Ihre Frage eingeben... (Enter zum Senden)",
                on_change=LLMQueryState.set_user_input,
                on_key_down=LLMQueryState.handle_key_down,
                disabled=LLMQueryState.is_sending,
                rows=3,
                style={
                    "width": "100%",
                    "padding": "10px",
                    "border": PANEL_BORDER,
                    "border_radius": "5px",
                    "resize": "vertical",
                    "font_family": "inherit",
                    "font_size": "14px",
                },
            ),
            rx.vstack(
                rx.button(
                    rx.icon("send", size=16),
                    on_click=LLMQueryState.send_message,
                    variant="solid",
                    disabled=LLMQueryState.is_sending,
                    size="3",
                ),
                spacing="2",
            ),
            width="100%",
            align="end",
            spacing="2",
        ),
        spacing="3",
        width="100%",
    )


def system_prompt_section() -> rx.Component:
    """Collapsible system prompt editor using accordion."""
    return rx.accordion.root(
        rx.accordion.item(
            header="System-Prompt anpassen",
            content=rx.vstack(
                rx.text(
                    "Der System-Prompt gibt dem LLM den Kontext für seine Rolle. "
                    "Er wird bei jeder Anfrage mitgesendet.",
                    size="2",
                    color=TEXT_MUTED,
                    style={"font_style": "italic"},
                ),
                rx.el.textarea(
                    value=LLMQueryState.system_prompt,
                    on_change=LLMQueryState.set_system_prompt,
                    rows=4,
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
                spacing="2",
                width="100%",
            ),
        ),
        collapsible=True,
        width="100%",
    )


# ============ Page ============


def llm_query_page() -> rx.Component:
    """Page layout for LLM query interface."""
    return base_layout(
        rx.container(
            rx.vstack(
                page_heading("LLM-ANFRAGE"),
                rx.text(
                    "Stellen Sie Fragen zu Ihren XML-Dateien mithilfe eines "
                    "Sprachmodells. Wählen Sie Dateien aus, die als Kontext "
                    "mitgesendet werden sollen.",
                ),
                no_files_warning(),
                rx.cond(
                    FileState.has_files,
                    rx.vstack(
                        file_selection_section(),
                        system_prompt_section(),
                        chat_section(),
                        spacing="4",
                        width="100%",
                    ),
                ),
                spacing="4",
            ),
        )
    )
