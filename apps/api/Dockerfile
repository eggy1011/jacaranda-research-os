FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system jacaranda && adduser --system --ingroup jacaranda jacaranda

COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/src ./src
COPY PROJECT_BRIEF.md ./PROJECT_BRIEF.md
COPY packages ./packages
COPY assets/brand ./assets/brand
RUN pip install --no-cache-dir .

USER jacaranda

EXPOSE 8000

CMD ["uvicorn", "jacaranda_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
