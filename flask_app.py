from flask import Flask, render_template, request, jsonify, session
import pickle
import numpy as np
import requests

app = Flask(__name__)
app.secret_key = 'movieerec-secret-2024'

TMDB_KEY      = "70132bf555889c9eb211cd36caa030fa"
POSTER_BASE   = "https://image.tmdb.org/t/p/w500"
BACKDROP_BASE = "https://image.tmdb.org/t/p/original"
NO_POSTER     = "https://placehold.co/300x450/1a1a2e/e50914?text=No+Image"

# ── Language → likely available regions ────────────────────────────────────
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
    'da':  ['DK'],
    'fi':  ['FI'],
    'yo':  ['NG','GH'],
    'ig':  ['NG'],
    'ha':  ['NG','GH','NE'],
    'sw':  ['KE','TZ','UG','RW'],
    'am':  ['ET'],
    'zu':  ['ZA'],
    'af':  ['ZA','NA'],
    'so':  ['SO','ET','KE'],
}

AFRICAN_LANGS = {'yo', 'ig', 'ha', 'sw', 'am', 'zu', 'af', 'so'}

REGIONS_LIST = [
    ('GLOBAL', '🌍 Global (All)'),
    ('US',     '🇺🇸 United States'),
    ('GB',     '🇬🇧 United Kingdom'),
    ('CA',     '🇨🇦 Canada'),
    ('AU',     '🇦🇺 Australia'),
    ('NG',     '🇳🇬 Nigeria'),
    ('ZA',     '🇿🇦 South Africa'),
    ('GH',     '🇬🇭 Ghana'),
    ('KE',     '🇰🇪 Kenya'),
    ('ET',     '🇪🇹 Ethiopia'),
    ('IN',     '🇮🇳 India'),
    ('KR',     '🇰🇷 South Korea'),
    ('JP',     '🇯🇵 Japan'),
    ('FR',     '🇫🇷 France'),
    ('DE',     '🇩🇪 Germany'),
    ('ES',     '🇪🇸 Spain'),
    ('BR',     '🇧🇷 Brazil'),
    ('MX',     '🇲🇽 Mexico'),
    ('TR',     '🇹🇷 Turkey'),
    ('AE',     '🇦🇪 UAE'),
    ('SA',     '🇸🇦 Saudi Arabia'),
    ('EG',     '🇪🇬 Egypt'),
]

# ── Genre row definitions ───────────────────────────────────────────────────
GENRE_ROWS = [
    ('Action & Adventure', ['Action', 'Adventure']),
    ('Crime & Thriller',   ['Crime', 'Thriller', 'Mystery']),
    ('Comedy',             ['Comedy']),
    ('Drama',              ['Drama']),
    ('Sci-Fi & Fantasy',   ['Science Fiction', 'Fantasy']),
    ('Horror',             ['Horror']),
    ('Romance',            ['Romance']),
    ('Documentary',        ['Documentary']),
    ('Animation',          ['Animation']),
    ('Family & Kids',      ['Family', 'Kids']),
    ('History & War',      ['History', 'War']),
]

# ── Load data ───────────────────────────────────────────────────────────────
movies     = pickle.load(open('movie_list.pkl', 'rb'))
similarity = pickle.load(open('similarity.pkl', 'rb'))

# Derive regions from original_language if not already in the pkl
if 'regions' not in movies.columns:
    movies['regions'] = movies['original_language'].apply(
        lambda lang: LANG_REGIONS.get(str(lang), ['US', 'GB', 'CA', 'AU'])
    )

all_titles = movies['title'].tolist()
has_type   = 'type' in movies.columns


@app.context_processor
def inject_nav_context():
    return {
        'regions_list':   REGIONS_LIST,
        'current_region': session.get('region', 'GLOBAL'),
    }


def to_dict(row):
    pp = row.get('poster_path', '') if hasattr(row, 'get') else ''
    bp = row.get('backdrop_path', '') if hasattr(row, 'get') else ''
    return {
        'id':                int(row['id']),
        'title':             str(row['title']),
        'type':              str(row.get('type', 'Movie')) if has_type else 'Movie',
        'genres':            str(row.get('genres', '')),
        'overview':          str(row.get('overview', '')),
        'vote_average':      round(float(row.get('vote_average', 0)), 1),
        'vote_count':        int(row.get('vote_count', 0)),
        'popularity':        round(float(row.get('popularity', 0)), 1),
        'year':              str(row.get('release_date', ''))[:4],
        'poster_url':        f"{POSTER_BASE}{pp}" if pp and str(pp) not in ['nan','None',''] else NO_POSTER,
        'backdrop_url':      f"{BACKDROP_BASE}{bp}" if bp and str(bp) not in ['nan','None',''] else '',
        'original_language': str(row.get('original_language', '')),
    }


def get_pool(region):
    if region == 'GLOBAL':
        return movies
    pool = movies[movies['regions'].apply(lambda r: isinstance(r, list) and region in r)]
    return pool if len(pool) >= 20 else movies


def build_row(label, pool, min_items=4, n=20, sort_col='popularity'):
    items = [to_dict(r) for _, r in pool.nlargest(n, sort_col).iterrows()]
    return {'label': label, 'items': items} if len(items) >= min_items else None


