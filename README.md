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
3. Open **Actions > Update RSS site > Run workflow** for the first build. Merged pull requests or direct commits changing `config/feeds.json` on `main` trigger **Deploy site changes** automatically. Site code changes and the 15-minute schedule also rebuild the page.

The generated page will be at the URL shown in **Settings > Pages**. The repository's default branch must be `main` for the included workflow; change its `push` branch if yours differs. 

## Automatic updates

The dedicated **Refresh feeds** workflow runs every 15 minutes (`*/15 * * * *`). GitHub Actions accepts schedules as frequent as every five minutes, but scheduled runs are best effort and may be delayed or dropped during high load. Each scheduled run fetches the feeds and compares the result with the published `feeds.json`, excluding its build timestamp. It uploads and deploys a new Pages artifact only when the feeds, alerts, or articles changed. A missing or unreadable published snapshot also triggers deployment. This can still run CI every 15 minutes, but avoids deploying the same board repeatedly. Changes to `config/feeds.json` on `main` and manual runs deploy immediately without waiting for content to differ.

To verify automatic updates, look for runs named **Refresh feeds** in the Actions tab. Commit timestamps do not change during scheduled runs because the generated snapshot is deployed as an artifact, not committed to the repository. If no scheduled runs appear after the workflow is on the default branch, check that **Refresh feeds** is enabled under Actions; GitHub may delay or skip scheduled starts.

GitHub may disable scheduled workflows in a public repository after 60 days without repository activity. Re-enable the workflow in the Actions tab if that happens.

The workflow has read access to repository contents and permission to deploy GitHub Pages. It does not commit generated data. Each run fetches the configured feeds, combines recent entries, and deploys a new static site. An unavailable feed is skipped so other feeds still render. The build fails if no configured feed can be fetched.

## Priority and automatic unpinning

The board ranks recent security and outage reports above ordinary updates. Explicit active incidents appear together in the red **Critical alerts** section. CVEs reported together form one alert, and active follow-ups sharing a distinctive incident name can join it. Patch-announcement headlines stay in the normal article list. The 150 most recent fetched articles are considered for ranking; title matching is still a heuristic, not a verified incident status.

For a recent CVE, CI queries GitHub's public advisory API and, when linked, the vendor's GitHub security advisory. A CVE alert leaves the critical section when a trusted advisory lists patched versions for all affected versions it describes or withdraws the advisory. This means a patch is *available*, not that every installation has been updated. If the advisory lookup fails or has no patch information, the alert remains eligible until **72 hours after the latest relevant article date**. A newer report can renew that window. Articles stay in the normal list after their alert leaves the critical section.

Non-CVE critical reports also expire after 72 hours. A resolved update using the same article URL clears an outage alert sooner. Separate follow-up URLs cannot be matched reliably without a shared incident ID, so those use the time limit. Headlines without a publication date do not become critical alerts. The time limit keeps old alerts from staying pinned indefinitely; it does **not** claim the underlying issue is resolved.

The ranking and alert rules are in [`scripts/build_feeds.py`](scripts/build_feeds.py). The page has no read/unread or saved state because it is a shared information board whose article snapshot rotates.

## Preview and local development

Open [`preview.html`](preview.html) directly in a browser to see the board with two sample critical alerts, ranked news, and a sample patched advisory that is no longer pinned. It is a temporary design preview and does not read the feed config. Edit its markup and [`assets/style.css`](assets/style.css) to iterate on the design; `index.html` is the published page. When the preview is ready, its markup can be carried over to `index.html` while keeping the data hooks used by `assets/app.js`.
