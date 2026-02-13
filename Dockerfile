FROM python:3.11-slim

LABEL maintainer="Lucía Cabanillas Rodríguez"
LABEL version="0.1.0"

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# Install Poetry
RUN pip install "poetry>=1.8" && \
    poetry install --no-root

# Copy application code
COPY ./app /app/app
RUN mkdir -p /app/policies/yang /app/policies/rego

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

