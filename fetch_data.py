import os
import numpy as np
import requests
import pandas as pd
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Shared session — reuses TCP connections (faster than new connection per request)
_session = requests.Session()
_session.headers.update({'User-Agent': 'MovieRec/1.0'})

# Directors/writers strongly associated with LGBTQ+ cinema
LGBTQ_AUTEURS = {
    'pedro almodovar', 'todd haynes', 'gus van sant', 'gregg araki',
    'derek jarman', 'john waters', 'ang lee', 'lisa cholodenko',
    'xavier dolan', 'francois ozon', 'sebastiane lelio', 'abdellatif kechiche',
    'brokeback mountain', 'moonlight', 'call me by your name', 'carol',
}

# Extra vocabulary to seed LGBTQ+ tags beyond what TMDB keywords provide
LGBTQ_SEED = (
    'lgbtq queer gay lesbian bisexual transgender nonbinary '
    'coming_out gay_romance lesbian_romance gay_relationship '
    'queer_cinema same_sex_love gay_protagonist lesbian_protagonist '
    'transgender_identity gay_marriage same_sex_marriage same_sex_couple '
    'queer_love drag_queen homophobia sexual_orientation lgbtq_community'
    # Removed: pride, identity, acceptance, self_discovery — too generic,
    # causes false matches with mainstream films (Lion King, etc.)
)


def fetch_tmdb_keywords(tmdb_id, media_type):
    mt = 'tv' if media_type == 'TV Show' else 'movie'
    try:
        res = requests.get(
            f"{BASE_URL}/{mt}/{tmdb_id}/keywords",
            params={'api_key': API_KEY}, timeout=4
        ).json()
        kws = res.get('keywords', res.get('results', []))
        return ' '.join(k['name'].lower().replace(' ', '_') for k in kws)
    except Exception:
        return ''


def fetch_credits_tags(tmdb_id, media_type):
    mt = 'tv' if media_type == 'TV Show' else 'movie'
    try:
        res = requests.get(
            f"{BASE_URL}/{mt}/{tmdb_id}/credits",
            params={'api_key': API_KEY}, timeout=4
        ).json()
        cast_names  = [p['name'].lower() for p in res.get('cast', [])[:10]]
        crew_names  = [p['name'].lower() for p in res.get('crew', [])
                       if p.get('job') in ('Director', 'Writer', 'Screenplay')]
        names = cast_names + crew_names
        # Mark auteur directors
        auteur_flag = ' lgbtq_auteur' if any(a in n for a in LGBTQ_AUTEURS for n in names) else ''
        return ' '.join(names).replace(' ', '_') + auteur_flag
    except Exception:
        return ''


def enrich_lgbtq_tags(items):
    """Fetch TMDB keywords + credits for LGBTQ+ items to improve similarity matching."""
    total = len(items)
    print(f"\n  Enriching {total} LGBTQ+ titles with keywords & credits…")
    for i, item in enumerate(items):
        kw      = fetch_tmdb_keywords(item['id'], item['type'])
        credits = fetch_credits_tags(item['id'], item['type'])
        item['tags'] += ' ' + kw + ' ' + credits + ' ' + LGBTQ_SEED
        if (i + 1) % 25 == 0:
            print(f"    {i+1}/{total} enriched")
        time.sleep(0.08)  # stay within TMDB rate limit (40 req/s)
    return items

from dotenv import load_dotenv
load_dotenv()
API_KEY  = os.environ.get('TMDB_KEY', '')
BASE_URL = 'https://api.themoviedb.org/3'

LANG_REGIONS = {
    'en':  ['US','GB','CA','AU','NZ','ZA','NG','GH','IE'],
    'fr':  ['FR','BE','CA','CH','CI','SN','CM','MG'],
    'es':  ['ES','MX','AR','CO','CL','PE','VE','US'],
    'pt':  ['BR','PT','AO','MZ'],
    'de':  ['DE','AT','CH'],
    'it':  ['IT','CH'],
    'nl':  ['NL','BE'],
    'ja':  ['JP','US','GB'],
    'ko':  ['KR','US','GB'],
    'zh':  ['CN','TW','HK','SG'],
    'hi':  ['IN','PK'],
    'ar':  ['AE','SA','EG','MA','IQ','JO','LB','KW'],
    'tr':  ['TR'],
    'ru':  ['RU'],
    'sv':  ['SE','NO','DK'],
    'yo':  ['NG','GH'],
    'ig':  ['NG'],
    'ha':  ['NG','GH','NE'],
    'sw':  ['KE','TZ','UG','RW'],
    'am':  ['ET'],
    'zu':  ['ZA'],
    'af':  ['ZA','NA'],
    'so':  ['SO','ET','KE'],
}

