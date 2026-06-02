"""
IMDb Non-Commercial Dataset Supplement
=======================================
Source:  https://datasets.imdbws.com/
License: Non-commercial use only — https://developer.imdb.com/non-commercial-datasets/

Downloads IMDb title data, finds Nigerian / South African (and other African)
titles that TMDB may not surface well, then looks each one up on TMDB to get
poster images, streaming providers, and full metadata.

Run AFTER fetch_data.py:
    python fetch_imdb_supplement.py

Outputs:
    imdb_supplement.pkl  — extra titles to merge into movie_list.pkl

Then re-run the similarity build:
    python build_similarity.py    (or just re-run fetch_data.py)
"""

import os, gzip, io, pickle, time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
TMDB_KEY = os.environ.get('TMDB_KEY', '')
BASE_URL = 'https://api.themoviedb.org/3'
POSTER_BASE   = 'https://image.tmdb.org/t/p/w500'
BACKDROP_BASE = 'https://image.tmdb.org/t/p/original'
NO_POSTER     = 'https://placehold.co/300x450/1a1a2e/59005c?text=No+Image'

# ── Countries we want to supplement ──────────────────────────────────────────
TARGET_COUNTRIES = {
    'NG',   # Nigeria
    'ZA',   # South Africa
    'GH',   # Ghana
    'KE',   # Kenya
    'ET',   # Ethiopia
    'TZ',   # Tanzania
    'CM',   # Cameroon
    'SN',   # Senegal
    'CI',   # Côte d'Ivoire
    'RW',   # Rwanda
    'UG',   # Uganda
}

IMDB_BASE = 'https://datasets.imdbws.com'

LANG_REGIONS = {
    'en':  ['US','GB','CA','AU','NZ','ZA','NG','GH','IE'],
    'fr':  ['FR','BE','CA','CH','CI','SN','CM','MG'],
    'yo':  ['NG','GH'],
    'ig':  ['NG'],
    'ha':  ['NG','GH','NE'],
    'sw':  ['KE','TZ','UG','RW'],
    'am':  ['ET'],
    'zu':  ['ZA'],
    'af':  ['ZA','NA'],
}


def download_tsv(filename):
    """Stream-download and decompress an IMDb .tsv.gz file into a DataFrame."""
    url = f"{IMDB_BASE}/{filename}"
    print(f"  Downloading {filename}…")
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with gzip.open(io.BytesIO(resp.content), 'rt', encoding='utf-8') as f:
        df = pd.read_csv(f, sep='\t', na_values=['\\N'], low_memory=False)
    print(f"  {filename}: {len(df):,} rows")
    return df


def tmdb_find_by_imdb(imdb_id, media_type):
    """
    Use TMDB's /find endpoint to get full TMDB metadata from an IMDb ID.
    Returns a dict or None.
    """
    try:
        res = requests.get(
            f"{BASE_URL}/find/{imdb_id}",
            params={'api_key': TMDB_KEY, 'external_source': 'imdb_id'},
            timeout=5
        ).json()
        key = 'movie_results' if media_type == 'movie' else 'tv_results'
        results = res.get(key, [])
        return results[0] if results else None
    except Exception:
        return None


def build_item(tmdb_item, media_type, origin_country, lang):
    name_key = 'title' if media_type == 'movie' else 'name'
    date_key = 'release_date' if media_type == 'movie' else 'first_air_date'
    pp = tmdb_item.get('poster_path')   or ''
    bp = tmdb_item.get('backdrop_path') or ''
    base_regions = LANG_REGIONS.get(lang, [])
    if origin_country not in base_regions:
        base_regions = [origin_country] + base_regions
    return {
        'id':                tmdb_item['id'],
        'title':             tmdb_item.get(name_key, ''),
        'type':              'Movie' if media_type == 'movie' else 'TV Show',
        'genres':            '',   # genre IDs need a separate call; left blank — TMDB fetch fills these
        'overview':          tmdb_item.get('overview', ''),
        'popularity':        tmdb_item.get('popularity', 0),
        'release_date':      tmdb_item.get(date_key, ''),
        'vote_average':      tmdb_item.get('vote_average', 0),
        'vote_count':        tmdb_item.get('vote_count', 0),
        'poster_path':       pp,
        'backdrop_path':     bp,
        'original_language': lang,
        'regions':           base_regions,
        'tags':              tmdb_item.get('overview', ''),
        'poster_url':        f"{POSTER_BASE}{pp}" if pp else NO_POSTER,
        'backdrop_url':      f"{BACKDROP_BASE}{bp}" if bp else '',
    }


