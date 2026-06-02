/* ── Theme ───────────────────────────────────────────────────────────── */
const html        = document.documentElement;
const themeToggle = document.getElementById('themeToggle');
const saved       = localStorage.getItem('theme') || 'dark';
html.setAttribute('data-bs-theme', saved);
if (themeToggle) themeToggle.textContent = saved === 'dark' ? '☀️' : '🌙';

themeToggle && themeToggle.addEventListener('click', () => {
  const next = html.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-bs-theme', next);
  localStorage.setItem('theme', next);
  themeToggle.textContent = next === 'dark' ? '☀️' : '🌙';
});

/* ── Navbar scroll effect ────────────────────────────────────────────── */
const nav = document.getElementById('mainNav');
window.addEventListener('scroll', () => {
  nav && nav.classList.toggle('scrolled', window.scrollY > 80);
});

/* ── Helpers ─────────────────────────────────────────────────────────── */
let currentSelected = null;
if (!window.WATCHLIST) window.WATCHLIST = [];

function starRating(score) {
  const f = Math.round(score / 2);
  return '★'.repeat(f) + '☆'.repeat(5 - f);
}

function genreBadges(genres, n = 3) {
  if (!genres) return '';
  return genres.split(',').slice(0, n).map(g =>
    `<span class="badge bg-secondary me-1">${g.trim()}</span>`
  ).join('');
}

function typeBadge(type) {
  if (!type) return '';
  const style = type !== 'Movie' ? 'style="background:#7c3aed"' : '';
  const cls   = type === 'Movie' ? 'bg-primary' : 'bg-purple';
  return `<span class="badge ${cls} me-1" ${style}>${type}</span>`;
}

function cardHtml(m) {
  return `
  <div class="col">
    <div class="movie-card h-100" onclick='openDetail(${JSON.stringify(m).replace(/'/g,"&#39;")})'>
      <div class="position-relative">
        <img src="${m.poster_url}" alt="${m.title}" class="card-poster w-100" loading="lazy"
             onerror="this.src='https://placehold.co/300x450/1a1a2e/e50914?text=No+Image'"/>
        <span class="rating-badge">${m.vote_average}★</span>
      </div>
      <div class="card-info">
        <p class="card-name" title="${m.title}">${m.title}</p>
        <p class="card-meta-text">${m.year} · ${m.vote_average}/10</p>
        <div style="margin:.25rem 0">${typeBadge(m.type)}${genreBadges(m.genres, 2)}</div>
        <p style="font-size:.72rem;color:var(--subtext);line-height:1.5;margin:0">
          ${(m.overview || '').slice(0, 90)}${m.overview && m.overview.length > 90 ? '…' : ''}
        </p>
      </div>
    </div>
  </div>`;
}

/* ── Autocomplete ────────────────────────────────────────────────────── */
function setupAutocomplete(inputId, listId, onSelect) {
  const input = document.getElementById(inputId);
  const list  = document.getElementById(listId);
  if (!input || !list) return;

  let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { list.innerHTML = ''; list.classList.add('hidden'); return; }
    timer = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(q)}`)
        .then(r => r.json())
        .then(matches => {
          if (!matches.length) { list.innerHTML = ''; list.classList.add('hidden'); return; }
          list.innerHTML = matches.map(t =>
            `<li data-title="${t.replace(/"/g,'&quot;')}">${t}</li>`
          ).join('');
          list.classList.remove('hidden');
          list.querySelectorAll('li').forEach(li => {
            li.addEventListener('click', () => {
              const title = li.getAttribute('data-title');
              input.value = title;
              list.innerHTML = '';
              list.classList.add('hidden');
              onSelect(title);
            });
          });
        });
    }, 200);
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !list.contains(e.target))
      list.classList.add('hidden');
  });
}

/* ── Home: Search & Recommendations ─────────────────────────────────── */
const searchInput    = document.getElementById('searchInput');
const findBtn        = document.getElementById('findBtn');
const diceBtn        = document.getElementById('diceBtn');
const addWlBtn       = document.getElementById('addWlBtn');
const searchMsg      = document.getElementById('searchMsg');
const resultsSection = document.getElementById('resultsSection');
const selectedCard   = document.getElementById('selectedCard');
const recGrid        = document.getElementById('recGrid');

