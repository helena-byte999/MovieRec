import streamlit as st
from utils import (
    init_state, load_data, build_search_index, get_theme, inject_css,
    sidebar_nav, show_results, poster_url, star_rating,
    genre_badges, type_badge, fuzzy_suggest, watchlist_suggest, ACCENT, GOLD
)

st.set_page_config(page_title="CineMatch", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

init_state()
movies, similarity = load_data()
build_search_index(movies)
all_titles = movies['title'].tolist()
has_type   = 'type' in movies.columns

t = get_theme()
dm, text, subtext, card_bg, border = t['dm'], t['text'], t['subtext'], t['card_bg'], t['border']

inject_css(t)

page = st.session_state.get('page', 'Home')
sidebar_nav(page)

def get_recs(title):
    idx = movies[movies['title'] == title].index[0]
    scores = sorted(enumerate(similarity[idx]), reverse=True, key=lambda x: x[1])
    return [movies.iloc[i[0]] for i in scores[1:6]]

# ════════════════════════════════════════════════════════════════════════════════
# HOME
# ════════════════════════════════════════════════════════════════════════════════
if page == 'Home':

    st.markdown('<div class="sec-title">Trending Now</div>', unsafe_allow_html=True)
    trending = movies.nlargest(16, 'popularity')
    c_html = '<div class="carousel">'
    for _, r in trending.iterrows():
        lbl = r.title[:22] + '…' if len(r.title) > 22 else r.title
        c_html += f"""<div class="c-item" title="{r.title}">
            <img src="{poster_url(r.get('poster_path',''))}" alt="{r.title}" loading="lazy"/>
            <div class="c-label">{lbl}</div>
            <div class="c-rating">{star_rating(r.vote_average)} {r.vote_average}</div>
        </div>"""
    st.markdown(c_html + '</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown('<div class="sec-title">Find Recommendations</div>', unsafe_allow_html=True)

    s1, s2 = st.columns([6, 1])
    with s1:
        prompt = st.text_input(
            "search",
            placeholder="Type a movie or TV show… e.g. Inception, Breaking Bad, The Dark Knight",
            label_visibility="collapsed",
            key="title_prompt"
        )
    with s2:
        st.markdown(f"""<style>
        div[data-testid="stHorizontalBlock"] > div:last-child .stButton>button{{
            background:{"#1e2138" if dm else "#eef0fa"}!important;
            color:{text}!important; font-size:1.5rem!important;
            border-radius:10px!important; padding:.2rem!important;
        }}
        div[data-testid="stHorizontalBlock"] > div:last-child .stButton>button:hover{{
            transform:rotate(20deg) scale(1.12);
            background:{"#2a2e50" if dm else "#dde0f5"}!important;
        }}
        </style>""", unsafe_allow_html=True)
        if st.button("🎲", help="Random pick", use_container_width=True):
            title = movies['title'].sample(1).values[0]
            st.session_state.selected_title = title
            st.session_state.results = get_recs(title)
            st.rerun()

    suggestions = fuzzy_suggest(prompt, all_titles) if prompt else []
    if suggestions and prompt not in all_titles:
        st.markdown(
            f"<div style='font-size:.78rem;color:{subtext};margin:.3rem 0 .5rem'>Did you mean: "
            + ' &nbsp;·&nbsp; '.join(f'<span style="color:{ACCENT}">{s}</span>' for s in suggestions)
            + "</div>",
            unsafe_allow_html=True
        )

    matched = prompt if prompt in all_titles else (suggestions[0] if suggestions else None)
    if matched:
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Find Recommendations", use_container_width=True):
                st.session_state.selected_title = matched
                st.session_state.results = get_recs(matched)
        with b2:
            if st.button("+ Add to Watchlist", use_container_width=True):
                if matched not in st.session_state.watchlist:
                    st.session_state.watchlist.append(matched)
                    st.success(f"'{matched}' added to watchlist!")

    if st.session_state.results and st.session_state.selected_title:
        sel = movies[movies['title'] == st.session_state.selected_title].iloc[0]
        yr  = str(sel.release_date)[:4]

        h1, h2 = st.columns([1, 3])
        with h1:
            st.image(poster_url(sel.get('poster_path', '')), use_container_width=True)
        with h2:
            st.markdown(f"""<div style="padding:.4rem 0">
                <div class="hero-title">{sel.title}</div>
                <div style="margin:.3rem 0">{type_badge(sel, has_type)}{genre_badges(sel.genres, 4)}</div>
                <div class="card-meta">Released: {yr} · {int(sel.vote_count):,} votes</div>
                <div class="ratings-row">
                    <div class="rbox"><div class="rsrc">TMDB</div><div class="rval" style="color:{GOLD}">{star_rating(sel.vote_average)}</div><div class="card-meta">{sel.vote_average}/10</div></div>
                    <div class="rbox"><div class="rsrc">Votes</div><div class="rval">{int(sel.vote_count):,}</div></div>
                    <div class="rbox"><div class="rsrc">Popularity</div><div class="rval">{int(sel.popularity):,}</div></div>
                </div>
                <div class="hero-overview">{sel.overview}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<div class="sec-title">You might also like</div>', unsafe_allow_html=True)
        show_results(st.session_state.results, t, has_type)

# ════════════════════════════════════════════════════════════════════════════════
# WATCHLIST
# ════════════════════════════════════════════════════════════════════════════════
elif page == 'Watchlist':

    wl_count = len(st.session_state.watchlist)
    st.markdown(
        f'<div class="sec-title">My Watchlist <span style="font-size:.9rem;color:{subtext};font-weight:400">({wl_count} saved)</span></div>',
        unsafe_allow_html=True
    )

    wa1, wa2 = st.columns([5, 1])
    with wa1:
        wl_input = st.text_input(
            "wl_search",
            placeholder="Search to add a title…",
            label_visibility="collapsed",
            key="wl_input"
        )
    with wa2:
        if st.button("+ Add", use_container_width=True):
            wl_match = wl_input if wl_input in all_titles else (fuzzy_suggest(wl_input, all_titles, 1) or [None])[0]
            if wl_match and wl_match not in st.session_state.watchlist:
                st.session_state.watchlist.append(wl_match)
                st.success(f"Added '{wl_match}'!")
                st.rerun()
            elif wl_match in st.session_state.watchlist:
                st.warning("Already in watchlist.")

    wl_sug = fuzzy_suggest(wl_input, all_titles) if wl_input else []
    if wl_sug and wl_input not in all_titles:
        st.markdown(
            f"<div style='font-size:.78rem;color:{subtext};margin-bottom:.4rem'>Matches: "
            + ' · '.join(f'<span style="color:{ACCENT}">{s}</span>' for s in wl_sug)
            + "</div>",
            unsafe_allow_html=True
        )

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
        st.markdown(
            f"<div style='text-align:center;padding:4rem;color:{subtext};font-size:1rem'>"
            "Your watchlist is empty.<br>Go to <b>Home</b> and add titles you want to watch."
            "</div>",
            unsafe_allow_html=True
        )