def get_genres(media_type):
    res = requests.get(f"{BASE_URL}/genre/{media_type}/list", params={'api_key': API_KEY}).json()
    return {g['id']: g['name'] for g in res['genres']}

WORKERS = 10   # parallel page requests — safe within TMDB's 40 req/s limit

def _fetch_page(media_type, page, params, genres_map, origin_country):
    """Fetch a single discover page. Called in parallel by fetch_items."""
    name_key = 'title' if media_type == 'movie' else 'name'
    date_key = 'release_date' if media_type == 'movie' else 'first_air_date'
    try:
        res = _session.get(
            f"{BASE_URL}/discover/{media_type}",
            params={**params, 'page': page}, timeout=8
        ).json()
    except Exception:
        return []

    results = []
    for item in res.get('results', []):
        genre_names = [genres_map.get(gid, '') for gid in item.get('genre_ids', [])]
        lang        = item.get('original_language', '')
        base_regions = list(LANG_REGIONS.get(lang, ['US', 'GB', 'CA', 'AU']))
        if origin_country and origin_country not in base_regions:
            base_regions = [origin_country] + base_regions
        results.append({
            'id':                item['id'],
            'title':             item.get(name_key, ''),
            'type':              'Movie' if media_type == 'movie' else 'TV Show',
            'genres':            ', '.join(g for g in genre_names if g),
            'overview':          item.get('overview', ''),
            'popularity':        item.get('popularity', 0),
            'release_date':      item.get(date_key, ''),
            'vote_average':      item.get('vote_average', 0),
            'vote_count':        item.get('vote_count', 0),
            'poster_path':       item.get('poster_path', ''),
            'backdrop_path':     item.get('backdrop_path', ''),
            'original_language': lang,
            'origin_country':    origin_country or '',
            'regions':           base_regions,
            'tags':              item.get('overview', '') + ' ' + ' '.join(genre_names),
        })
    return results


def fetch_items(media_type, pages=25, vote_min=50, language=None, region=None,
                sort_by='vote_count.desc', origin_country=None):
    genres_map = get_genres(media_type)
    base_params = {'api_key': API_KEY, 'sort_by': sort_by, 'vote_count.gte': vote_min}
    if language:       base_params['with_original_language'] = language
    if region:         base_params['region']                 = region
    if origin_country: base_params['with_origin_country']   = origin_country

    label = origin_country or language or media_type
    items, seen_ids = [], set()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_fetch_page, media_type, p, base_params, genres_map, origin_country): p
            for p in range(1, pages + 1)
        }
        done = 0
        for fut in as_completed(futures):
            done += 1
            for item in fut.result():
                uid = (item['id'], media_type)
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    items.append(item)
            if done % 10 == 0 or done == pages:
                print(f"  [{label}] {done}/{pages} pages done — {len(items)} titles")

    return items

# OR-separated keyword IDs (pipe = OR in TMDB discover API)
# 5720=gay, 6513=lesbian, 14226=homosexuality, 155341=gay_marriage,
# 13153=coming_of_age+queer, 256428=lgbtq  — pipe = OR, not AND
LGBTQ_KEYWORDS = '5720|6513|14226|155341|256428'

# Text patterns — phrases only, no single words like 'gay' or 'queer'
# (single words cause false positives on kids' shows, historical dramas, etc.)
LGBTQ_TEXT_SIGNALS = (
    'lgbtq', 'bisexual', 'transgender', 'non-binary', 'same-sex',
    'gay couple', 'gay relationship', 'gay romance', 'gay marriage',
    'lesbian couple', 'lesbian relationship', 'lesbian romance',
    'homosexual', 'gay protagonist', 'lesbian protagonist',
    'drag queen', 'drag king',
    'queer romance', 'queer relationship', 'queer love',
    'coming out of the closet',
)