if (searchInput) {
  setupAutocomplete('searchInput', 'autocompleteList', title => {
    currentSelected = title;
    if (searchMsg) searchMsg.textContent = '';
  });

  searchInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') doRecommend(searchInput.value.trim());
  });
}

findBtn && findBtn.addEventListener('click', () => {
  doRecommend(searchInput ? searchInput.value.trim() : '');
});

diceBtn && diceBtn.addEventListener('click', () => {
  setLoading(true);
  fetch('/api/random')
    .then(r => r.json())
    .then(data => showResults(data))
    .finally(() => setLoading(false));
});

addWlBtn && addWlBtn.addEventListener('click', () => {
  if (currentSelected) addToWatchlist(currentSelected, addWlBtn);
});

function setLoading(on) {
  if (!findBtn) return;
  findBtn.disabled = on;
  findBtn.textContent = on ? 'Finding…' : 'Find Recommendations';
}

function doRecommend(title) {
  if (!title) {
    if (searchMsg) searchMsg.textContent = 'Please type a movie or TV show title first.';
    return;
  }
  if (searchMsg) searchMsg.textContent = '';
  setLoading(true);

  fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        if (searchMsg) searchMsg.textContent = `"${title}" not found — try a different name.`;
      } else {
        showResults(data);
      }
    })
    .catch(() => {
      if (searchMsg) searchMsg.textContent = 'Something went wrong. Please try again.';
    })
    .finally(() => setLoading(false));
}

function showResults(data) {
  currentSelected = data.selected.title;
  if (searchInput) searchInput.value = data.selected.title;
  if (addWlBtn) addWlBtn.classList.remove('d-none');

  const inWl = window.WATCHLIST.includes(data.selected.title);

  if (selectedCard) {
    selectedCard.innerHTML = `
    <div class="col-auto">
      <img src="${data.selected.poster_url}" class="selected-poster" alt="${data.selected.title}"
           onerror="this.src='https://placehold.co/180x270/1a1a2e/e50914?text=No+Image'"/>
    </div>
    <div class="col">
      <h3 class="fw-black">${data.selected.title}</h3>
      <div class="mb-2">${typeBadge(data.selected.type)}${genreBadges(data.selected.genres, 4)}</div>
      <p class="text-muted small">${data.selected.year} · ${(data.selected.vote_count||0).toLocaleString()} votes</p>
      <p style="color:var(--gold)">${starRating(data.selected.vote_average)}
        <strong class="ms-1">${data.selected.vote_average}/10</strong>
      </p>
      <p style="font-size:.88rem;line-height:1.65;color:var(--subtext)">${data.selected.overview}</p>
      <button class="btn btn-sm ${inWl ? 'btn-outline-danger' : 'btn-danger'}" id="selWlBtn"
              onclick="addToWatchlist('${data.selected.title.replace(/'/g, "\\'")}', this)">
        ${inWl ? '✓ In Watchlist' : '+ Add to Watchlist'}
      </button>
    </div>`;
  }

  if (recGrid) recGrid.innerHTML = data.results.map(m => cardHtml(m)).join('');

  if (resultsSection) {
    resultsSection.classList.remove('d-none');
    setTimeout(() => resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
  }
}

/* ── Detail Modal ────────────────────────────────────────────────────── */
function openDetail(movie) {
  if (typeof movie === 'string') {
    try { movie = JSON.parse(movie); } catch(e) { return; }
  }
  const body  = document.getElementById('modalBody');
  const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('detailModal'));
  const inWl  = window.WATCHLIST.includes(movie.title);
  const is_tv = movie.type === 'TV Show';

  body.innerHTML = `
  <div class="row g-3">
    <div class="col-md-4">
      <img src="${movie.poster_url}" class="w-100 rounded-3" alt="${movie.title}"
           onerror="this.src='https://placehold.co/300x450/1a1a2e/e50914?text=No+Image'"/>
    </div>
    <div class="col-md-8">
      <h3 class="fw-black mb-2">${movie.title}</h3>
      <div class="mb-2">${typeBadge(movie.type)}${genreBadges(movie.genres, 5)}</div>
      <p class="text-muted small mb-1">${movie.year} · ${(movie.vote_count||0).toLocaleString()} votes · Popularity ${movie.popularity}</p>
      <p style="color:var(--gold)" class="mb-2">${starRating(movie.vote_average)}
        <strong class="ms-1">${movie.vote_average}/10</strong>
      </p>
      <p style="font-size:.88rem;line-height:1.65" class="mb-3">${movie.overview}</p>
      <div id="providersRow" class="mb-3">
        <small class="text-muted">Loading streaming info…</small>
      </div>
      <button class="btn ${inWl ? 'btn-outline-danger' : 'btn-danger'}" id="modalWlBtn"
              onclick="addToWatchlist('${movie.title.replace(/'/g,"\\'")}', this)">
        ${inWl ? '✓ In Watchlist' : '+ Add to Watchlist'}
      </button>
    </div>
  </div>`;

  modal.show();

  fetch(`/api/providers/${movie.id}?tv=${is_tv}`)
    .then(r => r.json())
    .then(providers => {
      const row = document.getElementById('providersRow');
      if (!row) return;
      if (!providers.length) {
        row.innerHTML = '<small class="text-muted">Not available on streaming in your region.</small>';
        return;
      }
      row.innerHTML =
        '<p class="small mb-1" style="text-transform:uppercase;letter-spacing:1px;font-weight:700;color:var(--subtext)">Stream on</p>' +
        providers.slice(0, 8).map(p =>
          `<img class="provider-logo" src="https://image.tmdb.org/t/p/original${p.logo_path}"
               title="${p.provider_name}"
               onerror="this.style.display='none'"/>`
        ).join('');
    })
    .catch(() => {
      const row = document.getElementById('providersRow');
      if (row) row.innerHTML = '';
    });
}