def main():
    print("=" * 60)
    print("IMDb Non-Commercial Dataset Supplement")
    print("License: Non-commercial use only (portfolio/personal)")
    print("=" * 60)

    # ── Step 1: Download IMDb basics + ratings ────────────────────────
    print("\n[1/4] Downloading IMDb datasets…")
    basics  = download_tsv('title.basics.tsv.gz')
    ratings = download_tsv('title.ratings.tsv.gz')

    # ── Step 2: Download title.akas for country filtering ─────────────
    print("\n[2/4] Downloading title region data (akas)…")
    akas = download_tsv('title.akas.tsv.gz')

    # Find IMDb IDs released/produced in target African countries
    african_ids = set(
        akas[akas['region'].isin(TARGET_COUNTRIES)]['titleId'].dropna()
    )
    print(f"  IMDb titles linked to target countries: {len(african_ids):,}")

    # ── Step 3: Filter to movies + TV series with decent ratings ──────
    print("\n[3/4] Filtering titles…")
    keep_types = {'movie', 'tvMovie', 'tvSeries', 'tvMiniSeries'}
    filtered = basics[
        basics['tconst'].isin(african_ids) &
        basics['titleType'].isin(keep_types) &
        basics['primaryTitle'].notna()
    ].copy()

    # Merge ratings
    filtered = filtered.merge(ratings, on='tconst', how='left')

    # Keep titles with ≥ 10 votes OR no rating info (might be new/uncatalogued)
    filtered = filtered[
        (filtered['numVotes'].isna()) |
        (filtered['numVotes'] >= 10)
    ]

    print(f"  Titles after filtering: {len(filtered):,}")

    # Sort by votes descending so we hit the most popular first
    filtered = filtered.sort_values('numVotes', ascending=False, na_position='last')

    # ── Step 4: Look each up on TMDB ──────────────────────────────────
    # Load existing pkl to skip titles we already have
    existing_ids = set()
    if os.path.exists('movie_list.pkl'):
        existing_df = pickle.load(open('movie_list.pkl', 'rb'))
        existing_ids = set(existing_df['id'].tolist())
        print(f"\n[4/4] Looking up on TMDB (skipping {len(existing_ids):,} already in dataset)…")
    else:
        print("\n[4/4] Looking up on TMDB…")

    new_items = []
    seen_tmdb = set(existing_ids)

    for i, row in filtered.iterrows():
        imdb_id  = row['tconst']
        is_movie = row['titleType'] in ('movie', 'tvMovie')
        media    = 'movie' if is_movie else 'tv'

        tmdb = tmdb_find_by_imdb(imdb_id, media)
        if not tmdb:
            continue

        tmdb_id = tmdb['id']
        if tmdb_id in seen_tmdb:
            continue
        seen_tmdb.add(tmdb_id)

        lang = tmdb.get('original_language', 'en')

        # Determine most likely origin country from akas data
        title_countries = akas[akas['titleId'] == imdb_id]['region'].dropna().tolist()
        origin = next((c for c in title_countries if c in TARGET_COUNTRIES), 'NG')

        new_items.append(build_item(tmdb, media, origin, lang))

        if len(new_items) % 50 == 0:
            print(f"  {len(new_items)} new titles found…")

        time.sleep(0.06)  # ~16 req/s — within TMDB rate limit

    print(f"\nNew titles to add: {len(new_items)}")

    if not new_items:
        print("Nothing new found — dataset is already comprehensive for these countries.")
        return

    # Save supplement
    supp_df = pd.DataFrame(new_items)
    pickle.dump(supp_df, open('imdb_supplement.pkl', 'wb'))
    print(f"Saved to imdb_supplement.pkl")
    print("\nNext step: run fetch_data.py (it will automatically merge this file)")


if __name__ == '__main__':
    main()
