FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv --no-cache-dir

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy source, extensions, config, and samples
COPY src/ ./src/
COPY extensions/ ./extensions/
COPY config/ ./config/
COPY samples/ ./samples/

# Create output directory
RUN mkdir -p output

EXPOSE 8000

# Default: web server
CMD ["uv", "run", "logforge", "serve", "--host", "0.0.0.0", "--port", "8000"]