def fetch_lgbtq(media_type, pages=15):
    genres_map = get_genres(media_type)
    name_key   = 'title' if media_type == 'movie' else 'name'
    date_key   = 'release_date' if media_type == 'movie' else 'first_air_date'
    label_type = 'Movie' if media_type == 'movie' else 'TV Show'
    base_params = {
        'api_key': API_KEY, 'with_keywords': LGBTQ_KEYWORDS,
        'sort_by': 'popularity.desc', 'vote_count.gte': 1,
    }
    items, seen_ids = [], set()

    def _fetch_lgbtq_page(page):
        try:
            res = _session.get(f"{BASE_URL}/discover/{media_type}",
                               params={**base_params, 'page': page}, timeout=8).json()
        except Exception:
            return []
        out = []
        for item in res.get('results', []):
            genre_names = [genres_map.get(gid, '') for gid in item.get('genre_ids', [])]
            lang = item.get('original_language', '')
            out.append({
                'id': item['id'], 'title': item.get(name_key, ''), 'type': label_type,
                'genres': ', '.join(g for g in genre_names if g),
                'overview': item.get('overview', ''), 'popularity': item.get('popularity', 0),
                'release_date': item.get(date_key, ''), 'vote_average': item.get('vote_average', 0),
                'vote_count': item.get('vote_count', 0), 'poster_path': item.get('poster_path', ''),
                'backdrop_path': item.get('backdrop_path', ''), 'original_language': lang,
                'origin_country': '',
                'regions': LANG_REGIONS.get(lang, ['US', 'GB', 'CA', 'AU']),
                'tags': item.get('overview', '') + ' ' + ' '.join(genre_names) + ' lgbtq queer',
            })
        return out

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for page_items in pool.map(_fetch_lgbtq_page, range(1, pages + 1)):
            for item in page_items:
                uid = (item['id'], media_type)
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    items.append(item)
    print(f"  [lgbtq {media_type}] {len(items)} titles")
    return items


def _is_kids_content(row):
    """Animation aimed at children — needs a much higher bar for LGBTQ+ tagging."""
    g = str(row.get('genres', '')).lower()
    return 'animation' in g and any(k in g for k in ('family', 'kids', 'children'))

def _text_is_lgbtq(row):
    """
    Fallback: detect LGBTQ+ content from overview text.
    Only tags a title if LGBTQ+ themes are clearly central — mirrors how
    Netflix curates their LGBTQ+ category (not peripheral characters).
    """
    if _is_kids_content(row):
        return False  # never tag kids' animation via text alone
    text = (str(row.get('overview', '')) + ' ' + str(row.get('tags', ''))).lower()
    return any(sig in text for sig in LGBTQ_TEXT_SIGNALS)


def fetch_trending(media_type, pages=10):
    items      = []
    genres_map = get_genres(media_type)
    name_key   = 'title' if media_type == 'movie' else 'name'
    date_key   = 'release_date' if media_type == 'movie' else 'first_air_date'
    label      = 'Movie' if media_type == 'movie' else 'TV Show'
    for page in range(1, pages + 1):
        res = requests.get(f"{BASE_URL}/trending/{media_type}/week",
                           params={'api_key': API_KEY, 'page': page}).json()
        for item in res.get('results', []):
            genre_names = [genres_map.get(gid, '') for gid in item.get('genre_ids', [])]
            lang = item.get('original_language', '')
            items.append({
                'id': item['id'], 'title': item.get(name_key, ''), 'type': label,
                'genres': ', '.join(g for g in genre_names if g),
                'overview': item.get('overview', ''), 'popularity': item.get('popularity', 0),
                'release_date': item.get(date_key, ''), 'vote_average': item.get('vote_average', 0),
                'vote_count': item.get('vote_count', 0), 'poster_path': item.get('poster_path', ''),
                'backdrop_path': item.get('backdrop_path', ''), 'original_language': lang,
                'origin_country': '',
                'regions': LANG_REGIONS.get(lang, ['US', 'GB', 'CA', 'AU']),
                'tags': item.get('overview', '') + ' ' + ' '.join(genre_names),
            })
    return items


all_items = []

# ── Global popular — boosted to 100 pages each (~4 000 titles) ────────
print("\nFetching popular movies (global)…")
all_items += fetch_items('movie', pages=100, vote_min=20, sort_by='popularity.desc')

