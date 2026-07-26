FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Formal PDF output (milestone 4): headless LibreOffice + CJK fonts so the
# Chinese edition renders correctly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-impress fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system jacaranda && adduser --system --ingroup jacaranda jacaranda

COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
COPY PROJECT_BRIEF.md ./PROJECT_BRIEF.md
COPY packages ./packages
COPY assets/brand ./assets/brand
RUN pip install --no-cache-dir ".[live]"

RUN mkdir -p /data && chown jacaranda:jacaranda /data

USER jacaranda

EXPOSE 8000

CMD ["uvicorn", "jacaranda_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
