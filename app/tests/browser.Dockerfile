FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && pip install --no-cache-dir playwright==1.65.0 \
    && playwright install --with-deps --only-shell chromium
WORKDIR /tests
CMD ["python", "products_browser.py"]
