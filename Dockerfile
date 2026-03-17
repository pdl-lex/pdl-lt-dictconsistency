FROM python:3.13-slim

WORKDIR /app

# uv installieren
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# System dependencies für Reflex
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies kopieren
COPY pyproject.toml uv.lock* ./

# Dependencies installieren
RUN uv sync --frozen

# App-Code kopieren
COPY . .

# Reflex initialisieren
RUN uv run reflex init

# Fix vaul SSR bug: document is not defined during prerender
RUN sed -i 's/document\.body/typeof document !== "undefined" \&\& document.body/g' \
    /app/.web/node_modules/vaul/dist/index.mjs

# Ports exposen
EXPOSE 3000
EXPOSE 8000

# Production mode
ENV REFLEX_ENV=prod

# App starten
CMD ["uv", "run", "reflex", "run", "--env", "prod"]