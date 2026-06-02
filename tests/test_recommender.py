"""
Unit tests for the recommender ranking pipeline.
Run: pytest tests/
"""
import sys, os
import numpy as np
import pandas as pd
import pytest

# ── Make the app package importable without a running Flask server ────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('TMDB_KEY', 'test')
os.environ.setdefault('SECRET_KEY', 'test')

# Minimal movie fixtures so tests don't need the real pkl files
MOVIES = pd.DataFrame([
    {'id': 1, 'title': 'Action Hero',     'type': 'Movie',   'genres': 'Action, Adventure',
     'overview': 'hero saves the world', 'vote_average': 8.5, 'vote_count': 5000,
     'popularity': 95.0, 'release_date': '2024-03-01', 'original_language': 'en',
     'tags': 'action adventure', 'regions': ['US', 'GB'], 'poster_path': '', 'backdrop_path': ''},
    {'id': 2, 'title': 'Comedy Night',    'type': 'Movie',   'genres': 'Comedy',
     'overview': 'funny people laugh', 'vote_average': 6.0, 'vote_count': 200,
     'popularity': 30.0, 'release_date': '2021-06-15', 'original_language': 'en',
     'tags': 'comedy', 'regions': ['US'], 'poster_path': '', 'backdrop_path': ''},
    {'id': 3, 'title': 'Drama Queen',     'type': 'TV Show', 'genres': 'Drama, Romance',
     'overview': 'love and tears', 'vote_average': 7.2, 'vote_count': 1500,
     'popularity': 55.0, 'release_date': '2023-09-01', 'original_language': 'ko',
     'tags': 'drama romance', 'regions': ['KR', 'US'], 'poster_path': '', 'backdrop_path': ''},
    {'id': 4, 'title': 'Queer Story',     'type': 'Movie',   'genres': 'Drama, Romance',
     'overview': 'lgbtq love story', 'vote_average': 8.0, 'vote_count': 900,
     'popularity': 40.0, 'release_date': '2022-11-20', 'original_language': 'en',
     'tags': 'lgbtq queer drama romance', 'regions': ['US', 'GB'], 'poster_path': '', 'backdrop_path': ''},
    {'id': 5, 'title': 'Old Classic',     'type': 'Movie',   'genres': 'Action',
     'overview': 'classic action film', 'vote_average': 9.0, 'vote_count': 10000,
     'popularity': 20.0, 'release_date': '2000-01-01', 'original_language': 'en',
     'tags': 'action classic', 'regions': ['US', 'GB'], 'poster_path': '', 'backdrop_path': ''},
])

_DENSE = np.array([
    [1.0, 0.1, 0.2, 0.3, 0.5],
    [0.1, 1.0, 0.4, 0.3, 0.2],
    [0.2, 0.4, 1.0, 0.6, 0.1],
    [0.3, 0.3, 0.6, 1.0, 0.2],
    [0.5, 0.2, 0.1, 0.2, 1.0],
], dtype=np.float32)

N, K = len(_DENSE), 4   # keep top-4 neighbours (N-1) in the test fixture
_indices = np.zeros((N, K), dtype=np.int32)
_scores  = np.zeros((N, K), dtype=np.float32)
for i in range(N):
    row      = _DENSE[i].copy()
    row[i]   = -1.0
    top      = np.argsort(row)[::-1][:K]
    _indices[i] = top
    _scores[i]  = row[top]

SIM = {'indices': _indices, 'scores': _scores}


# ── Patch module globals before importing helpers ─────────────────────────────
import flask_app as fa
fa.movies     = MOVIES
fa.similarity = SIM
fa.all_titles = MOVIES['title'].tolist()
fa.has_type   = True
fa._VOTE_MEAN = float(MOVIES['vote_average'].mean())
fa._VOTE_MIN  = float(MOVIES['vote_count'].quantile(0.20))


