# MOV.IE REC — Movie & TV Show Recommender

A Netflix-style movie and TV show recommender with a two-stage ranking pipeline, collaborative filtering, and global content coverage including Nollywood and South African cinema.

**Live:** [movierec-gzsa.onrender.com](https://movierec-gzsa.onrender.com)

---

## Features

- **Two-stage recommendation pipeline** — candidate retrieval via TF-IDF cosine similarity, re-ranked by a blended quality score
- **Collaborative filtering** — personalised recommendations built from each user's watch history and watchlist
- **Quality-aware ranking** — Bayesian weighted rating (IMDb formula) blended with Rotten Tomatoes and Metacritic scores
- **Diversity injection** — prevents genre monotony in results, mirroring Netflix's row diversity logic
- **Global content** — Nollywood, South African cinema, K-Drama, Anime, Bollywood, LGBTQ+, and 15+ language catalogues
- **Live TMDB trending** — real-time trending row fetched from TMDB on page load
- **Multilingual UI** — English, French, Spanish, German, Portuguese
- **Regional filtering** — auto-detects user country, filters content by region
- **Auth** — email/password + Google OAuth, duplicate account prevention, display name uniqueness
- **Email verification** — welcome email + verification link sent on signup via Gmail SMTP
- **Watch history** — mark titles as watched, tracked per user
- **Personalised feed** — `/api/for_you` endpoint returns personalised recommendations for logged-in users
- **Mobile responsive** — full responsive layout with media queries

---

## Recommendation Architecture

```
User searches / browses
         │
         ▼
┌─────────────────────────────────┐
│   Stage 1: Candidate Retrieval  │
│   TF-IDF cosine similarity      │
│   Top 300 candidates (sparse)   │
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│   Stage 2: Ranking              │
│                                 │
│   score = 0.50 × content_sim    │
│         + 0.20 × user_affinity  │  ← collaborative filtering
│         + 0.20 × quality_score  │  ← Bayesian + RT + Metacritic
│         + 0.10 × recency_boost  │  ← 2022+ content boosted
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│   Stage 3: Diversity Injection  │
│   Max 4 of same genre in top 10 │
└─────────────────────────────────┘
```

**Quality score** uses the IMDb Bayesian weighted rating formula, then blends with Rotten Tomatoes (30%) and Metacritic (20%) when available via OMDB enrichment.

**User affinity vector** aggregates neighbour scores across every title in the user's watch history and watchlist — item-based collaborative filtering without requiring user-user interaction data.

**Sparse similarity index** — stores only top-300 neighbours per title, reducing `similarity.pkl` from ~1.2 GB to ~30 MB.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, SQLAlchemy, Flask-Login, Flask-Mail |
| Database | PostgreSQL (Neon — free forever) / SQLite (local dev) |
| ML | scikit-learn (TF-IDF, cosine similarity), NumPy, Pandas |
| Auth | Werkzeug password hashing, Authlib (Google OAuth 2.0) |
| Email | Gmail SMTP via Flask-Mail |
| Data sources | TMDB API, OMDB API, IMDb non-commercial datasets |
| Frontend | Bootstrap 5, vanilla JS |
| Testing | pytest (14 unit tests) |
| Deployment | Gunicorn on Render (free tier) |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/helena-byte999/MovieRec.git
cd MovieRec
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file (never commit this):

```env
SECRET_KEY=your-secret-key
TMDB_KEY=your-tmdb-api-key
OMDB_KEY=your-omdb-api-key
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
DATABASE_URL=your-postgresql-url          # optional — uses SQLite locally if not set
MAIL_USERNAME=your-gmail@gmail.com        # optional — emails skipped if not set
MAIL_PASSWORD=your-gmail-app-password     # Gmail App Password (not your login password)
```

- **TMDB key** — free at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)
- **OMDB key** — free (1,000 req/day) at [omdbapi.com/apikey.aspx](http://www.omdbapi.com/apikey.aspx)
- **Google OAuth** — [console.cloud.google.com](https://console.cloud.google.com), add `http://localhost:5000/auth/google/callback` as authorised redirect URI
- **Gmail App Password** — myaccount.google.com → Security → 2-Step Verification → App Passwords

### 3. Build the dataset

```bash
# Optional: supplement with IMDb African content (~20 mins)
python fetch_imdb_supplement.py

# Build the full dataset and similarity matrix (~30-45 mins)
python fetch_data.py
```

### 4. Run

```bash
python flask_app.py
```

Open [http://localhost:5000](http://localhost:5000)

---

## Testing

```bash
python -m pytest tests/ -v
```

14 unit tests covering:
- Bayesian quality scoring
- Recency boost
- Genre diversity injection
- Recommendation pagination
- LGBTQ+ affinity boosting
- Personalisation with/without user history

---

## Data Sources

| Source | Usage | License |
|---|---|---|
| [TMDB API](https://www.themoviedb.org/documentation/api) | Primary metadata, posters, streaming providers, trending | Free non-commercial |
| [OMDB API](http://www.omdbapi.com/) | Rotten Tomatoes + Metacritic scores | Free tier (1k/day) |
| [IMDb Datasets](https://developer.imdb.com/non-commercial-datasets/) | African title discovery | Non-commercial only |

> This project uses IMDb non-commercial datasets. Not for commercial use.

---

## Project Structure

```
MovieRec/
├── flask_app.py              # Main app — routes, recommender, auth, email
├── fetch_data.py             # Dataset builder (TMDB + TF-IDF sparse similarity)
├── fetch_imdb_supplement.py  # IMDb dataset integration for African content
├── requirements.txt
├── runtime.txt               # Python 3.11 for Render
├── .env                      # secrets — gitignored
├── movie_list.pkl            # built dataset
├── similarity.pkl            # sparse top-300 similarity index (~30 MB)
├── static/
│   ├── css/style.css
│   └── js/main.js
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── watchlist.html
│   └── auth/
│       ├── login.html
│       └── register.html
└── tests/
    └── test_recommender.py
```

---

*© Ena Helena Otuokon, 2026. Made by 3N4*