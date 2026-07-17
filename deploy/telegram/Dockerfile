FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd --system --create-home --uid 10001 knowledge-builder \
    && chown -R knowledge-builder:knowledge-builder /app
USER knowledge-builder

CMD ["python", "telegram_bot.py"]