print("\nFetching popular TV shows (global)…")
all_items += fetch_items('tv', pages=100, vote_min=20, sort_by='popularity.desc')

# ── Recent releases 2024-2026 ─────────────────────────────────────────
print("\nFetching recent movies (2024-2026)…")
all_items += fetch_items('movie', pages=50, vote_min=5, sort_by='primary_release_date.desc')

print("\nFetching recent TV shows (2024-2026)…")
all_items += fetch_items('tv', pages=50, vote_min=5, sort_by='first_air_date.desc')

# ── Trending this week ────────────────────────────────────────────────
print("\nFetching trending movies (week)…")
all_items += fetch_trending('movie', pages=10)

print("\nFetching trending TV shows (week)…")
all_items += fetch_trending('tv', pages=10)

# ── African / Nigerian content — language-based (original) ───────────
AFRICAN_FETCH = [
    ('en',  'NG', 'Nigeria (English)'),
    ('yo',  None, 'Yoruba'),
    ('ig',  None, 'Igbo'),
    ('ha',  None, 'Hausa'),
    ('sw',  None, 'Swahili'),
    ('am',  None, 'Amharic'),
    ('zu',  None, 'Zulu'),
    ('af',  None, 'Afrikaans'),
    ('so',  None, 'Somali'),
    ('fr',  'CI', 'Francophone Africa'),
    ('fr',  'SN', 'Senegal'),
    ('en',  'ZA', 'South Africa'),
    ('en',  'GH', 'Ghana'),
    ('en',  'KE', 'Kenya'),
]

for lang, region, label in AFRICAN_FETCH:
    print(f"\nFetching movies: {label}…")
    all_items += fetch_items('movie', pages=10, vote_min=2, language=lang, region=region, sort_by='popularity.desc')
    print(f"Fetching TV shows: {label}…")
    all_items += fetch_items('tv',    pages=10, vote_min=2, language=lang, region=region, sort_by='popularity.desc')

# ── Nigerian content — origin country (catches all Nollywood languages) ──
# with_origin_country=NG finds every film MADE in Nigeria regardless of language.
# vote_min=0: many Nollywood titles have very few TMDB votes but are real films.
print("\nFetching Nigerian movies (origin country)…")
all_items += fetch_items('movie', pages=25, vote_min=0, origin_country='NG', sort_by='popularity.desc')
print("\nFetching Nigerian TV shows (origin country)…")
all_items += fetch_items('tv',    pages=25, vote_min=0, origin_country='NG', sort_by='popularity.desc')

# ── South African content — origin country ────────────────────────────
print("\nFetching South African movies (origin country)…")
all_items += fetch_items('movie', pages=20, vote_min=0, origin_country='ZA', sort_by='popularity.desc')
print("\nFetching South African TV shows (origin country)…")
all_items += fetch_items('tv',    pages=20, vote_min=0, origin_country='ZA', sort_by='popularity.desc')

# ── Major international languages ─────────────────────────────────────
INTL_LANGS = [
    ('ko', 'Korean'), ('ja', 'Japanese'), ('hi', 'Hindi'),  ('es', 'Spanish'),
    ('fr', 'French'), ('de', 'German'),   ('pt', 'Portuguese'), ('zh', 'Chinese'),
    ('tr', 'Turkish'), ('ar', 'Arabic'),  ('it', 'Italian'), ('ru', 'Russian'),
    ('nl', 'Dutch'),  ('pl', 'Polish'),   ('sv', 'Swedish'),
]
for lang, label in INTL_LANGS:
    print(f"\nFetching {label} content…")
    all_items += fetch_items('movie', pages=10, vote_min=10, language=lang, sort_by='popularity.desc')
    all_items += fetch_items('tv',    pages=10, vote_min=10, language=lang, sort_by='popularity.desc')

# ── LGBTQ+ content (fetched + enriched with keywords & credits) ──────
print("\nFetching LGBTQ+ movies…")
lgbtq_movies = fetch_lgbtq('movie', pages=15)
print("\nFetching LGBTQ+ TV shows…")
lgbtq_tv = fetch_lgbtq('tv', pages=15)

lgbtq_all = lgbtq_movies + lgbtq_tv
enrich_lgbtq_tags(lgbtq_all)
all_items += lgbtq_all

