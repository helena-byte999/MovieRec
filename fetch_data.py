import requests
import pandas as pd
import pickle
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

API_KEY = '70132bf555889c9eb211cd36caa030fa'
BASE_URL = 'https://api.themoviedb.org/3'

def get_genres(media_type):
    url = f"{BASE_URL}/genre/{media_type}/list"
    res = requests.get(url, params={'api_key': API_KEY}).json()
    return {g['id']: g['name'] for g in res['genres']}

def fetch_items(media_type, pages=20):
    items = []
    genres_map = get_genres(media_type)
    name_key = 'title' if media_type == 'movie' else 'name'
    date_key = 'release_date' if media_type == 'movie' else 'first_air_date'

    for page in range(1, pages + 1):
        res = requests.get(
            f"{BASE_URL}/discover/{media_type}",
            params={
                'api_key': API_KEY,
                'sort_by': 'vote_count.desc',
                'vote_count.gte': 100,
                'page': page
            }
        ).json()

        for item in res.get('results', []):
            genre_names = [genres_map.get(gid, '') for gid in item.get('genre_ids', [])]
            items.append({
                'id': item['id'],
                'title': item.get(name_key, ''),
                'type': 'Movie' if media_type == 'movie' else 'TV Show',
                'genres': ', '.join(genre_names),
                'overview': item.get('overview', ''),
                'popularity': item.get('popularity', 0),
                'release_date': item.get(date_key, ''),
                'vote_average': item.get('vote_average', 0),
                'vote_count': item.get('vote_count', 0),
                'poster_path': item.get('poster_path', ''),
                'backdrop_path': item.get('backdrop_path', ''),
                'tags': item.get('overview', '') + ' ' + ' '.join(genre_names)
            })
        print(f"  Fetched {media_type} page {page}/{pages}")

    return items

print("Fetching movies...")
movies = fetch_items('movie', pages=25)

print("Fetching TV shows...")
tv_shows = fetch_items('tv', pages=25)

df = pd.DataFrame(movies + tv_shows).drop_duplicates(subset=['id', 'type']).reset_index(drop=True)
df['tags'] = df['tags'].str.lower()

print(f"\nTotal entries: {len(df)} ({df['type'].value_counts().to_dict()})")

print("Building similarity matrix...")
cv = CountVectorizer(max_features=5000, stop_words='english')
vectors = cv.fit_transform(df['tags']).toarray()
similarity = cosine_similarity(vectors)

print("Saving files...")
pickle.dump(df, open('movie_list.pkl', 'wb'))
pickle.dump(similarity, open('similarity.pkl', 'wb'))

print("Done! movie_list.pkl and similarity.pkl updated.")
