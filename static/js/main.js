/* ── Region ──────────────────────────────────────────────────────────── */
function setRegion(code) {
  fetch('/api/set_region', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ region: code })
  }).then(() => location.reload());
}

// Auto-detect on first visit (localStorage flag prevents repeat calls)
if (!localStorage.getItem('regionDetected')) {
  fetch('/api/detect_region')
    .then(r => r.json())
    .then(data => {
      localStorage.setItem('regionDetected', '1');
      const code = data.country_code;
      if (code && code !== 'GLOBAL') setRegion(code);
    })
    .catch(() => localStorage.setItem('regionDetected', '1'));
}

/* ── Language selector ───────────────────────────────────────────────── */
function setLanguage(code) {
  fetch('/api/set_language', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language: code })
  }).then(() => location.reload());
}

/* ── Genre filter pills (home page) ─────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const pills    = document.querySelectorAll('.genre-pill');
  const sections = document.querySelectorAll('.genre-section');

  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      pills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const selected = pill.dataset.genre;
      sections.forEach(sec => {
        if (selected === 'all' || sec.dataset.genre === selected) {
          sec.style.display = '';
        } else {
          sec.style.display = 'none';
        }
      });
      if (selected !== 'all') {
        const first = document.querySelector(`.genre-section[data-genre="${selected}"]`);
        if (first) first.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
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

function genreBadges(genres, n = 3, movie = null) {
  const gmap   = (window.T && window.T.genres) || {};
  const badges = [];

  if (movie && movie.is_lgbtq) {
    badges.push(`<span class="badge badge-genre me-1"
                       style="background:linear-gradient(90deg,#e40303,#ff8c00,#ffed00,#008026,#004dff,#750787);color:#fff;font-weight:700"
                       onclick="event.stopPropagation();genreClick('LGBTQ+')">LGBTQ+</span>`);
  }

  if (genres) {
    genres.split(',').slice(0, n).forEach(g => {
      const name = g.trim();
      if (!name) return;
      const label = gmap[name] || name;
      badges.push(`<span class="badge bg-secondary me-1 badge-genre"
                         onclick="event.stopPropagation();genreClick('${name.replace(/'/g,"\\'")}')">
                    ${label}
                   </span>`);
    });
  }

  return badges.join('');
}

function typeBadge(type) {
  if (!type) return '';
  const label = type === 'Movie'
    ? (window.T && window.T.type_movie ? window.T.type_movie : type)
    : (window.T && window.T.type_tv   ? window.T.type_tv   : type);
  const style = type !== 'Movie' ? 'style="background:#7c3aed"' : '';
  const cls   = type === 'Movie' ? 'bg-primary' : 'bg-purple';
  const typeFilter = type === 'Movie' ? 'Movie' : 'TV Show';
  return `<span class="badge ${cls} me-1 badge-genre" ${style}
               onclick="event.stopPropagation();typeClick('${typeFilter}')">${label}</span>`;
}

function genreClick(genre) {
  selectedGenres = [genre];
  document.querySelectorAll('.genre-pick-pill').forEach(p => {
    p.classList.toggle('active', p.dataset.genre === genre);
  });
  updateSelectedGenresDisplay();
  const modal = bootstrap.Modal.getInstance(document.getElementById('detailModal'));
  if (modal) modal.hide();
  doGenreBrowse([genre]);
}

function typeClick(type) {
  // Browse by type (Movie or TV Show)
  if (searchMsg) searchMsg.textContent = '';
  setLoading(true);
  fetch(`/api/genre_top?genres[]=Action&genres[]=Drama&genres[]=Comedy&genres[]=Thriller&type=${encodeURIComponent(type)}`)
    .then(r => r.json())
    .then(results => {
      if (selectedCard) selectedCard.innerHTML = '';
      const heading = document.getElementById('resultsHeading');
      if (heading) heading.textContent = `Top ${type}s`;
      if (recGrid) recGrid.innerHTML = results.map(m => cardHtml(m)).join('');
      if (resultsSection) {
        resultsSection.classList.remove('d-none');
        const modal = bootstrap.Modal.getInstance(document.getElementById('detailModal'));
        if (modal) modal.hide();
        setTimeout(() => resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
      }
    })
    .finally(() => setLoading(false));
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
        <div style="margin:.25rem 0">${typeBadge(m.type)}${genreBadges(m.genres, 2, m)}</div>
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
          list.innerHTML = matches.map(item => {
            const title = typeof item === 'string' ? item : item.title;
            const type  = typeof item === 'string' ? '' : item.type;
            const badge = type
              ? `<span class="ac-type" style="background:${type==='Movie'?'#1d4ed8':'#7c3aed'};color:#fff">${type==='Movie'?(window.T?.type_movie||'Movie'):(window.T?.type_tv||'TV')}</span>`
              : '';
            return `<li data-title="${title.replace(/"/g,'&quot;')}">${title}${badge}</li>`;
          }).join('');
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

/* ── Pagination state ────────────────────────────────────────────────── */
let _recState   = null;  // { title, offset }
let _genreState = null;  // { genres, offset }
let _browseState= null;  // { query, offset }

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