# ── Top-rated catalogue ───────────────────────────────────────────────
print("\nFetching top-rated movies…")
all_items += fetch_items('movie', pages=20, vote_min=100, sort_by='vote_average.desc')

print("\nFetching top-rated TV shows…")
all_items += fetch_items('tv', pages=20, vote_min=100, sort_by='vote_average.desc')

# ── OMDB enrichment — Rotten Tomatoes + Metacritic for top titles ─────
# Only runs if OMDB_KEY is set in .env. Free tier = 1,000 req/day.
# Get a free key at: https://www.omdbapi.com/apikey.aspx
OMDB_KEY = os.environ.get('OMDB_KEY', '').strip()

def enrich_omdb_df(df, limit=1000):
    """
    Fetch RT + Metacritic scores from OMDB for the top `limit` titles by
    popularity. Operates on the final deduplicated DataFrame so enriched
    rows are never discarded. Adds rt_score and metacritic_score columns.
    """
    if not OMDB_KEY:
        print("  (OMDB_KEY not set — skipping RT/Metacritic enrichment)")
        df['rt_score']         = float('nan')
        df['metacritic_score'] = float('nan')
        return df

    df['rt_score']         = float('nan')
    df['metacritic_score'] = float('nan')

    top_idx = df.nlargest(limit, 'popularity').index.tolist()
    print(f"\nEnriching top {limit} titles with OMDB (RT + Metacritic)…")
    enriched = 0

    def _fetch(idx):
        row = df.loc[idx]
        try:
            params = {'apikey': OMDB_KEY, 't': row['title'],
                      'type': 'movie' if row['type'] == 'Movie' else 'series'}
            year = str(row.get('release_date', ''))[:4]
            if year: params['y'] = year
            res = _session.get('https://www.omdbapi.com/', params=params, timeout=5).json()
            if res.get('Response') != 'True':
                return idx, None, None
            rt, mc = None, None
            for rating in res.get('Ratings', []):
                if rating['Source'] == 'Rotten Tomatoes':
                    try: rt = int(rating['Value'].replace('%', ''))
                    except Exception: pass
                if rating['Source'] == 'Metacritic':
                    try: mc = int(rating['Value'].split('/')[0])
                    except Exception: pass
            return idx, rt, mc
        except Exception:
            return idx, None, None

    with ThreadPoolExecutor(max_workers=5) as pool:
        for idx, rt, mc in pool.map(_fetch, top_idx):
            if rt is not None:
                df.at[idx, 'rt_score'] = rt
                enriched += 1
            if mc is not None:
                df.at[idx, 'metacritic_score'] = mc

    print(f"  OMDB enriched: {enriched}/{limit}")
    return df

# ── Merge IMDb supplement if it exists ───────────────────────────────
if os.path.exists('imdb_supplement.pkl'):
    supp = pickle.load(open('imdb_supplement.pkl', 'rb'))
    print(f"\nMerging IMDb supplement: {len(supp)} titles")
    all_items += supp.to_dict('records')
else:
    print("\n(imdb_supplement.pkl not found — run fetch_imdb_supplement.py to add it)")

# ── Deduplicate & build dataset ───────────────────────────────────────
# Track lgbtq IDs before dedup so popular films (Moonlight etc.) keep the tag
lgbtq_ids = {(item['id'], item['type']) for item in lgbtq_all}

df = pd.DataFrame(all_items).drop_duplicates(subset=['id', 'type']).reset_index(drop=True)
df = df[df['title'].str.strip() != '']
df['tags'] = df['tags'].str.lower().fillna('')

# Fill OMDB columns with NaN if not enriched (so flask_app can check .notna())
if 'rt_score'         not in df.columns: df['rt_score']         = float('nan')
if 'metacritic_score' not in df.columns: df['metacritic_score'] = float('nan')

# Pass 1: re-apply lgbtq tag to any title from the keyword fetch
# (dedup may have kept the general-fetch version which has no lgbtq tag)
lgbtq_mask = df.apply(lambda r: (r['id'], r['type']) in lgbtq_ids, axis=1)
df.loc[lgbtq_mask, 'tags'] += ' lgbtq queer same_sex_couple lgbtq_community'
print(f"LGBTQ+ titles via keyword fetch: {lgbtq_mask.sum()}")

