# RSS Priority

A static priority board published with GitHub Pages. Public RSS and Atom subscriptions live in the tracked [`config/feeds.json`](config/feeds.json) file. GitHub Actions fetches them and builds a separate `feeds.json` snapshot for the browser.

## Set up

1. Edit [`config/feeds.json`](config/feeds.json) and commit a JSON array of public feed URLs, for example:

   ```json
   [
     "https://example.com/feed.xml",
     "https://another.example.org/atom.xml"
   ]
   ```

   **Use RSS or Atom feed URLs, not the home page of a site.** The array may contain up to **30** URLs. The starter list includes security, PHP, infrastructure, and general tech feeds; edit it to suit your interests. 
2. Open **Settings > Pages** and set **Build and deployment > Source** to **GitHub Actions**.
3. Open **Actions > Update RSS site > Run workflow** for the first build. Merged pull requests or direct commits changing `config/feeds.json` on `main` trigger **Deploy site changes** automatically. Site code changes and the five-minute schedule also rebuild the page.

The generated page will be at the URL shown in **Settings > Pages**. The repository's default branch must be `main` for the included workflow; change its `push` branch if yours differs. 

## Automatic updates

The shortest interval GitHub Actions accepts for `schedule` is **every five minutes**. This workflow runs at minutes 2, 7, 12, and so on (`2-59/5 * * * *`) to avoid the top-of-hour peak. Scheduled runs are best effort: GitHub may delay or drop runs during high load. A feed is fetched only when the workflow runs; this is not a guaranteed five-minute delivery service. Changes to `config/feeds.json` on `main` start a deployment without waiting for the next scheduled run; GitHub's queue and build still take some time. You can also trigger a run manually from the Actions tab.

GitHub may disable scheduled workflows in a public repository after 60 days without repository activity. Re-enable the workflow in the Actions tab if that happens.

The workflow has read access to repository contents and permission to deploy GitHub Pages. It does not commit generated data. Each run fetches the configured feeds, combines recent entries, and deploys a new static site. An unavailable feed is skipped so other feeds still render. The build fails if no configured feed can be fetched.

## Priority and automatic unpinning

The board ranks recent security and outage reports above ordinary updates. Critical reports appear together in the red **Critical alerts** section. Reports sharing a CVE ID become one alert with a report count; other critical reports are identified by their article URL. The 150 most recent fetched articles are considered for ranking.

For a recent CVE, CI queries GitHub's public advisory API and, when linked, the vendor's GitHub security advisory. A CVE alert leaves the critical section when a trusted advisory lists patched versions for all affected versions it describes or withdraws the advisory. This means a patch is *available*, not that every installation has been updated. If the advisory lookup fails or has no patch information, the alert remains eligible until **72 hours after the latest relevant article date**. A newer report can renew that window. Articles stay in the normal list after their alert leaves the critical section.

Non-CVE critical reports also expire after 72 hours. A resolved update using the same article URL clears an outage alert sooner. Separate follow-up URLs cannot be matched reliably without a shared incident ID, so those use the time limit. Headlines without a publication date do not become critical alerts. The time limit keeps old alerts from staying pinned indefinitely; it does **not** claim the underlying issue is resolved.

The ranking and alert rules are in [`scripts/build_feeds.py`](scripts/build_feeds.py). The page has no read/unread state because it is a shared information board; saved articles remain local to each visitor's browser.

## Preview and local development

Open [`preview.html`](preview.html) directly in a browser to see the board with two sample critical alerts, ranked news, and a sample patched advisory that is no longer pinned. It is a temporary design preview and does not read the feed config. Edit its markup and [`assets/style.css`](assets/style.css) to iterate on the design; `index.html` is the published page. When the preview is ready, its markup can be carried over to `index.html` while keeping the data hooks used by `assets/app.js`.