/* ── Multi-genre picker ──────────────────────────────────────────────── */
let selectedGenres = [];

function updateSelectedGenresDisplay() {
  const display = document.getElementById('selectedGenresDisplay');
  if (!display) return;
  if (!selectedGenres.length) { display.innerHTML = ''; return; }
  display.innerHTML = selectedGenres.map(g =>
    `<span class="selected-genre-chip">${g}
       <button type="button" class="chip-remove" data-genre="${g}" aria-label="Remove ${g}">×</button>
     </span>`
  ).join('');
  display.querySelectorAll('.chip-remove').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const g = btn.dataset.genre;
      selectedGenres = selectedGenres.filter(x => x !== g);
      document.querySelectorAll('.genre-pick-pill').forEach(p => {
        if (p.dataset.genre === g) p.classList.remove('active');
      });
      updateSelectedGenresDisplay();
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.genre-pick-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const genre = pill.dataset.genre;
      if (selectedGenres.includes(genre)) {
        selectedGenres = selectedGenres.filter(g => g !== genre);
        pill.classList.remove('active');
      } else {
        selectedGenres.push(genre);
        pill.classList.add('active');
      }
      updateSelectedGenresDisplay();
    });
  });
});

findBtn && findBtn.addEventListener('click', () => {
  const title = searchInput ? searchInput.value.trim() : '';
  if (selectedGenres.length && !title) {
    doGenreBrowse(selectedGenres);
  } else if (title && currentSelected === title) {
    doRecommend(title);
  } else if (title) {
    doSearchCards(title);
  } else {
    if (searchMsg) searchMsg.textContent = window.T?.search_placeholder || 'Please type a title or pick a genre first.';
  }
});

diceBtn && diceBtn.addEventListener('click', () => {
  const sec = document.getElementById('browseSection');
  if (sec) sec.classList.add('d-none');
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
  _recState = { title, offset: 0 };

  fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, offset: 0 })
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        if (searchMsg) searchMsg.textContent = `"${title}" ${window.T?.not_found || 'not found'}`;
      } else {
        showResults(data);
        _recState.offset = data.offset || 20;
        const wrap = document.getElementById('recMoreWrap');
        if (wrap) wrap.classList.toggle('d-none', !data.has_more);
      }
    })
    .catch(() => {
      if (searchMsg) searchMsg.textContent = window.T?.error || 'Something went wrong.';
    })
    .finally(() => setLoading(false));
}

function loadMoreRecs() {
  if (!_recState) return;
  const btn = document.getElementById('recMoreBtn');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }

  fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: _recState.title, offset: _recState.offset })
  })
    .then(r => r.json())
    .then(data => {
      if (recGrid) recGrid.insertAdjacentHTML('beforeend', data.items.map(m => cardHtml(m)).join(''));
      _recState.offset = data.offset;
      const wrap = document.getElementById('recMoreWrap');
      if (wrap) wrap.classList.toggle('d-none', !data.has_more);
    })
    .finally(() => {
      if (btn) { btn.disabled = false; btn.textContent = window.T?.show_more || 'Show More'; }
    });
}

