FROM python:3.12-slim

# System deps required by Playwright's headless Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Playwright's Chromium at build time so first scan is instant
RUN crawl4ai-setup || python -m playwright install chromium --with-deps

COPY . .

RUN mkdir -p data/inbox data/packs data/cookies

EXPOSE 5000

# Environment variables (all optional):
#
#   ANTHROPIC_API_KEY       — enables AI deal verdict, floorplan + legal pack analysis
#   EPC_API_EMAIL / KEY     — free EPC data (register at epc.opendatacommunities.org)
#   SCRAPER_PROXY_URL       — residential proxy, e.g. ScraperAPI (optional)
#
# All env vars can be set in .env (copy from .env.example)
# Cookie files: mount data/ with -v $(pwd)/data:/app/data
# See docs/CLAUDE.md for the AI analysis contract.

CMD ["python", "wsgi.py"]