/* ── Toast helper ────────────────────────────────────────────────────── */
function showToast(text, icon = '✓', type = 'success') {
  const el   = document.getElementById('wlToast');
  const txt  = document.getElementById('wlToastText');
  const ico  = document.getElementById('wlToastIcon');
  if (!el) return;
  txt.textContent = text;
  ico.textContent = icon;
  el.className = `toast align-items-center border-0 text-white toast-${type}`;
  bootstrap.Toast.getOrCreateInstance(el).show();
}

/* ── Watchlist ───────────────────────────────────────────────────────── */
function addToWatchlist(title, btn) {
  fetch('/api/watchlist/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  })
    .then(r => r.json())
    .then(data => {
      if (!window.WATCHLIST.includes(title)) window.WATCHLIST.push(title);
      if (btn) {
        btn.textContent = '✓ In Watchlist';
        btn.className   = btn.className.replace('btn-danger', 'btn-outline-danger');
      }
      // Update navbar badge
      const badge  = document.querySelector('a[href="/watchlist"] .badge');
      const wlLink = document.querySelector('a[href="/watchlist"]');
      if (badge) {
        badge.textContent = data.count;
      } else if (wlLink && data.count > 0) {
        wlLink.insertAdjacentHTML('beforeend',
          `<span class="badge rounded-pill bg-danger ms-1">${data.count}</span>`);
      }
      showToast(`"${title}" added to Watchlist`, '✓', 'success');
    });
}

function removeFromWatchlist(title, cardId) {
  fetch('/api/watchlist/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  })
    .then(() => {
      window.WATCHLIST = window.WATCHLIST.filter(t => t !== title);
      const el = document.getElementById(cardId);
      if (el) {
        el.style.transition = 'opacity .3s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 300);
      }
    });
}

function clearWatchlist() {
  if (!confirm('Clear your entire watchlist?')) return;
  Promise.all(
    window.WATCHLIST.map(title =>
      fetch('/api/watchlist/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
      })
    )
  ).then(() => location.reload());
}

/* ── Watchlist page: add search ──────────────────────────────────────── */
const wlInput  = document.getElementById('wlInput');
const wlAddBtn = document.getElementById('wlAddBtn');
const wlMsg    = document.getElementById('wlMsg');

if (wlInput) {
  setupAutocomplete('wlInput', 'wlAutocomplete', title => {
    wlInput.value = title;
  });

  wlAddBtn && wlAddBtn.addEventListener('click', () => {
    const title = wlInput.value.trim();
    if (!title) return;
    fetch('/api/watchlist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    })
      .then(r => r.json())
      .then(data => {
        if (data.count !== undefined) location.reload();
        else if (wlMsg) wlMsg.textContent = 'Title not found.';
      });
  });

  wlInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') wlAddBtn && wlAddBtn.click();
  });
}
