FROM python:3.13-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir fastapi uvicorn httpx firebase-admin pydantic

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "cloud_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
