# How to export your browser cookies to BRRR Scout

This lets the scraper impersonate your real browser session, bypassing
Rightmove and Zoopla bot detection entirely. One-time setup, ~2 minutes.

## Step 1 — Install Cookie-Editor (free, open source)
- Chrome / Edge: https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm
- Firefox:       https://addons.mozilla.org/en-GB/firefox/addon/cookie-editor/

## Step 2 — Export Rightmove cookies
1. Go to https://www.rightmove.co.uk and browse any page (log in if you have an account)
2. Click the Cookie-Editor icon in your browser toolbar
3. Click **Export** → **Export as JSON**
4. Save the file as `data/cookies/rightmove.json`

## Step 3 — Export Zoopla cookies
1. Go to https://www.zoopla.co.uk and browse any page
2. Click Cookie-Editor → **Export** → **Export as JSON**
3. Save the file as `data/cookies/zoopla.json`

## Step 4 — Mount into Docker (if using Docker)
Add the cookies folder to your docker run command:

```bash
docker run -p 5000:5000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v $(pwd)/data:/app/data \
  brrr-scout
```

The `-v $(pwd)/data:/app/data` line mounts your entire data/ folder
(including data/cookies/) into the container. No rebuild needed.

## How long do cookies last?
Rightmove and Zoopla session cookies typically last 30–90 days.
When scraping starts failing again, just re-export and overwrite the files.
The app logs how many cookies it's sending — check the terminal output.

## Cookie file formats supported
- **Cookie-Editor JSON** (list of cookie objects) — recommended
- **Playwright storage_state** (dict with "cookies" key) — also works

## Security note
Cookie files contain your session tokens. They're stored locally on your
machine inside data/cookies/ which is excluded from git via .gitignore.
Never commit cookie files to version control.
