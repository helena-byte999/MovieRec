import requests
import pandas as pd
import pickle
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

API_KEY  = '70132bf555889c9eb211cd36caa030fa'
BASE_URL = 'https://api.themoviedb.org/3'

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
            items.append({
                'id':           item['id'],
                'title':        item.get(name_key, ''),
                'type':         'Movie' if media_type == 'movie' else 'TV Show',
                'genres':       ', '.join(g for g in genre_names if g),
                'overview':     item.get('overview', ''),
                'popularity':   item.get('popularity', 0),
                'release_date': item.get(date_key, ''),
                'vote_average': item.get('vote_average', 0),
                'vote_count':   item.get('vote_count', 0),
                'poster_path':  item.get('poster_path', ''),
                'backdrop_path':item.get('backdrop_path', ''),
                'original_language': item.get('original_language', ''),
                'tags':         item.get('overview', '') + ' ' + ' '.join(genre_names),
            })
        print(f"  [{media_type}] page {page}/{pages}" + (f" ({language})" if language else ""))

    return items

all_items = []

# ── Global popular (English, international) ────────────────────────────
print("\nFetching popular movies (global)…")
all_items += fetch_items('movie', pages=25, vote_min=50)

print("\nFetching popular TV shows (global)…")
all_items += fetch_items('tv', pages=25, vote_min=50)

# ── Recent / trending (catches new releases like Off Campus) ───────────
print("\nFetching trending movies (week)…")
for page in range(1, 6):
    res = requests.get(f"{BASE_URL}/trending/movie/week", params={'api_key': API_KEY, 'page': page}).json()
    genres_map = get_genres('movie')
    for item in res.get('results', []):
        genre_names = [genres_map.get(gid,'') for gid in item.get('genre_ids',[])]
        all_items.append({
            'id': item['id'], 'title': item.get('title',''), 'type': 'Movie',
            'genres': ', '.join(g for g in genre_names if g),
            'overview': item.get('overview',''), 'popularity': item.get('popularity',0),
            'release_date': item.get('release_date',''), 'vote_average': item.get('vote_average',0),
            'vote_count': item.get('vote_count',0), 'poster_path': item.get('poster_path',''),
            'backdrop_path': item.get('backdrop_path',''), 'original_language': item.get('original_language',''),
            'tags': item.get('overview','') + ' ' + ' '.join(genre_names),
        })

print("\nFetching trending TV shows (week)…")
for page in range(1, 6):
    res = requests.get(f"{BASE_URL}/trending/tv/week", params={'api_key': API_KEY, 'page': page}).json()
    genres_map = get_genres('tv')
    for item in res.get('results', []):
        genre_names = [genres_map.get(gid,'') for gid in item.get('genre_ids',[])]
        all_items.append({
            'id': item['id'], 'title': item.get('name',''), 'type': 'TV Show',
            'genres': ', '.join(g for g in genre_names if g),
            'overview': item.get('overview',''), 'popularity': item.get('popularity',0),
            'release_date': item.get('first_air_date',''), 'vote_average': item.get('vote_average',0),
            'vote_count': item.get('vote_count',0), 'poster_path': item.get('poster_path',''),
            'backdrop_path': item.get('backdrop_path',''), 'original_language': item.get('original_language',''),
            'tags': item.get('overview','') + ' ' + ' '.join(genre_names),
        })

# ── African / Nigerian content (Nollywood + African streaming) ─────────
# Lower vote threshold so newer / smaller-audience titles are included
AFRICAN_LANGS = [
    ('en',  'NG', 'Nigeria (English)'),   # Nollywood English
    ('yo',  None, 'Yoruba'),
    ('ig',  None, 'Igbo'),
    ('ha',  None, 'Hausa'),
    ('sw',  None, 'Swahili'),
    ('am',  None, 'Amharic (Ethiopian)'),
    ('zu',  None, 'Zulu'),
    ('af',  None, 'Afrikaans'),
    ('so',  None, 'Somali'),
    ('fr',  'CI', 'Francophone Africa'),
]

for lang, region, label in AFRICAN_LANGS:
    print(f"\nFetching movies: {label}…")
    all_items += fetch_items('movie', pages=5, vote_min=5, language=lang, region=region, sort_by='popularity.desc')
    print(f"Fetching TV shows: {label}…")
    all_items += fetch_items('tv',    pages=5, vote_min=5, language=lang, region=region, sort_by='popularity.desc')

# ── Other major international languages ───────────────────────────────
INTL_LANGS = [
    ('ko', 'Korean'), ('ja', 'Japanese'), ('hi', 'Hindi'), ('es', 'Spanish'),
    ('fr', 'French'), ('de', 'German'),   ('pt', 'Portuguese'), ('zh', 'Chinese'),
    ('tr', 'Turkish'), ('ar', 'Arabic'),
]
for lang, label in INTL_LANGS:
    print(f"\nFetching {label} movies…")
    all_items += fetch_items('movie', pages=5, vote_min=20, language=lang, sort_by='popularity.desc')
    print(f"Fetching {label} TV shows…")
    all_items += fetch_items('tv',    pages=5, vote_min=20, language=lang, sort_by='popularity.desc')

# ── Deduplicate & build dataset ────────────────────────────────────────
df = pd.DataFrame(all_items).drop_duplicates(subset=['id', 'type']).reset_index(drop=True)
df = df[df['title'].str.strip() != '']
df['tags'] = df['tags'].str.lower().fillna('')

print(f"\nTotal entries: {len(df)}")
print(df['type'].value_counts().to_dict())
if 'original_language' in df.columns:
    print("Languages:", df['original_language'].value_counts().head(15).to_dict())

print("\nBuilding similarity matrix…")
cv         = CountVectorizer(max_features=8000, stop_words='english')
vectors    = cv.fit_transform(df['tags']).toarray()
similarity = cosine_similarity(vectors)

print("Saving…")
pickle.dump(df, open('movie_list.pkl', 'wb'))
pickle.dump(similarity, open('similarity.pkl', 'wb'))
print("Done! Run python flask_app.py to start the server.")