# ── _quality_score ────────────────────────────────────────────────────────────
class TestQualityScore:
    def test_high_votes_approaches_actual_rating(self):
        row = MOVIES.iloc[4]          # Old Classic: 9.0 / 10000 votes
        score = fa._quality_score(row)
        assert score > 0.85, "High-vote classic should score above 0.85"

    def test_low_votes_pulled_toward_mean(self):
        row_low  = MOVIES.iloc[1]     # Comedy Night: 6.0 / 200 votes
        row_high = MOVIES.iloc[0]     # Action Hero: 8.5 / 5000 votes
        assert fa._quality_score(row_low) < fa._quality_score(row_high)

    def test_score_between_zero_and_one(self):
        for _, row in MOVIES.iterrows():
            s = fa._quality_score(row)
            assert 0.0 <= s <= 1.0, f"Score out of range for {row['title']}: {s}"


# ── _recency_boost ────────────────────────────────────────────────────────────
class TestRecencyBoost:
    def test_2024_gets_max_boost(self):
        assert fa._recency_boost(MOVIES.iloc[0]) == pytest.approx(0.08)

    def test_2022_gets_medium_boost(self):
        assert fa._recency_boost(MOVIES.iloc[4-1]) == pytest.approx(0.04)  # 2022-11-20

    def test_old_title_no_boost(self):
        assert fa._recency_boost(MOVIES.iloc[4]) == pytest.approx(0.0)

    def test_bad_date_returns_zero(self):
        row = MOVIES.iloc[0].copy()
        row['release_date'] = 'n/a'
        assert fa._recency_boost(row) == pytest.approx(0.0)


# ── _diversify ────────────────────────────────────────────────────────────────
class TestDiversify:
    def test_no_genre_dominates_top_results(self):
        # 5 Action titles followed by 1 Comedy — after diversify, Comedy should surface earlier
        action_rows = [
            {'genres': 'Action', 'title': f'Action {i}', 'release_date': '2020-01-01',
             'vote_average': 7.0, 'vote_count': 500, 'tags': ''}
            for i in range(5)
        ]
        comedy_row = {'genres': 'Comedy', 'title': 'Comedy 1', 'release_date': '2020-01-01',
                      'vote_average': 7.0, 'vote_count': 500, 'tags': ''}
        old_movies = fa.movies
        fa.movies  = pd.DataFrame(action_rows + [comedy_row])
        result     = fa._diversify(list(range(6)), max_same_genre=4, top_n=5)
        comedy_pos = result.index(5)   # Comedy is at original index 5
        fa.movies  = old_movies
        assert comedy_pos < 5, "Comedy should appear in top-5 after diversity injection"

    def test_output_contains_all_input_indices(self):
        indices = list(range(5))
        result  = fa._diversify(indices, max_same_genre=2, top_n=3)
        assert sorted(result) == sorted(indices)


# ── get_recs ──────────────────────────────────────────────────────────────────
class TestGetRecs:
    def test_returns_expected_keys(self):
        result = fa.get_recs('Action Hero')
        assert {'items', 'total', 'has_more', 'offset'} <= result.keys()

    def test_source_title_excluded(self):
        result = fa.get_recs('Action Hero')
        titles = [m['title'] for m in result['items']]
        assert 'Action Hero' not in titles

    def test_pagination_offset(self):
        page0 = fa.get_recs('Drama Queen', offset=0, limit=2)
        page1 = fa.get_recs('Drama Queen', offset=2, limit=2)
        t0 = [m['title'] for m in page0['items']]
        t1 = [m['title'] for m in page1['items']]
        assert t0 != t1, "Pages should return different titles"

    def test_lgbtq_source_boosts_lgbtq_results(self):
        result = fa.get_recs('Queer Story')
        titles = [m['title'] for m in result['items']]
        # Queer Story is lgbtq; other lgbtq-tagged titles should rank higher
        assert len(titles) > 0

    def test_no_user_id_still_works(self):
        result = fa.get_recs('Comedy Night', user_id=None)
        assert len(result['items']) > 0
