from flask import Flask, render_template, request, jsonify, session
import pickle
import numpy as np
import requests

app = Flask(__name__)
app.secret_key = 'movieerec-secret-2024'

TMDB_KEY      = "70132bf555889c9eb211cd36caa030fa"
POSTER_BASE   = "https://image.tmdb.org/t/p/w500"
BACKDROP_BASE = "https://image.tmdb.org/t/p/original"
LOGO_BASE     = "https://image.tmdb.org/t/p/original"
NO_POSTER     = "https://placehold.co/300x450/1a1a2e/e50914?text=No+Image"

movies     = pickle.load(open('movie_list.pkl', 'rb'))
similarity = pickle.load(open('similarity.pkl', 'rb'))
all_titles = movies['title'].tolist()
has_type   = 'type' in movies.columns

def to_dict(row):
    pp = row.get('poster_path', '') if hasattr(row, 'get') else ''
    bp = row.get('backdrop_path', '') if hasattr(row, 'get') else ''
    return {
        'id':           int(row['id']),
        'title':        str(row['title']),
        'type':         str(row.get('type', 'Movie')) if has_type else 'Movie',
        'genres':       str(row.get('genres', '')),
        'overview':     str(row.get('overview', '')),
        'vote_average': round(float(row.get('vote_average', 0)), 1),
        'vote_count':   int(row.get('vote_count', 0)),
        'popularity':   round(float(row.get('popularity', 0)), 1),
        'year':         str(row.get('release_date', ''))[:4],
        'poster_url':   f"{POSTER_BASE}{pp}" if pp and str(pp) not in ['nan','None',''] else NO_POSTER,
        'backdrop_url': f"{BACKDROP_BASE}{bp}" if bp and str(bp) not in ['nan','None',''] else '',
    }

def get_recs(title):
    idx    = movies[movies['title'] == title].index[0]
    scores = sorted(enumerate(similarity[idx]), reverse=True, key=lambda x: x[1])
    return [to_dict(movies.iloc[i[0]]) for i in scores[1:6]]

# ── Pages ──────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    hero     = to_dict(movies.nlargest(1, 'popularity').iloc[0])
    trending = [to_dict(r) for _, r in movies.nlargest(16, 'popularity').iterrows()]
    mv_list  = [to_dict(r) for _, r in movies[movies['type']=='Movie'].nlargest(10,'popularity').iterrows()] if has_type else trending[:10]
    tv_list  = [to_dict(r) for _, r in movies[movies['type']=='TV Show'].nlargest(10,'popularity').iterrows()] if has_type else []
    return render_template('index.html', hero=hero, trending=trending, mv_list=mv_list, tv_list=tv_list)

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

# ── API ────────────────────────────────────────────────────────────────────────
@app.route('/api/search')
def search():
    q = request.args.get('q','').lower()
    if not q: return jsonify([])
    return jsonify([t for t in all_titles if q in t.lower()][:8])

@app.route('/api/recommend', methods=['POST'])
def recommend():
    title = request.json.get('title','')
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
    is_tv = request.args.get('tv','false') == 'true'
    media = 'tv' if is_tv else 'movie'
    try:
        res = requests.get(f"https://api.themoviedb.org/3/{media}/{tmdb_id}/watch/providers",
                           params={'api_key': TMDB_KEY}, timeout=4).json().get('results',{})
        for region in ['US','GB','AU','CA']:
            if region in res:
                flat = res[region].get('flatrate',[])
                if flat: return jsonify(flat)
    except: pass
    return jsonify([])

@app.route('/api/watchlist/add', methods=['POST'])
def wl_add():
    title = request.json.get('title','')
    if 'watchlist' not in session: session['watchlist'] = []
    if title in all_titles and title not in session['watchlist']:
        session['watchlist'] = session['watchlist'] + [title]
    return jsonify({'count': len(session['watchlist'])})

@app.route('/api/watchlist/remove', methods=['POST'])
def wl_remove():
    title = request.json.get('title','')
    if 'watchlist' in session:
        session['watchlist'] = [t for t in session['watchlist'] if t != title]
    return jsonify({'count': len(session.get('watchlist',[]))})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
