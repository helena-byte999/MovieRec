import streamlit as st
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as cos_sim

POSTER_BASE = "https://image.tmdb.org/t/p/w500"
NO_POSTER   = "https://placehold.co/300x450/1a1a2e/e50914?text=No+Image"
ACCENT      = "#e50914"
GOLD        = "#f5c518"

def init_state():
    for k, v in {
        'dark_mode': True, 'view_mode': 'Grid',
        'results': [], 'selected_title': None, 'watchlist': [],
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

@st.cache_resource
def load_data():
    m = pickle.load(open('movie_list.pkl', 'rb'))
    s = pickle.load(open('similarity.pkl', 'rb'))
    return m, s

@st.cache_resource
def build_search_index(_movies):
    tfidf = TfidfVectorizer(max_features=5000, stop_words='english')
    matrix = tfidf.fit_transform(_movies['tags'].fillna(''))
    return tfidf, matrix

def poster_url(path):
    return f"{POSTER_BASE}{path}" if path and str(path) not in ['nan','None',''] else NO_POSTER

def star_rating(score):
    f = round(score / 2)
    return '★' * f + '☆' * (5 - f)

def badge(label, kind=""):
    return f'<span class="badge{" badge-"+kind if kind else ""}">{label}</span>'

def genre_badges(genres_str, n=3):
    gs = [g.strip() for g in str(genres_str).split(',') if g.strip()][:n]
    return ''.join(badge(g) for g in gs)

def type_badge(row, has_type):
    if not has_type: return ''
    t = row.get('type','Movie') if hasattr(row,'get') else getattr(row,'type','Movie')
    return badge(t, 'movie' if t=='Movie' else 'tv')

def fuzzy_suggest(query, all_titles, n=6):
    if not query: return []
    q = query.lower()
    return [t for t in all_titles if q in t.lower()][:n]

def watchlist_suggest(movies, similarity):
    if not st.session_state.watchlist: return []
    scores = np.zeros(len(movies))
    for title in st.session_state.watchlist:
        if title in movies['title'].values:
            scores += similarity[movies[movies['title']==title].index[0]]
    for title in st.session_state.watchlist:
        if title in movies['title'].values:
            scores[movies[movies['title']==title].index[0]] = 0
    return [movies.iloc[i] for i in scores.argsort()[::-1][:5]]

def get_theme():
    dm = st.session_state.get('dark_mode', True)
    return {
        'dm':      dm,
        'bg':      "#0e1117" if dm else "#f0f2f6",
        'card_bg': "#1c1f2e" if dm else "#ffffff",
        'text':    "#f0f0f0" if dm else "#1a1a2e",
        'subtext': "#9ca3af" if dm else "#6b7280",
        'border':  "#2d3148" if dm else "#e2e8f0",
    }

def inject_css(t):
    dm, bg, card_bg = t['dm'], t['bg'], t['card_bg']
    text, subtext, border = t['text'], t['subtext'], t['border']
    st.markdown(f"""<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"]{{display:none!important;}}
[data-testid="stSidebarNav"]{{display:none!important;}}
.block-container{{padding-top:1.5rem!important;padding-bottom:2rem!important;max-width:100%!important;}}
.stApp{{background:{bg};color:{text};font-family:'Inter',-apple-system,sans-serif;font-size:15px;}}
.sec-title{{font-size:1.15rem;font-weight:800;color:{text};margin:1.4rem 0 .85rem;letter-spacing:-.2px;}}
.card-body{{padding:.85rem;background:{card_bg};border:1px solid {border};border-radius:0 0 12px 12px;margin-top:-3px;}}
.card-title{{font-weight:700;font-size:.9rem;color:{text};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:.25rem;}}
.card-meta{{font-size:.74rem;color:{subtext};margin:.2rem 0;}}
.card-overview{{font-size:.73rem;color:{subtext};line-height:1.5;margin-top:.4rem;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}}
.list-title{{font-weight:700;font-size:1rem;color:{text};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:.25rem;}}
.list-overview{{font-size:.8rem;color:{subtext};line-height:1.5;margin-top:.35rem;}}
.hero-title{{font-size:1.4rem;font-weight:900;color:{text};margin-bottom:.3rem;}}
.hero-overview{{font-size:.86rem;color:{subtext};line-height:1.6;margin-top:.5rem;}}
.ratings-row{{display:flex;gap:.85rem;flex-wrap:wrap;margin-top:.6rem;}}
.rbox{{background:{"#252840" if dm else "#f1f5f9"};border-radius:8px;padding:.35rem .75rem;text-align:center;}}
.rsrc{{font-size:.6rem;color:{subtext};text-transform:uppercase;letter-spacing:.5px;}}
.rval{{font-size:.95rem;font-weight:800;color:{text};}}
.badge{{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.68rem;font-weight:600;margin:2px;background:{"#2d3148" if dm else "#e2e8f0"};color:{subtext};}}
.badge-movie{{background:#1d4ed8;color:#fff;}}
.badge-tv{{background:#7c3aed;color:#fff;}}
.badge-match{{background:#065f46;color:#6ee7b7;}}
.carousel{{display:flex;gap:12px;overflow-x:auto;padding-bottom:8px;scrollbar-width:thin;scrollbar-color:{ACCENT} {card_bg};}}
.c-item{{flex:0 0 148px;background:{card_bg};border:1px solid {border};border-radius:12px;overflow:hidden;transition:transform .2s;}}
.c-item:hover{{transform:scale(1.04);box-shadow:0 8px 28px rgba(229,9,20,.22);}}
.c-item img{{width:100%;height:220px;object-fit:cover;display:block;}}
.c-label{{padding:7px 9px 2px;font-size:.72rem;font-weight:600;color:{text};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.c-rating{{padding:0 9px 7px;font-size:.68rem;color:{GOLD};}}
[data-testid="stMain"] .stButton>button{{background:{ACCENT}!important;color:#fff!important;border:none!important;border-radius:8px!important;font-weight:700!important;transition:opacity .2s!important;}}
[data-testid="stMain"] .stButton>button:hover{{opacity:.85!important;}}
::-webkit-scrollbar{{width:4px;height:4px;}}
::-webkit-scrollbar-thumb{{background:{ACCENT};border-radius:2px;}}
::-webkit-scrollbar-track{{background:{card_bg};}}
#MainMenu,footer{{visibility:hidden;}}
</style>""", unsafe_allow_html=True)

def sidebar_nav(current_page):
    t = get_theme()
    dm = t['dm']
    with st.sidebar:
        st.markdown(f"""<style>
        section[data-testid="stSidebar"]{{background:{"#0d0f1c" if dm else "#1a1e3a"}!important;min-width:200px!important;max-width:200px!important;}}
        section[data-testid="stSidebar"]>div{{padding:2rem 1rem!important;}}
        .nav-logo{{font-size:1.4rem;font-weight:900;letter-spacing:-.5px;color:#fff;margin-bottom:2rem;}}
        .nav-logo span{{color:{ACCENT};}}
        .nav-active{{display:flex;align-items:center;gap:.7rem;padding:.7rem 1rem;border-radius:10px;background:rgba(229,9,20,.16);border-left:3px solid {ACCENT};color:#fff;font-size:.95rem;font-weight:700;margin-bottom:.2rem;}}
        section[data-testid="stSidebar"] .stButton>button{{background:transparent!important;border:none!important;box-shadow:none!important;text-align:left!important;justify-content:flex-start!important;color:#8890b8!important;font-size:.95rem!important;font-weight:500!important;padding:.7rem 1rem!important;border-radius:10px!important;width:100%!important;margin-bottom:.2rem!important;transition:all .15s!important;}}
        section[data-testid="stSidebar"] .stButton>button:hover{{background:rgba(229,9,20,.1)!important;color:#fff!important;}}
        </style>""", unsafe_allow_html=True)

        st.markdown('<div class="nav-logo">Cine<span>Match</span></div>', unsafe_allow_html=True)

        for name, icon in [("Home", "⌂"), ("Watchlist", "☆")]:
            if current_page == name:
                st.markdown(f'<div class="nav-active">{icon}&nbsp;&nbsp;{name}</div>', unsafe_allow_html=True)
            else:
                if st.button(f"{icon}  {name}", key=f"nav_{name}", use_container_width=True):
                    st.session_state.page = name
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        new_dm = st.toggle("Dark mode", value=dm)
        if new_dm != dm:
            st.session_state.dark_mode = new_dm
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.session_state.watchlist:
            wl_count = len(st.session_state.watchlist)
            st.markdown(f"<div style='font-size:.78rem;color:#8890b8'>{wl_count} in Watchlist</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:.7rem;color:#8890b8;margin-top:1rem'>TMDB · Streamlit</div>", unsafe_allow_html=True)

def render_grid(rows, t, has_type):
    cols = st.columns(5)
    for i, row in enumerate(rows):
        with cols[i % 5]:
            yr  = str(row.release_date)[:4]
            ov  = str(row.overview)[:100]+'…' if len(str(row.overview))>100 else str(row.overview)
            st.image(poster_url(row.get('poster_path','')), use_container_width=True)
            st.markdown(f"""<div class="card-body">
                <div class="card-title" title="{row.title}">{row.title}</div>
                <div style="margin:.2rem 0">{type_badge(row,has_type)}{genre_badges(row.genres,2)}</div>
                <div class="card-meta">{yr} · {int(row.vote_count):,} votes</div>
                <div style="color:{GOLD};font-size:.84rem">{star_rating(row.vote_average)}
                    <span style="color:{t['text']};font-weight:700"> {row.vote_average}/10</span>
                </div>
                <div class="card-overview">{ov}</div>
            </div>""", unsafe_allow_html=True)

def render_list(rows, t, has_type):
    for row in rows:
        yr = str(row.release_date)[:4]
        c1, c2 = st.columns([1, 4])
        with c1:
            st.image(poster_url(row.get('poster_path','')), use_container_width=True)
        with c2:
            st.markdown(f"""<div style="padding:.4rem 0">
                <div class="list-title">{row.title}</div>
                <div style="margin:.2rem 0">{type_badge(row,has_type)}{genre_badges(row.genres,3)}</div>
                <div class="card-meta">{yr} · {int(row.vote_count):,} votes</div>
                <div style="color:{GOLD};font-size:.88rem">{star_rating(row.vote_average)}
                    <span style="color:{t['text']};font-weight:700"> {row.vote_average}/10</span>
                </div>
                <div class="list-overview">{row.overview}</div>
            </div>""", unsafe_allow_html=True)
        st.divider()

def show_results(rows, t, has_type):
    if st.session_state.view_mode == 'Grid':
        render_grid(rows, t, has_type)
    else:
        render_list(rows, t, has_type)