/* ── Show More button wiring ─────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const recBtn = document.getElementById('recMoreBtn');
  recBtn && recBtn.addEventListener('click', () => {
    if (_recState)   loadMoreRecs();
    else if (_genreState) loadMoreGenre();
  });

  const browseBtn = document.getElementById('browseMoreBtn');
  browseBtn && browseBtn.addEventListener('click', loadMoreBrowse);
});

function loadMoreGenre() {
  if (!_genreState) return;
  const btn = document.getElementById('recMoreBtn');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  const params = _genreState.genres.map(g => `genres[]=${encodeURIComponent(g)}`).join('&');
  fetch(`/api/genre_top?${params}&offset=${_genreState.offset}`)
    .then(r => r.json())
    .then(data => {
      const items = data.items || [];
      if (recGrid) recGrid.insertAdjacentHTML('beforeend', items.map(m => cardHtml(m)).join(''));
      _genreState.offset = data.offset;
      const wrap = document.getElementById('recMoreWrap');
      if (wrap) wrap.classList.toggle('d-none', !data.has_more);
    })
    .finally(() => {
      if (btn) { btn.disabled = false; btn.textContent = window.T?.show_more || 'Show More'; }
    });
}

function loadMoreBrowse() {
  if (!_browseState) return;
  const btn = document.getElementById('browseMoreBtn');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  fetch(`/api/search_cards?q=${encodeURIComponent(_browseState.query)}&offset=${_browseState.offset}`)
    .then(r => r.json())
    .then(data => {
      const items = data.items || [];
      const grid  = document.getElementById('browseGrid');
      if (grid) grid.insertAdjacentHTML('beforeend', items.map(m => browseCardHtml(m)).join(''));
      _browseState.offset = data.offset;
      const wrap = document.getElementById('browseMoreWrap');
      if (wrap) wrap.classList.toggle('d-none', !data.has_more);
    })
    .finally(() => {
      if (btn) { btn.disabled = false; btn.textContent = window.T?.show_more || 'Show More'; }
    });
}

/* ── Browse: show all matching titles as cards ───────────────────────── */
function doSearchCards(query) {
  if (searchMsg) searchMsg.textContent = '';
  setLoading(true);

  fetch(`/api/search_cards?q=${encodeURIComponent(query)}`)
    .then(r => r.json())
    .then(data => {
      const results = data.items || [];
      if (!results.length) {
        if (searchMsg) searchMsg.textContent = `"${query}" not found — try a different name.`;
        return;
      }
      const sec     = document.getElementById('browseSection');
      const grid    = document.getElementById('browseGrid');
      const heading = document.getElementById('browseHeading');
      const hint    = document.getElementById('browseHint');

      if (heading) heading.textContent = `${data.total || results.length} result${results.length !== 1 ? 's' : ''} for "${query}"`;
      if (hint)    hint.textContent    = window.T?.browse_hint || 'Click a title to get recommendations';
      if (grid)    grid.innerHTML      = results.map(m => browseCardHtml(m)).join('');
      _browseState = { query, offset: data.offset || results.length };
      const moreWrap = document.getElementById('browseMoreWrap');
      if (moreWrap) moreWrap.classList.toggle('d-none', !data.has_more);

      // Hide old recs, show browse
      if (resultsSection) resultsSection.classList.add('d-none');
      if (sec) {
        sec.classList.remove('d-none');
        setTimeout(() => sec.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
      }
    })
    .catch(() => {
      if (searchMsg) searchMsg.textContent = 'Something went wrong. Please try again.';
    })
    .finally(() => setLoading(false));
}

function browseCardHtml(m) {
  const safeM = JSON.stringify(m).replace(/'/g, "&#39;");
  return `
  <div class="col">
    <div class="movie-card h-100" style="cursor:pointer" onclick='selectAndRecommend(${safeM})'>
      <div class="position-relative">
        <img src="${m.poster_url}" alt="${m.title}" class="card-poster w-100" loading="lazy"
             onerror="this.src='https://placehold.co/300x450/1a1a2e/59005c?text=No+Image'"/>
        <span class="rating-badge">${m.vote_average}★</span>
      </div>
      <div class="card-info">
        <p class="card-name" title="${m.title}">${m.title}</p>
        <p class="card-meta-text">${m.year} · ${m.vote_average}/10</p>
        <div style="margin:.25rem 0">${typeBadge(m.type)}${genreBadges(m.genres, 2, m)}</div>
        <button class="btn btn-sm btn-danger w-100 mt-2 fw-bold" style="pointer-events:none">
          ${window.T?.find_recs || 'Find Recommendations'}
        </button>
      </div>
    </div>
  </div>`;
}

function selectAndRecommend(movie) {
  currentSelected = movie.title;
  if (searchInput) searchInput.value = movie.title;
  const sec = document.getElementById('browseSection');
  if (sec) sec.classList.add('d-none');
  doRecommend(movie.title);
}

function doGenreBrowse(genres) {
  if (!Array.isArray(genres)) genres = [genres];
  if (searchMsg) searchMsg.textContent = '';
  setLoading(true);
  const params = genres.map(g => `genres[]=${encodeURIComponent(g)}`).join('&');
  fetch(`/api/genre_top?${params}`)
    .then(r => r.json())
    .then(data => {
      // Handle both {items:[...]} dict and legacy plain-array responses
      const results  = Array.isArray(data) ? data : (data.items || []);
      const hasMore  = Array.isArray(data) ? false : !!data.has_more;
      const nextOff  = Array.isArray(data) ? results.length : (data.offset || results.length);
      if (!results.length) {
        if (searchMsg) searchMsg.textContent = `No results found for "${genres.join(' + ')}".`;
        return;
      }
      if (selectedCard) selectedCard.innerHTML = '';
      const heading = document.getElementById('resultsHeading');
      if (heading) heading.textContent = `Top ${genres.join(' + ')} Titles`;
      if (recGrid) recGrid.innerHTML = results.map(m => cardHtml(m)).join('');
      _genreState = { genres, offset: nextOff };
      const wrap = document.getElementById('recMoreWrap');
      if (wrap) wrap.classList.toggle('d-none', !hasMore);
      if (resultsSection) {
        resultsSection.classList.remove('d-none');
        setTimeout(() => resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
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
           onerror="this.src='https://placehold.co/180x270/1a1a2e/59005c?text=No+Image'"/>
    </div>
    <div class="col">
      <h3 class="fw-black">${data.selected.title}</h3>
      <div class="mb-2">${typeBadge(data.selected.type)}${genreBadges(data.selected.genres, 4, data.selected)}</div>
      <p class="text-muted small">${data.selected.year} · ${(data.selected.vote_count||0).toLocaleString()} votes</p>
      <p style="color:var(--gold)">${starRating(data.selected.vote_average)}
        <strong class="ms-1">${data.selected.vote_average}/10</strong>
      </p>
      <p style="font-size:.88rem;line-height:1.65;color:var(--subtext)">${data.selected.overview}</p>
      <button class="btn btn-sm ${inWl ? 'btn-outline-danger' : 'btn-danger'}" id="selWlBtn"
              onclick="addToWatchlist('${data.selected.title.replace(/'/g, "\\'")}', this)">
        ${inWl ? (window.T?.in_watchlist||'✓ In Watchlist') : (window.T?.add_watchlist||'+ Watchlist')}
      </button>
    </div>`;
  }

  const items = data.items || data.results || [];
  if (recGrid) recGrid.innerHTML = items.map(m => cardHtml(m)).join('');

  const wrap = document.getElementById('recMoreWrap');
  if (wrap) wrap.classList.toggle('d-none', !data.has_more);

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
      <div class="mb-2">${typeBadge(movie.type)}${genreBadges(movie.genres, 5, movie)}</div>
      <p class="text-muted small mb-1">${movie.year} · ${(movie.vote_count||0).toLocaleString()} votes · Popularity ${movie.popularity}</p>
      <p style="color:var(--gold)" class="mb-2">${starRating(movie.vote_average)}
        <strong class="ms-1">${movie.vote_average}/10</strong>
      </p>
      ${is_tv ? `<div id="tvInfoRow" class="mb-2"><small class="text-muted">${window.T.loading_seasons}</small></div>` : ''}
      <p style="font-size:.88rem;line-height:1.65" class="mb-3" id="modalOverview">${movie.overview}</p>
      <div id="providersRow" class="mb-3">
        <small class="text-muted">${window.T.loading_streaming}</small>
      </div>
      <div id="reviewsRow" class="mb-3">
        <small class="text-muted">${window.T.loading_reviews}</small>
      </div>
      <button class="btn ${inWl ? 'btn-outline-danger' : 'btn-danger'}" id="modalWlBtn"
              onclick="addToWatchlist('${movie.title.replace(/'/g,"\\'")}', this)">
        ${inWl ? window.T.in_watchlist : window.T.add_watchlist}
      </button>
    </div>
  </div>`;

  modal.show();

  // Fetch translated overview if language is not English
  if (window.LANG && window.LANG !== 'en') {
    fetch(`/api/overview/${movie.id}?tv=${is_tv}&lang=${window.LANG}`)
      .then(r => r.json())
      .then(data => {
        if (data.overview) {
          const el = document.getElementById('modalOverview');
          if (el) el.textContent = data.overview;
        }
      })
      .catch(() => {});
  }

  // Fetch TV season info
  if (is_tv) {
    fetch(`/api/tv_info/${movie.id}`)
      .then(r => r.json())
      .then(info => {
        const row = document.getElementById('tvInfoRow');
        if (!row || !info.seasons) return;
        const statusBadge = info.status
          ? `<span class="badge ms-2" style="background:${info.status==='Ended'?'#6b7280':'#16a34a'};font-size:.7rem">${info.status}</span>`
          : '';
        const networkText = info.network ? ` · ${info.network}` : '';
        const seasonWord  = info.seasons === 1 ? window.T.season : window.T.seasons;
        const seasonPills = info.season_list.map(s =>
          `<span class="badge me-1 mb-1" style="background:rgba(147,51,234,.25);color:#c084fc;font-size:.7rem;font-weight:500">
            S${s.number} · ${s.episodes} eps
          </span>`
        ).join('');
        row.innerHTML = `
          <div class="mb-1">
            <span style="font-size:.88rem;font-weight:700;color:var(--text)">
              ${info.seasons} ${seasonWord}
            </span>
            <span style="font-size:.82rem;color:var(--subtext)">
              · ${info.episodes} ${window.T.episodes}${networkText}
            </span>
            ${statusBadge}
          </div>
          <div>${seasonPills}</div>`;
      })
      .catch(() => {
        const row = document.getElementById('tvInfoRow');
        if (row) row.innerHTML = '';
      });
  }

  // Fetch streaming providers
  fetch(`/api/providers/${movie.id}?tv=${is_tv}`)
    .then(r => r.json())
    .then(providers => {
      const row = document.getElementById('providersRow');
      if (!row) return;
      if (!providers.length) {
        row.innerHTML = `<small class="text-muted">${window.T.not_streaming}</small>`;
        return;
      }
      row.innerHTML =
        `<p class="small mb-1" style="text-transform:uppercase;letter-spacing:1px;font-weight:700;color:var(--subtext)">${window.T.stream_on}</p>` +
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

  // Fetch reviews
  fetch(`/api/reviews/${movie.id}?tv=${is_tv}`)
    .then(r => r.json())
    .then(reviews => {
      const row = document.getElementById('reviewsRow');
      if (!row) return;
      if (!reviews.length) { row.innerHTML = ''; return; }
      const cards = reviews.map(rv => {
        const stars  = rv.rating ? `<span style="color:var(--gold);font-weight:700">${rv.rating}/10</span>` : '';
        const avatar = rv.avatar
          ? `<img src="${rv.avatar}" style="width:28px;height:28px;border-radius:50%;object-fit:cover;margin-right:.5rem" onerror="this.style.display='none'"/>`
          : `<span style="width:28px;height:28px;border-radius:50%;background:rgba(89,0,92,.4);display:inline-flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700;margin-right:.5rem;color:#fff">${rv.author[0].toUpperCase()}</span>`;
        const preview = rv.content.length > 180 ? rv.content.slice(0, 180) + '…' : rv.content;
        return `
        <div style="background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;padding:.75rem;margin-bottom:.5rem">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.4rem">
            <div style="display:flex;align-items:center">
              ${avatar}
              <span style="font-weight:700;font-size:.82rem;color:var(--text)">${rv.author}</span>
            </div>
            <div style="display:flex;align-items:center;gap:.5rem">
              ${stars}
              <span style="font-size:.72rem;color:var(--subtext)">${rv.date}</span>
            </div>
          </div>
          <p style="font-size:.78rem;color:var(--subtext);line-height:1.55;margin:0">${preview}</p>
          ${rv.url ? `<a href="${rv.url}" target="_blank" style="font-size:.72rem;color:#a855f7;margin-top:.3rem;display:inline-block">${window.T.read_review}</a>` : ''}
        </div>`;
      }).join('');
      row.innerHTML = `
        <p class="small mb-2" style="text-transform:uppercase;letter-spacing:1px;font-weight:700;color:var(--subtext)">
          ${window.T.reviews}
        </p>
        ${cards}`;
    })
    .catch(() => {
      const row = document.getElementById('reviewsRow');
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
      const msg = window.T && window.T.added_to_watchlist ? window.T.added_to_watchlist : 'added to Watchlist';
      showToast(`"${title}" ${msg}`, '✓', 'success');
    });
}

function markWatched(title, posterUrl, year, type, rating, cardId) {
  const card = document.getElementById(cardId);

  // 🎉 Celebration animation on the card
  if (card) {
    card.style.transition = 'transform .15s';
    card.style.transform  = 'scale(1.08)';
    // Burst confetti-style emoji overlay
    const burst = document.createElement('div');
    burst.style.cssText = `
      position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
      font-size:4rem; z-index:9999; pointer-events:none;
      animation: watchedBurst .8s ease-out forwards;
    `;
    burst.textContent = '🎉';
    document.body.appendChild(burst);
    setTimeout(() => burst.remove(), 900);
    setTimeout(() => {
      card.style.transform = 'scale(1)';
      card.style.opacity   = '0';
      card.style.transition = 'opacity .4s';
      setTimeout(() => card.remove(), 400);
    }, 300);
  }

  fetch('/api/watched/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, poster_url: posterUrl, year, type, vote_average: rating })
  }).then(() => {
    window.WATCHLIST = window.WATCHLIST.filter(t => t !== title);
    showToast(`"${title}" ✓ marked as watched!`, '🎬', 'success');

    // Update watchlist count badge
    const countEl = document.querySelector('h1 .fw-normal');
    if (countEl) {
      const cur = parseInt(countEl.textContent.match(/\d+/)?.[0] || 1);
      countEl.textContent = `(${Math.max(0, cur - 1)} ${window.T?.saved || 'saved'})`;
    }

    // Inject card into Watch History section immediately
    const historySection = document.getElementById('historySection');
    const historyGrid    = document.getElementById('historyGrid');
    if (historyGrid) {
      const today = new Date().toLocaleDateString('en-GB', { month:'short', day:'numeric', year:'numeric' });
      const col   = document.createElement('div');
      col.className = 'col';
      col.innerHTML = `
        <div class="watched-card">
          <div class="position-relative">
            <img src="${posterUrl || 'https://placehold.co/300x450/1a1a2e/59005c?text=No+Image'}"
                 alt="${title}" class="card-poster w-100" loading="lazy"
                 onerror="this.src='https://placehold.co/300x450/1a1a2e/59005c?text=No+Image'"/>
            <div class="watched-overlay">✓</div>
          </div>
          <div class="card-info">
            <p class="card-name" title="${title}">${title}</p>
            <p class="card-meta-text">${year} · ⭐ ${rating}</p>
            <p class="card-meta-text" style="font-size:.65rem;color:var(--subtext)">${today}</p>
          </div>
        </div>`;
      historyGrid.prepend(col);

      // Show section if it was hidden (first ever watched item)
      if (historySection) historySection.style.display = '';

      // Update history count
      const histCount = document.getElementById('historyCount');
      if (histCount) {
        const cur = parseInt(histCount.textContent.match(/\d+/)?.[0] || 0);
        histCount.textContent = `${cur + 1} ${window.T?.titles_watched || 'titles watched'}`;
      }
    }
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
      if (data.count === undefined) {
        if (wlMsg) wlMsg.textContent = 'Title not found.';
        return;
      }
      // Fetch full movie data and inject card without reload
      return fetch(`/api/movie_data?title=${encodeURIComponent(title)}`)
        .then(r => r.json())
        .then(m => {
          if (!m) return;
          const grid = document.getElementById('wlGrid');
          const countEl = document.querySelector('h1 .fw-normal');
          const emptyEl = document.querySelector('.text-center.py-5');

          // Update count
          if (countEl) countEl.textContent = `(${data.count} ${window.T?.saved || 'saved'})`;

          // Hide empty state if showing
          if (emptyEl) emptyEl.style.display = 'none';

          // Create grid if it doesn't exist
          let g = grid;
          if (!g) {
            g = document.createElement('div');
            g.id = 'wlGrid';
            g.className = 'row row-cols-2 row-cols-sm-3 row-cols-md-4 row-cols-lg-5 g-3';
            const section = document.querySelector('.content-section');
            const hr = section && section.querySelector('hr');
            if (hr) section.insertBefore(g, hr);
            else if (section) section.appendChild(g);
          }

          const idx   = data.count;
          const type  = m.type === 'Movie' ? (window.T?.type_movie || 'Movie') : (window.T?.type_tv || 'TV Show');
          const col   = document.createElement('div');
          col.className = 'col';
          col.id        = `wl-${idx}`;
          col.innerHTML = `
            <div class="movie-card h-100" onclick='openDetail(${JSON.stringify(m).replace(/'/g,"&#39;")})'>
              <div class="position-relative">
                <img src="${m.poster_url}" alt="${m.title}" class="card-poster w-100" loading="lazy"
                     onerror="this.src='https://placehold.co/300x450/1a1a2e/59005c?text=No+Image'"/>
                <span class="rating-badge">${m.vote_average}★</span>
              </div>
              <div class="card-info">
                <p class="card-name" title="${m.title}">${m.title}</p>
                <p class="card-meta-text">${m.year} · ${type}</p>
                <button class="btn btn-sm btn-outline-danger w-100 mt-1"
                        onclick="event.stopPropagation();removeFromWatchlist('${m.title.replace(/'/g,"\\'")}','wl-${idx}')">
                  ${window.T?.remove || 'Remove'}
                </button>
              </div>
            </div>`;

          g.appendChild(col);
          col.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

          // Update WATCHLIST array
          if (!window.WATCHLIST.includes(title)) window.WATCHLIST.push(title);

          // Clear input
          wlInput.value = '';
          if (wlMsg) wlMsg.textContent = '';
        });
    })
    .catch(() => {
      if (wlMsg) wlMsg.textContent = 'Something went wrong.';
    });
  });

  wlInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') wlAddBtn && wlAddBtn.click();
  });
}
