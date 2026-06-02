import requests
import pandas as pd
import pickle
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

API_KEY  = '70132bf555889c9eb211cd36caa030fa'
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

def fetch_items(media_type, pages=25, vote_min=50, language=None, region=None, sort_by='vote_count.desc'):
    items      = []
    genres_map = get_genres(media_type)
    name_key   = 'title' if media_type == 'movie' else 'name'
    date_key   = 'release_date' if media_type == 'movie' else 'first_air_date'
    seen_ids   = set()

    for page in range(1, pages + 1):
        params = {
            'api_key':         API_KEY,
            'sort_by':         sort_by,
            'vote_count.gte':  vote_min,
            'page':            page,
        }
        if language: params['with_original_language'] = language
        if region:   params['region'] = region

        res = requests.get(f"{BASE_URL}/discover/{media_type}", params=params).json()

        for item in res.get('results', []):
            uid = (item['id'], media_type)
            if uid in seen_ids:
                continue
            seen_ids.add(uid)
            genre_names = [genres_map.get(gid, '') for gid in item.get('genre_ids', [])]
            lang = item.get('original_language', '')
            items.append({
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
                'regions':           LANG_REGIONS.get(lang, ['US', 'GB', 'CA', 'AU']),
                'tags':              item.get('overview', '') + ' ' + ' '.join(genre_names),
            })
        print(f"  [{media_type}] page {page}/{pages}" + (f" ({language})" if language else ""))

    return items

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

# ── African / Nigerian content ────────────────────────────────────────
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

# ── Top-rated catalogue ───────────────────────────────────────────────
print("\nFetching top-rated movies…")
all_items += fetch_items('movie', pages=20, vote_min=100, sort_by='vote_average.desc')

print("\nFetching top-rated TV shows…")
all_items += fetch_items('tv', pages=20, vote_min=100, sort_by='vote_average.desc')

# ── Deduplicate & build dataset ───────────────────────────────────────
df = pd.DataFrame(all_items).drop_duplicates(subset=['id', 'type']).reset_index(drop=True)
df = df[df['title'].str.strip() != '']
df['tags'] = df['tags'].str.lower().fillna('')

print(f"\nTotal entries: {len(df)}")
print(df['type'].value_counts().to_dict())
if 'original_language' in df.columns:
    print("Languages:", df['original_language'].value_counts().head(15).to_dict())

print("\nBuilding similarity matrix…")
cv         = CountVectorizer(max_features=10000, stop_words='english')
vectors    = cv.fit_transform(df['tags']).toarray()
similarity = cosine_similarity(vectors)

print("Saving…")
pickle.dump(df, open('movie_list.pkl', 'wb'))
pickle.dump(similarity, open('similarity.pkl', 'wb'))
print(f"Done — {len(df):,} titles saved. Run: python flask_app.py")