# Pass 2: text-based fallback — catches titles missed by keyword search
text_mask = (~lgbtq_mask) & df.apply(_text_is_lgbtq, axis=1)
df.loc[text_mask, 'tags'] += ' lgbtq queer lgbtq_community'
print(f"LGBTQ+ titles via text fallback: {text_mask.sum()}")
print(f"LGBTQ+ titles in dataset (total): {(lgbtq_mask | text_mask).sum()}")

# ── OMDB enrichment — runs AFTER dedup so enriched rows are never dropped ──
df = enrich_omdb_df(df, limit=1000)

print(f"\nTotal entries: {len(df)}")
print(df['type'].value_counts().to_dict())
if 'original_language' in df.columns:
    print("Languages:", df['original_language'].value_counts().head(15).to_dict())

# ── Feature engineering — genres get 3× weight via repetition ────────────
def build_features(row):
    genres  = str(row.get('genres', ''))
    overview = str(row.get('overview', ''))
    lang    = str(row.get('original_language', ''))
    mtype   = str(row.get('type', ''))

    # Normalise genre names to tokens (e.g. "Science Fiction" → "science_fiction")
    genre_tokens = ' '.join(
        g.strip().lower().replace(' ', '_')
        for g in genres.split(',') if g.strip()
    )

    # Year-decade token → temporal similarity signal
    try:
        decade = f"decade_{int(str(row.get('release_date', ''))[:4]) // 10 * 10}"
    except Exception:
        decade = ''

    # Language and type tokens → cultural / format similarity
    lang_tag = f"lang_{lang}" if lang else ''
    type_tag = 'is_movie' if mtype == 'Movie' else 'is_tv'

    # Repeat genre tokens 3× so TF-IDF weights them above free-text overview
    return ' '.join([
        (genre_tokens + ' ') * 3,
        overview.lower(),
        str(row.get('tags', '')).lower(),
        decade, lang_tag, type_tag,
    ])

df['features'] = df.apply(build_features, axis=1)

# ── TF-IDF with bigrams ───────────────────────────────────────────────
print("\nBuilding TF-IDF vectors…")
tfidf = TfidfVectorizer(
    max_features=15000,
    stop_words='english',
    ngram_range=(1, 2),
    min_df=2,
    sublinear_tf=True,
)
vectors = tfidf.fit_transform(df['features'])
N = vectors.shape[0]
print(f"  {N:,} titles × {vectors.shape[1]:,} features")

# ── Sparse top-K similarity index ─────────────────────────────────────
# Only store the top 300 neighbours per title instead of the full N×N
# matrix.  Shrinks similarity.pkl from ~1-6 GB → ~30 MB.
K     = 300
BATCH = 500   # rows processed per chunk — controls peak RAM

print(f"\nBuilding sparse similarity index (top-{K} per title, batch={BATCH})…")
top_k_indices = np.zeros((N, K), dtype=np.int32)
top_k_scores  = np.zeros((N, K), dtype=np.float32)

for start in range(0, N, BATCH):
    end       = min(start + BATCH, N)
    batch_sim = cosine_similarity(vectors[start:end], vectors).astype(np.float32)

    for local_i, global_i in enumerate(range(start, end)):
        row            = batch_sim[local_i]
        row[global_i]  = -1.0          # exclude self

        k_actual = min(K, N - 1)
        top_idx  = np.argpartition(row, -k_actual)[-k_actual:]   # O(N) partition
        top_idx  = top_idx[np.argsort(row[top_idx])[::-1]]       # sort the K items

        top_k_indices[global_i] = top_idx
        top_k_scores[global_i]  = row[top_idx]

    if end % (BATCH * 10) == 0 or end == N:
        print(f"  {end:,}/{N:,} titles indexed…")

similarity = {'indices': top_k_indices, 'scores': top_k_scores}

sim_mb = (top_k_indices.nbytes + top_k_scores.nbytes) / 1e6
print(f"  Sparse index size: {sim_mb:.1f} MB  (was {N*N*8/1e6:.0f} MB full matrix)")

print("\nSaving…")
pickle.dump(df, open('movie_list.pkl', 'wb'))
pickle.dump(similarity, open('similarity.pkl', 'wb'))
print(f"Done — {len(df):,} titles saved. Run: python flask_app.py")
