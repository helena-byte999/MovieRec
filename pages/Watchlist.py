import streamlit as st
from utils import (
    init_state, load_data, get_theme, inject_css, sidebar_nav,
    show_results, poster_url, star_rating, genre_badges, type_badge,
    fuzzy_suggest, watchlist_suggest, ACCENT
)

st.set_page_config(page_title="Watchlist · CineMatch", page_icon="☆", layout="wide", initial_sidebar_state="expanded")

init_state()
movies, similarity = load_data()
all_titles = movies['title'].tolist()
has_type   = 'type' in movies.columns

t = get_theme()
dm, text, subtext, card_bg, border = t['dm'], t['text'], t['subtext'], t['card_bg'], t['border']

inject_css(t)
sidebar_nav("Watchlist")

wl_count = len(st.session_state.watchlist)
st.markdown(
    f'<div class="sec-title">My Watchlist <span style="font-size:.9rem;color:{subtext};font-weight:400">({wl_count} saved)</span></div>',
    unsafe_allow_html=True
)

# ── Add a title ────────────────────────────────────────────────────────────────
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

# ── Watchlist poster grid ──────────────────────────────────────────────────────
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
                <div style="margin-bottom:.4rem">{type_badge(row, has_type)}</div>
            </div>""", unsafe_allow_html=True)
            if st.button("Remove", key=f"rm_{i}", use_container_width=True):
                st.session_state.watchlist.remove(row.title)
                st.rerun()

    st.divider()

    c1, c2 = st.columns([2, 1])
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
