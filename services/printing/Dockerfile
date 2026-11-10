FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PRINT_SPOOL_DIR=/data
WORKDIR /service
RUN apt-get update && apt-get install -y --no-install-recommends libusb-1.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py printer.py tests.py ./
EXPOSE 8080
CMD ["python", "server.py"]
