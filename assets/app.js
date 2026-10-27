(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = { data: null, view: 'all', feedId: null, query: '' };
  const savedKey = 'rss-priority-saved-v1';
  let saved;
  try { saved = new Set(JSON.parse(localStorage.getItem(savedKey) || '[]')); }
  catch { saved = new Set(); }
  const persist = () => {
    try { localStorage.setItem(savedKey, JSON.stringify([...saved])); }
    catch { /* The board still works when browser storage is disabled. */ }
  };
  const isHttpUrl = (value) => {
    try { return ['http:', 'https:'].includes(new URL(value).protocol); }
    catch { return false; }
  };
  const timeLabel = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Undated';
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
  };
  const matches = (parts) => !state.query || parts.join(' ').toLowerCase().includes(state.query);

  function renderFeeds() {
    const list = $('#feed-list');
    list.replaceChildren();
    $('#feed-count').textContent = state.data.feeds.length;
    for (const feed of state.data.feeds) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `feed-item${state.feedId === feed.id ? ' active' : ''}`;
      button.setAttribute('aria-pressed', String(state.feedId === feed.id));
      const badge = document.createElement('span');
      badge.className = 'feed-badge';
      badge.textContent = feed.title.slice(0, 1).toUpperCase();
      const name = document.createElement('span');
      name.className = 'feed-name';
      name.textContent = feed.title;
      const count = document.createElement('span');
      count.className = 'feed-item-count';
      count.textContent = state.data.items.filter((item) => item.feedId === feed.id).length;
      button.append(badge, name, count);
      button.addEventListener('click', () => {
        state.feedId = state.feedId === feed.id ? null : feed.id;
        render();
      });
      list.append(button);
    }
  }

  function renderPin(pin) {
    const row = document.createElement('article');
    row.className = 'pin';
    const top = document.createElement('div');
    top.className = 'pin-top';
    const label = document.createElement('span');
    label.className = 'pin-label';
    label.textContent = pin.reason || 'Critical report';
    const id = document.createElement('span');
    id.className = 'pin-id';
    id.textContent = pin.cve || 'LIVE ALERT';
    top.append(label, id);
    const title = document.createElement('h3');
    const link = document.createElement('a');
    link.href = isHttpUrl(pin.url) ? pin.url : '#';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = pin.title;
    title.append(link);
    const meta = document.createElement('div');
    meta.className = 'pin-meta';
    meta.textContent = `${pin.feed} · ${timeLabel(pin.date)}${pin.reports > 1 ? ` · ${pin.reports} reports` : ''}`;
    row.append(top, title, meta);
    return row;
  }

  function renderArticle(item) {
    const row = document.createElement('article');
    row.className = `article${item.priorityScore >= 50 ? ' high-priority' : ''}`;
    const body = document.createElement('div');
    body.className = 'article-body';
    const meta = document.createElement('div');
    meta.className = 'article-meta';
    const source = document.createElement('span');
    source.className = 'article-source';
    source.textContent = item.feed;
    const separator = document.createElement('span');
    separator.textContent = '·';
    const date = document.createElement('time');
    date.textContent = timeLabel(item.date);
    if (item.date) date.dateTime = item.date;
    meta.append(source, separator, date);
    if (item.priorityScore >= 50) {
      const priority = document.createElement('span');
      priority.className = 'priority-tag';
      priority.textContent = 'HIGH PRIORITY';
      meta.append(priority);
    }
    const title = document.createElement('h2');
    const link = document.createElement('a');
    link.href = isHttpUrl(item.url) ? item.url : '#';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = item.title;
    title.append(link);
    const summary = document.createElement('p');
    summary.textContent = item.summary || 'Open the article to read more.';
    body.append(meta, title, summary);
    const save = document.createElement('button');
    save.type = 'button';
    save.className = `icon-button${saved.has(item.url) ? ' selected' : ''}`;
    save.textContent = saved.has(item.url) ? '★' : '☆';
    save.title = saved.has(item.url) ? 'Remove from saved' : 'Save article';
    save.setAttribute('aria-label', save.title);
    save.addEventListener('click', () => {
      saved.has(item.url) ? saved.delete(item.url) : saved.add(item.url);
      persist(); render();
    });
    row.append(body, save);
    return row;
  }

  function render() {
    if (!state.data) return;
    const visiblePins = state.data.pins.filter((pin) =>
      (state.feedId === null || pin.feedIds.includes(state.feedId)) &&
      matches([pin.title, pin.cve || '', pin.feed, pin.reason || ''])
    );
    const pinnedCves = new Set(visiblePins.map((pin) => pin.cve).filter(Boolean));
    const pinnedUrls = new Set(visiblePins.map((pin) => pin.url));
    const items = state.data.items.filter((item) =>
      (state.feedId === null || item.feedId === state.feedId) &&
      (state.view !== 'saved' || saved.has(item.url)) &&
      matches([item.title, item.summary, item.feed, ...(item.cves || [])]) &&
      (state.view === 'saved' || (!pinnedUrls.has(item.url) && !(item.cves || []).some((cve) => pinnedCves.has(cve))))
    );

    $('#all-count').textContent = state.data.items.length;
    $('#saved-count').textContent = state.data.items.filter((item) => saved.has(item.url)).length;
    $('#pin-count').textContent = state.data.pins.length;
    $('#critical-total').textContent = `${visiblePins.length} active`;
    document.querySelectorAll('[data-view]').forEach((button) => {
      button.classList.toggle('active', button.dataset.view === state.view);
      button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
    });
    const feedName = state.data.feeds.find((feed) => feed.id === state.feedId)?.title;
    $('#page-title').textContent = feedName || (state.view === 'saved' ? 'Saved articles' : 'All updates');
    $('#page-subtitle').textContent = feedName ? `Latest stories from ${feedName}.` : 'The most important stories from your feeds, first.';
    $('#results-label').textContent = `${items.length} ${items.length === 1 ? 'ARTICLE' : 'ARTICLES'}`;
    renderFeeds();

    const pinList = $('#pin-list');
    pinList.replaceChildren();
    if (!visiblePins.length) {
      const empty = document.createElement('div');
      empty.className = 'pin-empty';
      empty.textContent = state.query || state.feedId !== null ? 'No critical alerts match this filter.' : 'No active critical alerts.';
      pinList.append(empty);
    } else {
      visiblePins.forEach((pin) => pinList.append(renderPin(pin)));
    }

    const list = $('#article-list');
    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = state.query ? 'No articles match your search.' : state.view === 'saved' ? 'No saved articles yet.' : state.data.feeds.length ? 'No other articles are available.' : 'No feeds configured yet. Add public RSS URLs in config/feeds.json.';
      list.append(empty);
    } else {
      items.forEach((item) => list.append(renderArticle(item)));
    }
  }

  async function load() {
    const preview = $('#preview-data');
    $('#sync-status').textContent = 'Loading feeds';
    try {
      const data = preview ? JSON.parse(preview.textContent) : await (async () => {
        const response = await fetch(`feeds.json?t=${Date.now()}`, { cache: 'no-store' });
        if (!response.ok) throw new Error('Feed snapshot is unavailable');
        return response.json();
      })();
      if (!Array.isArray(data.feeds) || !Array.isArray(data.items) || !Array.isArray(data.pins)) throw new Error('Invalid feed snapshot');
      state.data = data;
      $('#sync-status').textContent = `Updated ${timeLabel(data.updatedAt)}`;
      render();
    } catch {
      $('#sync-status').textContent = 'Feeds unavailable';
      $('#article-list').innerHTML = '<div class="empty-state">The feed snapshot is not available yet. Run the GitHub workflow to publish the board.</div>';
    }
  }

  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => {
    state.view = button.dataset.view;
    render();
  }));
  $('#priority-nav').addEventListener('click', () => {
    state.view = 'all';
    state.feedId = null;
    state.query = '';
    $('#search-input').value = '';
    render();
    $('#critical-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  $('#search-input').addEventListener('input', (event) => {
    state.query = event.target.value.trim().toLowerCase();
    render();
  });
  $('#refresh-button').addEventListener('click', load);
  $('#manage-feeds').addEventListener('click', () => $('#manage-dialog').showModal());
  load();
})();
