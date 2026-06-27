FROM python:3.12-slim

WORKDIR /app

# Install build dependencies and project
COPY pyproject.toml README.md ./
COPY requirements.txt constraints.txt ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt && \
    pip install --no-cache-dir .

# Copy runtime assets
COPY web ./web
COPY data ./data
COPY migrations ./migrations
COPY alembic.ini ./

# Create a non-root user
RUN useradd -m -u 1000 marketedge && chown -R marketedge:marketedge /app
USER marketedge

# Default to showing help
ENTRYPOINT ["marketedge"]
CMD ["--help"]