def get_recs(title):
    idx    = movies[movies['title'] == title].index[0]
    scores = sorted(enumerate(similarity[idx]), reverse=True, key=lambda x: x[1])
    return [to_dict(movies.iloc[i[0]]) for i in scores[1:6]]


# ── Pages ───────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    region = session.get('region', 'GLOBAL')
    pool   = get_pool(region)
    hero   = to_dict(pool.nlargest(1, 'popularity').iloc[0])
    rows   = []

    row = build_row('Trending Now', pool)
    if row: rows.append(row)

    if has_type:
        mv = build_row('Top Movies',   pool[pool['type'] == 'Movie'])
        tv = build_row('Top TV Shows', pool[pool['type'] == 'TV Show'])
        if mv: rows.append(mv)
        if tv: rows.append(tv)

    for label, tags in GENRE_ROWS:
        subset = pool[pool['genres'].apply(lambda g: any(t in str(g) for t in tags))]
        row    = build_row(label, subset)
        if row: rows.append(row)

    african = pool[pool['original_language'].isin(AFRICAN_LANGS)]
    row = build_row('African Stories', african)
    if row: rows.append(row)

    korean = pool[pool['original_language'] == 'ko']
    row = build_row('K-Drama & Korean Cinema', korean)
    if row: rows.append(row)

    anime = pool[(pool['original_language'] == 'ja') &
                 pool['genres'].apply(lambda g: 'Animation' in str(g))]
    row = build_row('Anime', anime)
    if row: rows.append(row)

    bollywood = pool[pool['original_language'] == 'hi']
    row = build_row('Bollywood & Indian Cinema', bollywood)
    if row: rows.append(row)

    acclaimed = pool[(pool['vote_average'] >= 8.0) & (pool['vote_count'] >= 500)]
    row = build_row('Critically Acclaimed', acclaimed, sort_col='vote_count')
    if row: rows.append(row)

    return render_template('index.html', hero=hero, genre_rows=rows, region=region)


@app.route('/watchlist')
def watchlist_page():
    wl_titles = session.get('watchlist', [])
    wl_items  = [to_dict(movies[movies['title']==t].iloc[0]) for t in wl_titles if not movies[movies['title']==t].empty]
    suggestions = []
    if wl_titles:
        sc = np.zeros(len(movies))
        for t in wl_titles:
            if t in movies['title'].values:
                sc += similarity[movies[movies['title']==t].index[0]]
        for t in wl_titles:
            if t in movies['title'].values:
                sc[movies[movies['title']==t].index[0]] = 0
        suggestions = [to_dict(movies.iloc[i]) for i in sc.argsort()[::-1][:5]]
    return render_template('watchlist.html', watchlist=wl_items, suggestions=suggestions)


# ── API ─────────────────────────────────────────────────────────────────────
@app.route('/api/search')
def search():
    q = request.args.get('q', '').lower()
    if not q: return jsonify([])
    return jsonify([t for t in all_titles if q in t.lower()][:8])


@app.route('/api/recommend', methods=['POST'])
def recommend():
    title = request.json.get('title', '')
    if title not in all_titles:
        matches = [t for t in all_titles if title.lower() in t.lower()]
        if not matches:
            return jsonify({'error': 'Not found'}), 404
        title = matches[0]
    return jsonify({'selected': to_dict(movies[movies['title']==title].iloc[0]),
                    'results':  get_recs(title)})


@app.route('/api/random')
def random_pick():
    row   = movies.sample(1).iloc[0]
    title = row['title']
    return jsonify({'selected': to_dict(row), 'results': get_recs(title)})


@app.route('/api/providers/<int:tmdb_id>')
def providers(tmdb_id):
    is_tv       = request.args.get('tv', 'false') == 'true'
    media       = 'tv' if is_tv else 'movie'
    user_region = session.get('region', 'GLOBAL')
    try:
        res = requests.get(
            f"https://api.themoviedb.org/3/{media}/{tmdb_id}/watch/providers",
            params={'api_key': TMDB_KEY}, timeout=4
        ).json().get('results', {})
        check = ([user_region] if user_region != 'GLOBAL' else []) + ['US', 'GB', 'AU', 'CA']
        for r in check:
            if r in res:
                flat = res[r].get('flatrate', [])
                if flat: return jsonify(flat)
    except: pass
    return jsonify([])


@app.route('/api/detect_region')
def detect_region():
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        if ip in ('127.0.0.1', '::1'):
            return jsonify({'country_code': 'GLOBAL'})
        res = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=3).json()
        return jsonify({'country_code': res.get('countryCode', 'GLOBAL')})
    except:
        return jsonify({'country_code': 'GLOBAL'})


@app.route('/api/set_region', methods=['POST'])
def set_region():
    region = request.json.get('region', 'GLOBAL')
    session['region'] = region
    return jsonify({'region': region})


@app.route('/api/watchlist/add', methods=['POST'])
def wl_add():
    title = request.json.get('title', '')
    if 'watchlist' not in session: session['watchlist'] = []
    if title in all_titles and title not in session['watchlist']:
        session['watchlist'] = session['watchlist'] + [title]
    return jsonify({'count': len(session['watchlist'])})


@app.route('/api/watchlist/remove', methods=['POST'])
def wl_remove():
    title = request.json.get('title', '')
    if 'watchlist' in session:
        session['watchlist'] = [t for t in session['watchlist'] if t != title]
    return jsonify({'count': len(session.get('watchlist', []))})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
