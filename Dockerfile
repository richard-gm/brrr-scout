FROM python:3.12-slim

# System deps for Playwright/Chromium (used by crawl4ai)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Playwright browsers needed by crawl4ai
RUN crawl4ai-setup || python -m playwright install chromium --with-deps

# Copy application code
COPY . .

# Ensure data directories exist
RUN mkdir -p data/inbox data/packs

EXPOSE 5000

# Optional env vars (set at runtime):
#   ANTHROPIC_API_KEY   — enables floorplan + legal pack AI analysis
#   SCRAPER_PROXY_URL   — e.g. http://scraperapi:<key>@proxy-server.scraperapi.com:8001
#                         Routes crawl4ai + requests through a residential proxy;
#                         greatly improves live scraping success rate.
CMD ["python", "app.py"]
