import streamlit as st
from utils import (
    init_state, load_data, build_search_index, get_theme, inject_css,
    show_results, poster_url, star_rating,
    genre_badges, type_badge, fuzzy_suggest, watchlist_suggest, ACCENT, GOLD
)

st.set_page_config(page_title="MOV.IE REC", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")

init_state()
movies, similarity = load_data()
build_search_index(movies)
all_titles = movies['title'].tolist()
has_type   = 'type' in movies.columns

t = get_theme()
dm, text, subtext, card_bg, border = t['dm'], t['text'], t['subtext'], t['card_bg'], t['border']

BACKDROP_BASE = "https://image.tmdb.org/t/p/original"

inject_css(t)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown(f"""<style>
/* Hide sidebar & collapse button */
section[data-testid="stSidebar"] {{ display:none!important; }}
button[data-testid="collapsedControl"] {{ display:none!important; }}
[data-testid="stSidebarCollapsedControl"] {{ display:none!important; }}
header[data-testid="stHeader"] {{ display:none!important; }}
.block-container {{ padding-top:0!important; padding-left:0!important; padding-right:0!important; max-width:100%!important; }}

/* Navbar floats over hero */
.nb-row {{
    position:relative; z-index:100;
    margin-bottom:-68px;
    background:transparent!important;
}}
.nb-row > div,
.nb-row [data-testid="stHorizontalBlock"],
.nb-row [data-testid="stColumn"],
.nb-row [data-testid="column"],
.nb-row .element-container,
.nb-row .stButton {{
    background:transparent!important;
}}
/* Remove ALL vertical padding/gap Streamlit adds between the navbar and hero */
.nb-row [data-testid="stHorizontalBlock"] {{ gap:0!important; padding:0!important; }}

/* Transparent navbar */
.topnav {{
    display:flex; align-items:center; justify-content:space-between;
    padding:.85rem 2.5rem;
    background:transparent;
    position:relative; z-index:10;
}}
.topnav-logo {{
    font-size:1.3rem; font-weight:900; letter-spacing:-.5px; color:#fff;
}}
.topnav-logo span {{ color:{ACCENT}; }}
.topnav-links {{ display:flex; gap:.3rem; align-items:center; }}
.topnav-link {{
    padding:.42rem 1.1rem; border-radius:20px;
    font-size:.88rem; font-weight:600; color:rgba(255,255,255,.65);
    cursor:pointer; transition:all .15s; text-decoration:none;
    border:none; background:transparent;
}}
.topnav-link:hover {{ color:#fff; background:rgba(255,255,255,.1); }}
.topnav-link.active {{
    background:rgba(229,9,20,.2); color:#fff;
    border:1px solid rgba(229,9,20,.4);
}}
.topnav-right {{ display:flex; align-items:center; gap:.5rem; }}

/* Navbar button overrides */
.nb-wrap .stButton>button {{
    background:transparent!important; border:none!important;
    box-shadow:none!important; color:rgba(255,255,255,.6)!important;
    font-size:.92rem!important; font-weight:600!important;
    padding:.5rem 1.4rem!important; border-radius:6px!important;
    transition:background .15s,color .15s!important;
    white-space:nowrap!important; min-height:0!important;
    letter-spacing:.1px!important;
}}
.nb-wrap .stButton>button:hover {{
    color:#fff!important;
    background:rgba(229,9,20,.18)!important;
}}
.nb-active .stButton>button {{
    background:rgba(229,9,20,.32)!important;
    color:#fff!important; font-weight:700!important;
}}
.nb-dm .stButton>button {{
    background:transparent!important; border:none!important;
    color:rgba(255,255,255,.6)!important; padding:.4rem .8rem!important;
    border-radius:6px!important; font-size:.9rem!important;
}}
.nb-dm .stButton>button:hover {{
    background:rgba(229,9,20,.18)!important; color:#fff!important;
}}

/* Hero */
.hero-outer {{
    position:relative; width:100%; overflow:hidden;
    min-height:420px; margin-bottom:2rem;
}}
.hero-bg {{
    position:absolute; inset:0; width:100%; height:100%;
    object-fit:cover; object-position:center 20%;
    opacity:.5; display:block;
}}
.hero-grad {{
    position:absolute; inset:0;
    background:linear-gradient(to right, rgba(10,12,20,.97) 38%, rgba(10,12,20,.5) 70%, transparent 100%);
}}
.hero-grad-bottom {{
    position:absolute; bottom:0; left:0; right:0; height:120px;
    background:linear-gradient(to top, {"#0a0c14" if dm else "#f0f2f6"}, transparent);
}}
.hero-content {{
    position:relative; z-index:2;
    padding:5.5rem 2.5rem 2.5rem; max-width:580px;
}}
.hero-eyebrow {{
    font-size:.7rem; font-weight:800; letter-spacing:2.5px;
    color:{ACCENT}; text-transform:uppercase; margin-bottom:.8rem;
    display:flex; align-items:center; gap:.4rem;
}}
.hero-title {{
    font-size:3rem; font-weight:900; color:#fff;
    line-height:1.05; letter-spacing:-.5px; margin-bottom:.75rem;
    text-transform:uppercase;
}}
.hero-meta {{
    color:{GOLD}; font-size:.88rem; margin-bottom:.8rem;
    display:flex; align-items:center; gap:.5rem;
}}
.hero-overview {{
    font-size:.88rem; color:rgba(255,255,255,.72);
    line-height:1.7; max-width:500px;
    display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;
}}

/* Carousel + cards */
.sec-pad {{ padding:0 2.5rem; }}
.sec-title {{ font-size:1.05rem; font-weight:800; color:{text}; margin:1.6rem 0 .8rem; padding:0 2.5rem; }}

[data-testid="stMain"] .stButton>button {{
    background:{ACCENT}!important; color:#fff!important; border:none!important;
    border-radius:8px!important; font-weight:700!important; font-size:.85rem!important;
    transition:opacity .2s!important;
}}
[data-testid="stMain"] .stButton>button:hover {{ opacity:.85!important; }}
</style>""", unsafe_allow_html=True)

def get_recs(title):
    idx = movies[movies['title'] == title].index[0]
    scores = sorted(enumerate(similarity[idx]), reverse=True, key=lambda x: x[1])
    return [movies.iloc[i[0]] for i in scores[1:6]]

page = st.session_state.get('page', 'Home')

# ── Transparent top navbar (floats over hero) ──────────────────────────────────
st.markdown('<div class="nb-row"><div class="nb-wrap">', unsafe_allow_html=True)
nb1, nb_sp1, nb2, nb3, nb_sp2, nb4 = st.columns([2, 3, 1, 1, 3, 1])

with nb1:
    st.markdown("<div style='padding:.5rem 0 0 .5rem;font-size:1.2rem;font-weight:900'><span style='color:#fff'>MOV.IE</span><span style='color:#9333ea'> REC</span></div>", unsafe_allow_html=True)

for name, col in [("Home", nb2), ("Watchlist", nb3)]:
    with col:
        if page == name:
            st.markdown('<div class="nb-active">', unsafe_allow_html=True)
        if st.button(name, key=f"nav_{name}", use_container_width=True):
            if page != name:
                st.session_state.page = name
                st.rerun()
        if page == name:
            st.markdown('</div>', unsafe_allow_html=True)

with nb4:
    st.markdown('<div class="nb-dm">', unsafe_allow_html=True)
    if st.button("☀️" if dm else "🌙", key="dm_tog", use_container_width=True):
        st.session_state.dark_mode = not dm
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════════
# HOME
# ════════════════════════════════════════════════════════════════════════════════
if page == 'Home':

    # ── Hero ───────────────────────────────────────────────────────────────────
    hero = movies.nlargest(1, 'popularity').iloc[0]
    bd   = hero.get('backdrop_path', '')
    bd_url = f"{BACKDROP_BASE}{bd}" if bd and str(bd) not in ['nan','None',''] else ''
    yr_h = str(hero.release_date)[:4]
    ov_h = str(hero.overview)[:220] + '…' if len(str(hero.overview)) > 220 else str(hero.overview)

    st.markdown(f"""<div class="hero-outer">
        {"<img class='hero-bg' src='"+bd_url+"' alt='"+hero.title+"'/>" if bd_url else f"<div class='hero-bg' style='background:linear-gradient(135deg,#1a1a2e,#16213e)'></div>"}
        <div class="hero-grad"></div>
        <div class="hero-grad-bottom"></div>
        <div class="hero-content">
            <div class="hero-eyebrow">🔥 Trending</div>
            <div class="hero-title">{hero.title}</div>
            <div style="margin-bottom:.75rem">{type_badge(hero, has_type)}{genre_badges(hero.genres, 4)}</div>
            <div class="hero-meta">
                {'★' * round(hero.vote_average/2)}{'☆' * (5-round(hero.vote_average/2))}
                &nbsp;<strong>{hero.vote_average}/10</strong>&nbsp;·&nbsp;{yr_h}
            </div>
            <div class="hero-overview">{ov_h}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── Trending carousel ──────────────────────────────────────────────────────
    st.markdown('<div class="sec-title">Trending Now</div>', unsafe_allow_html=True)
    trending = movies.nlargest(16, 'popularity')
    c_html = '<div class="carousel" style="padding:0 2.5rem 1rem">'
    for _, r in trending.iterrows():
        lbl = r.title[:22] + '…' if len(r.title) > 22 else r.title
        c_html += f"""<div class="c-item" title="{r.title}">
            <img src="{poster_url(r.get('poster_path',''))}" alt="{r.title}" loading="lazy"/>
            <div class="c-label">{lbl}</div>
            <div class="c-rating">{star_rating(r.vote_average)} {r.vote_average}</div>
        </div>"""
    st.markdown(c_html + '</div>', unsafe_allow_html=True)

    st.divider()

    # ── Search ─────────────────────────────────────────────────────────────────
    st.markdown(f"<h1 style='text-align:center;font-size:2.2rem;font-weight:900;color:{text};margin:1.5rem 0 1.2rem;letter-spacing:-.5px;'>Movie Recommendations</h1>", unsafe_allow_html=True)

    # Constrain search to centre 60% of the page
    _, sc, _ = st.columns([1, 4, 1])

    with sc:
        si1, si2 = st.columns([8, 1])
        with si1:
            prompt = st.text_input(
                "search",
                placeholder="Type a movie or TV show… e.g. Inception, Breaking Bad, The Dark Knight",
                label_visibility="collapsed",
                key="title_prompt"
            )
        with si2:
            st.markdown(f"""<style>
            .dice-col .stButton>button{{
                background:{"#1e2138" if dm else "#eef0fa"}!important;
                color:{text}!important; font-size:1.3rem!important;
                border-radius:10px!important; padding:.18rem!important;
                border:none!important; box-shadow:none!important;
            }}
            </style>""", unsafe_allow_html=True)
            st.markdown('<div class="dice-col">', unsafe_allow_html=True)
            if st.button("🎲", help="Random pick", use_container_width=True, key="dice"):
                title = movies['title'].sample(1).values[0]
                st.session_state.selected_title = title
                st.session_state.results = get_recs(title)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        suggestions = fuzzy_suggest(prompt, all_titles) if prompt else []
        if suggestions and prompt not in all_titles:
            st.markdown(
                f"<div style='font-size:.78rem;color:{subtext};margin:.3rem 0 .4rem'>Did you mean: "
                + ' &nbsp;·&nbsp; '.join(f'<span style="color:{ACCENT}">{s}</span>' for s in suggestions)
                + "</div>", unsafe_allow_html=True
            )
        elif prompt and not suggestions:
            st.markdown(f"<div style='font-size:.8rem;color:{ACCENT};margin:.3rem 0'>No titles found for \"{prompt}\".</div>", unsafe_allow_html=True)

        matched = prompt if prompt in all_titles else (suggestions[0] if suggestions else None)
        if matched:
            rb1, rb2 = st.columns(2)
            with rb1:
                if st.button("Find Recommendations", use_container_width=True):
                    st.session_state.selected_title = matched
                    st.session_state.results = get_recs(matched)
            with rb2:
                if st.button("+ Add to Watchlist", use_container_width=True):
                    if matched not in st.session_state.watchlist:
                        st.session_state.watchlist.append(matched)
                        st.success(f"'{matched}' added!")
        else:
            if st.button("Find Recommendations", use_container_width=True, key="rec_empty"):
                if prompt:
                    st.error("No matching title — try a different name.")
                else:
                    st.info("Type a title above or use 🎲 for a random pick.")

    if st.session_state.results and st.session_state.selected_title:
        sel = movies[movies['title'] == st.session_state.selected_title].iloc[0]
        yr  = str(sel.release_date)[:4]

        h1, h2 = st.columns([1, 3])
        with h1:
            st.image(poster_url(sel.get('poster_path', '')), use_container_width=True)
        with h2:
            st.markdown(f"""<div style="padding:.4rem 0">
                <div style="font-size:1.3rem;font-weight:900;color:{text};margin-bottom:.35rem">{sel.title}</div>
                <div style="margin:.3rem 0">{type_badge(sel, has_type)}{genre_badges(sel.genres, 4)}</div>
                <div style="font-size:.78rem;color:{subtext};margin:.3rem 0">Released: {yr} · {int(sel.vote_count):,} votes</div>
                <div class="ratings-row">
                    <div class="rbox"><div class="rsrc">TMDB</div><div class="rval" style="color:{GOLD}">{star_rating(sel.vote_average)}</div><div class="card-meta">{sel.vote_average}/10</div></div>
                    <div class="rbox"><div class="rsrc">Votes</div><div class="rval">{int(sel.vote_count):,}</div></div>
                    <div class="rbox"><div class="rsrc">Popularity</div><div class="rval">{int(sel.popularity):,}</div></div>
                </div>
                <div style="font-size:.85rem;color:{subtext};line-height:1.65;margin-top:.5rem">{sel.overview}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<div class="sec-title">You might also like</div>', unsafe_allow_html=True)
        show_results(st.session_state.results, t, has_type)

# ════════════════════════════════════════════════════════════════════════════════
# WATCHLIST
# ════════════════════════════════════════════════════════════════════════════════
elif page == 'Watchlist':

    wl_count = len(st.session_state.watchlist)
    st.markdown(f'<div class="sec-title">My Watchlist &nbsp;<span style="font-size:.88rem;color:{subtext};font-weight:400">({wl_count} saved)</span></div>', unsafe_allow_html=True)

    wa1, wa2 = st.columns([5, 1])
    with wa1:
        wl_input = st.text_input("wl_search", placeholder="Search to add a title…",
                                  label_visibility="collapsed", key="wl_input")
    with wa2:
        if st.button("+ Add", use_container_width=True):
            wl_matches = [t2 for t2 in all_titles if wl_input.lower() in t2.lower()][:1] if wl_input else []
            wl_match = wl_input if wl_input in all_titles else (wl_matches[0] if wl_matches else None)
            if wl_match and wl_match not in st.session_state.watchlist:
                st.session_state.watchlist.append(wl_match)
                st.success(f"Added '{wl_match}'!")
                st.rerun()
            elif wl_match:
                st.warning("Already in watchlist.")
            else:
                st.error("No matching title found.")

    wl_sug = [t2 for t2 in all_titles if wl_input.lower() in t2.lower()][:6] if wl_input else []
    if wl_sug and wl_input not in all_titles:
        st.markdown(f"<div style='font-size:.78rem;color:{subtext};margin-bottom:.4rem'>Matches: "
                    + ' · '.join(f'<span style="color:{ACCENT}">{s}</span>' for s in wl_sug) + "</div>",
                    unsafe_allow_html=True)

    st.divider()

    if st.session_state.watchlist:
        wl_rows = [movies[movies['title'] == t2].iloc[0]
                   for t2 in st.session_state.watchlist
                   if not movies[movies['title'] == t2].empty]

        cols = st.columns(5)
        for i, row in enumerate(wl_rows):
            with cols[i % 5]:
                st.image(poster_url(row.get('poster_path', '')), use_container_width=True)
                st.markdown(f"""<div class="card-body">
                    <div class="card-title" title="{row.title}">{row.title}</div>
                    <div class="card-meta">{str(row.release_date)[:4]} · {row.vote_average}/10</div>
                    <div style="margin-bottom:.3rem">{type_badge(row, has_type)}</div>
                </div>""", unsafe_allow_html=True)
                if st.button("Remove", key=f"rm_{i}", use_container_width=True):
                    st.session_state.watchlist.remove(row.title)
                    st.rerun()

        st.divider()
        c1, c2 = st.columns([3, 1])
        with c1:
            if st.button("Smart Suggestions from my Watchlist", use_container_width=True):
                with st.spinner("Analysing your taste…"):
                    sugg = watchlist_suggest(movies, similarity)
                if sugg:
                    st.markdown('<div class="sec-title">Based on your watchlist</div>', unsafe_allow_html=True)
                    show_results(sugg, t, has_type)
        with c2:
            if st.button("Clear All", use_container_width=True):
                st.session_state.watchlist = []
                st.rerun()
    else:
        st.markdown(f"<div style='text-align:center;padding:4rem;color:{subtext}'>Your watchlist is empty — go to Home and add titles.</div>", unsafe_allow_html=True)
