from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_mail import Mail, Message
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from datetime import datetime
from dotenv import load_dotenv
import pickle, os, secrets, time, re
import numpy as np
import requests

load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # allow HTTP in development

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///movierec.db')
# Render provides postgres:// but SQLAlchemy requires postgresql://
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI']        = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Secure session cookies on HTTPS (Render) — keeps OAuth state intact
app.config['SESSION_COOKIE_SECURE']   = _db_url.startswith('postgresql')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ── Email (Gmail SMTP) ───────────────────────────────────────────────────────
app.config['MAIL_SERVER']   = 'smtp.gmail.com'
app.config['MAIL_PORT']     = 587
app.config['MAIL_USE_TLS']  = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', '')

db            = SQLAlchemy(app)
login_manager = LoginManager(app)
mail          = Mail(app)
login_manager.login_view = 'login_page'
oauth = OAuth(app)

# ── Database models ─────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    email        = db.Column(db.String(120), unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    password_hash= db.Column(db.String(256))
    google_id    = db.Column(db.String(100), unique=True)
    avatar       = db.Column(db.String(256))
    region             = db.Column(db.String(10),  default='GLOBAL')
    language           = db.Column(db.String(5),   default='en')
    created_at         = db.Column(db.DateTime,    default=datetime.utcnow)
    email_verified     = db.Column(db.Boolean,     default=False)
    verification_token = db.Column(db.String(64),  nullable=True)
    onboarded          = db.Column(db.Boolean,     default=False)
    watchlist    = db.relationship('WatchlistItem', backref='user', lazy=True,
                                   cascade='all, delete-orphan')

class WatchlistItem(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title    = db.Column(db.String(256), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class WatchedItem(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title      = db.Column(db.String(256), nullable=False)
    poster_url = db.Column(db.String(512))
    year       = db.Column(db.String(10))
    media_type = db.Column(db.String(20))
    rating     = db.Column(db.Float)
    watched_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ── Google OAuth ─────────────────────────────────────────────────────────────
google_oauth = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# ── Watchlist helpers (DB for logged-in, session for anonymous) ──────────────
def _wl_titles():
    if current_user.is_authenticated:
        return [w.title for w in current_user.watchlist]
    return session.get('watchlist', [])

def _wl_add(title):
    if current_user.is_authenticated:
        if not WatchlistItem.query.filter_by(user_id=current_user.id, title=title).first():
            db.session.add(WatchlistItem(user_id=current_user.id, title=title))
            db.session.commit()
    else:
        if 'watchlist' not in session: session['watchlist'] = []
        if title not in session['watchlist']:
            session['watchlist'] = session['watchlist'] + [title]

def _wl_remove(title):
    if current_user.is_authenticated:
        WatchlistItem.query.filter_by(user_id=current_user.id, title=title).delete()
        db.session.commit()
    else:
        session['watchlist'] = [t for t in session.get('watchlist', []) if t != title]

def _migrate_session_wl():
    """Move anonymous session watchlist into the DB after login."""
    for title in session.pop('watchlist', []):
        if not WatchlistItem.query.filter_by(user_id=current_user.id, title=title).first():
            db.session.add(WatchlistItem(user_id=current_user.id, title=title))
    db.session.commit()

# ── Preference helpers ───────────────────────────────────────────────────────
def _get_region():
    return current_user.region if current_user.is_authenticated else session.get('region', 'GLOBAL')

def _get_language():
    return current_user.language if current_user.is_authenticated else session.get('language', 'en')

def _save_region(r):
    if current_user.is_authenticated:
        current_user.region = r; db.session.commit()
    else:
        session['region'] = r

def _save_language(l):
    if current_user.is_authenticated:
        current_user.language = l; db.session.commit()
    else:
        session['language'] = l

TMDB_KEY      = os.environ.get('TMDB_KEY', '')
POSTER_BASE   = "https://image.tmdb.org/t/p/w500"
BACKDROP_BASE = "https://image.tmdb.org/t/p/original"
NO_POSTER     = "https://placehold.co/300x450/1a1a2e/59005c?text=No+Image"

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

AFRICAN_LANGS    = {'yo', 'ig', 'ha', 'sw', 'am', 'zu', 'af', 'so'}
AFRICAN_COUNTRIES = {'NG', 'ZA', 'GH', 'KE', 'ET', 'TZ', 'CM', 'SN', 'CI', 'RW', 'UG', 'AO', 'MZ'}

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
# UI language options (for interface translation only)
LANGUAGES_LIST = [
    ('en', '🇬🇧 English'),
    ('fr', '🇫🇷 Français'),
    ('es', '🇪🇸 Español'),
    ('de', '🇩🇪 Deutsch'),
    ('pt', '🇧🇷 Português'),
]

TRANSLATIONS = {
    'en': {
        'type_movie': 'Movie', 'type_tv': 'TV Show',
        'genres': {},  # no translation needed for English
        'home': 'Home', 'watchlist': 'Watchlist',
        'trending': 'TRENDING', 'find_recs': 'Find Recommendations',
        'recommender_title': 'Movie / TV Show Recommender',
        'you_might_like': 'You might also like',
        'add_watchlist': '+ Watchlist', 'in_watchlist': '✓ In Watchlist',
        'search_placeholder': 'Or type a title… e.g. Inception, Breaking Bad',
        'genre_placeholder': '🎬 Browse by genre (optional)',
        'all': 'All', 'stream_on': 'Stream on', 'reviews': 'Reviews',
        'read_review': 'Read full review ↗',
        'loading_seasons': 'Loading season info…',
        'loading_streaming': 'Loading streaming info…',
        'loading_reviews': 'Loading reviews…',
        'seasons': 'Seasons', 'season': 'Season', 'episodes': 'Episodes',
        'not_streaming': 'Not available on streaming in your region.',
        'not_found': 'not found — try a different name.',
        'error': 'Something went wrong. Please try again.',
        'top_results': 'Top {genre} Titles',
        # Row labels
        'trending_now': 'Trending Now', 'top_movies': 'Top Movies', 'top_tv': 'Top TV Shows',
        'action_adventure': 'Action & Adventure', 'crime_thriller': 'Crime & Thriller',
        'comedy': 'Comedy', 'drama': 'Drama', 'scifi_fantasy': 'Sci-Fi & Fantasy',
        'horror': 'Horror', 'romance': 'Romance', 'documentary': 'Documentary',
        'animation': 'Animation', 'family_kids': 'Family & Kids', 'history_war': 'History & War',
        'african_stories': 'African Stories', 'nollywood': 'Nollywood', 'south_african': 'South African Cinema',
        'kdrama': 'K-Drama & Korean Cinema',
        'anime': 'Anime', 'bollywood': 'Bollywood & Indian Cinema', 'acclaimed': 'Critically Acclaimed',
        'lgbtq': 'LGBTQ+', 'new_releases': 'New Releases', 'trending_week': 'Trending This Week',
        'show_more': 'Show More',
        'watchlist_title': 'My Watchlist', 'saved': 'saved', 'search_add_placeholder': 'Search to add a title…',
        'add_btn': '+ Add', 'remove': 'Remove', 'clear_all': 'Clear All',
        'based_on_watchlist': 'Based on your watchlist', 'empty_watchlist': 'Your watchlist is empty.',
        'go_home': 'Go to Home', 'added_to_watchlist': 'added to Watchlist', 'refresh': 'Refresh',
    },
    'fr': {
        'type_movie': 'Film', 'type_tv': 'Série',
        'genres': {
            'Action': 'Action', 'Adventure': 'Aventure', 'Animation': 'Animation',
            'Comedy': 'Comédie', 'Crime': 'Crime', 'Documentary': 'Documentaire',
            'Drama': 'Drame', 'Family': 'Famille', 'Fantasy': 'Fantaisie',
            'History': 'Histoire', 'Horror': 'Horreur', 'Music': 'Musique',
            'Mystery': 'Mystère', 'Romance': 'Romance', 'Science Fiction': 'Science-Fiction',
            'Thriller': 'Thriller', 'War': 'Guerre', 'Western': 'Western',
            'Sci-Fi & Fantasy': 'Science-Fiction & Fantaisie',
        },
        'home': 'Accueil', 'watchlist': 'Ma liste',
        'trending': 'TENDANCES', 'find_recs': 'Trouver des recommandations',
        'recommender_title': 'Recommandeur de Films / Séries',
        'you_might_like': 'Vous pourriez aussi aimer',
        'add_watchlist': '+ Ma liste', 'in_watchlist': '✓ Dans la liste',
        'search_placeholder': 'Tapez un titre… ex. Inception, Breaking Bad',
        'genre_placeholder': '🎬 Parcourir par genre (optionnel)',
        'all': 'Tout', 'stream_on': 'Disponible sur', 'reviews': 'Critiques',
        'read_review': 'Lire la critique complète ↗',
        'loading_seasons': 'Chargement des saisons…',
        'loading_streaming': 'Chargement des plateformes…',
        'loading_reviews': 'Chargement des critiques…',
        'seasons': 'Saisons', 'season': 'Saison', 'episodes': 'Épisodes',
        'not_streaming': 'Non disponible en streaming dans votre région.',
        'not_found': 'introuvable — essayez un autre titre.',
        'error': 'Une erreur est survenue. Veuillez réessayer.',
        'top_results': 'Meilleurs titres {genre}',
        'trending_now': 'Tendances du moment', 'top_movies': 'Meilleurs films', 'top_tv': 'Meilleures séries',
        'action_adventure': 'Action & Aventure', 'crime_thriller': 'Crime & Thriller',
        'comedy': 'Comédie', 'drama': 'Drame', 'scifi_fantasy': 'Science-Fiction & Fantaisie',
        'horror': 'Horreur', 'romance': 'Romance', 'documentary': 'Documentaire',
        'animation': 'Animation', 'family_kids': 'Famille & Enfants', 'history_war': 'Histoire & Guerre',
        'african_stories': 'Histoires africaines', 'nollywood': 'Nollywood', 'south_african': 'Cinéma sud-africain',
        'kdrama': 'K-Drama & Cinéma coréen',
        'anime': 'Animé', 'bollywood': 'Bollywood & Cinéma indien', 'acclaimed': 'Acclamé par la critique',
        'lgbtq': 'LGBTQ+', 'new_releases': 'Nouvelles sorties', 'trending_week': 'Tendances de la semaine',
        'watchlist_title': 'Ma liste', 'saved': 'sauvegardés', 'search_add_placeholder': 'Rechercher un titre…',
        'add_btn': '+ Ajouter', 'remove': 'Supprimer', 'clear_all': 'Tout effacer',
        'based_on_watchlist': 'Basé sur votre liste', 'empty_watchlist': 'Votre liste est vide.',
        'go_home': 'Retour à l\'accueil', 'added_to_watchlist': 'ajouté à la liste', 'refresh': 'Actualiser',
    },
    'es': {
        'type_movie': 'Película', 'type_tv': 'Serie',
        'genres': {
            'Action': 'Acción', 'Adventure': 'Aventura', 'Animation': 'Animación',
            'Comedy': 'Comedia', 'Crime': 'Crimen', 'Documentary': 'Documental',
            'Drama': 'Drama', 'Family': 'Familia', 'Fantasy': 'Fantasía',
            'History': 'Historia', 'Horror': 'Terror', 'Music': 'Música',
            'Mystery': 'Misterio', 'Romance': 'Romance', 'Science Fiction': 'Ciencia Ficción',
            'Thriller': 'Thriller', 'War': 'Guerra', 'Western': 'Western',
        },
        'home': 'Inicio', 'watchlist': 'Mi lista',
        'trending': 'TENDENCIAS', 'find_recs': 'Buscar recomendaciones',
        'recommender_title': 'Recomendador de Películas / Series',
        'you_might_like': 'También te podría gustar',
        'add_watchlist': '+ Mi lista', 'in_watchlist': '✓ En la lista',
        'search_placeholder': 'Escribe un título… ej. Inception, Breaking Bad',
        'genre_placeholder': '🎬 Explorar por género (opcional)',
        'all': 'Todo', 'stream_on': 'Ver en', 'reviews': 'Reseñas',
        'read_review': 'Leer reseña completa ↗',
        'loading_seasons': 'Cargando temporadas…',
        'loading_streaming': 'Cargando plataformas…',
        'loading_reviews': 'Cargando reseñas…',
        'seasons': 'Temporadas', 'season': 'Temporada', 'episodes': 'Episodios',
        'not_streaming': 'No disponible en streaming en tu región.',
        'not_found': 'no encontrado — prueba con otro título.',
        'error': 'Algo salió mal. Por favor, inténtalo de nuevo.',
        'top_results': 'Mejores títulos de {genre}',
        'trending_now': 'Tendencias ahora', 'top_movies': 'Mejores películas', 'top_tv': 'Mejores series',
        'action_adventure': 'Acción & Aventura', 'crime_thriller': 'Crimen & Thriller',
        'comedy': 'Comedia', 'drama': 'Drama', 'scifi_fantasy': 'Ciencia Ficción & Fantasía',
        'horror': 'Terror', 'romance': 'Romance', 'documentary': 'Documental',
        'animation': 'Animación', 'family_kids': 'Familia & Niños', 'history_war': 'Historia & Guerra',
        'african_stories': 'Historias africanas', 'nollywood': 'Nollywood', 'south_african': 'Cine sudafricano',
        'kdrama': 'K-Drama & Cine coreano',
        'anime': 'Anime', 'bollywood': 'Bollywood & Cine indio', 'acclaimed': 'Aclamados por la crítica',
        'lgbtq': 'LGBTQ+', 'new_releases': 'Nuevos lanzamientos', 'trending_week': 'Tendencias de la semana',
        'watchlist_title': 'Mi lista', 'saved': 'guardados', 'search_add_placeholder': 'Buscar un título…',
        'add_btn': '+ Añadir', 'remove': 'Eliminar', 'clear_all': 'Borrar todo',
        'based_on_watchlist': 'Basado en tu lista', 'empty_watchlist': 'Tu lista está vacía.',
        'go_home': 'Ir a inicio', 'added_to_watchlist': 'añadido a la lista', 'refresh': 'Actualizar',
    },
    'de': {
        'type_movie': 'Film', 'type_tv': 'Serie',
        'genres': {
            'Action': 'Action', 'Adventure': 'Abenteuer', 'Animation': 'Animation',
            'Comedy': 'Komödie', 'Crime': 'Krimi', 'Documentary': 'Dokumentarfilm',
            'Drama': 'Drama', 'Family': 'Familie', 'Fantasy': 'Fantasy',
            'History': 'Geschichte', 'Horror': 'Horror', 'Music': 'Musik',
            'Mystery': 'Mystery', 'Romance': 'Romantik', 'Science Fiction': 'Science-Fiction',
            'Thriller': 'Thriller', 'War': 'Krieg', 'Western': 'Western',
        },
        'home': 'Startseite', 'watchlist': 'Merkliste',
        'trending': 'TRENDS', 'find_recs': 'Empfehlungen finden',
        'recommender_title': 'Film- & Serien-Empfehlungen',
        'you_might_like': 'Das könnte dir auch gefallen',
        'add_watchlist': '+ Merkliste', 'in_watchlist': '✓ Auf der Liste',
        'search_placeholder': 'Titel eingeben… z.B. Inception, Breaking Bad',
        'genre_placeholder': '🎬 Nach Genre stöbern (optional)',
        'all': 'Alle', 'stream_on': 'Streamen auf', 'reviews': 'Kritiken',
        'read_review': 'Vollständige Kritik lesen ↗',
        'loading_seasons': 'Staffeln werden geladen…',
        'loading_streaming': 'Streaming-Anbieter werden geladen…',
        'loading_reviews': 'Kritiken werden geladen…',
        'seasons': 'Staffeln', 'season': 'Staffel', 'episodes': 'Episoden',
        'not_streaming': 'In Ihrer Region nicht auf Streaming verfügbar.',
        'not_found': 'nicht gefunden — anderen Titel versuchen.',
        'error': 'Etwas ist schiefgelaufen. Bitte versuche es erneut.',
        'top_results': 'Top {genre} Titel',
        'trending_now': 'Gerade im Trend', 'top_movies': 'Top Filme', 'top_tv': 'Top Serien',
        'action_adventure': 'Action & Abenteuer', 'crime_thriller': 'Krimi & Thriller',
        'comedy': 'Komödie', 'drama': 'Drama', 'scifi_fantasy': 'Science-Fiction & Fantasy',
        'horror': 'Horror', 'romance': 'Romantik', 'documentary': 'Dokumentarfilm',
        'animation': 'Animation', 'family_kids': 'Familie & Kinder', 'history_war': 'Geschichte & Krieg',
        'african_stories': 'Afrikanische Geschichten', 'nollywood': 'Nollywood', 'south_african': 'Südafrikanisches Kino',
        'kdrama': 'K-Drama & Koreanisches Kino',
        'anime': 'Anime', 'bollywood': 'Bollywood & Indisches Kino', 'acclaimed': 'Von der Kritik gelobt',
        'lgbtq': 'LGBTQ+', 'new_releases': 'Neuerscheinungen', 'trending_week': 'Trends der Woche',
        'watchlist_title': 'Merkliste', 'saved': 'gespeichert', 'search_add_placeholder': 'Titel suchen…',
        'add_btn': '+ Hinzufügen', 'remove': 'Entfernen', 'clear_all': 'Alle löschen',
        'based_on_watchlist': 'Basierend auf deiner Liste', 'empty_watchlist': 'Deine Liste ist leer.',
        'go_home': 'Zur Startseite', 'added_to_watchlist': 'zur Liste hinzugefügt', 'refresh': 'Aktualisieren',
    },
    'pt': {
        'type_movie': 'Filme', 'type_tv': 'Série',
        'genres': {
            'Action': 'Ação', 'Adventure': 'Aventura', 'Animation': 'Animação',
            'Comedy': 'Comédia', 'Crime': 'Crime', 'Documentary': 'Documentário',
            'Drama': 'Drama', 'Family': 'Família', 'Fantasy': 'Fantasia',
            'History': 'História', 'Horror': 'Terror', 'Music': 'Música',
            'Mystery': 'Mistério', 'Romance': 'Romance', 'Science Fiction': 'Ficção Científica',
            'Thriller': 'Thriller', 'War': 'Guerra', 'Western': 'Faroeste',
        },
        'home': 'Início', 'watchlist': 'Minha lista',
        'trending': 'TENDÊNCIAS', 'find_recs': 'Encontrar recomendações',
        'recommender_title': 'Recomendador de Filmes / Séries',
        'you_might_like': 'Você também pode gostar',
        'add_watchlist': '+ Minha lista', 'in_watchlist': '✓ Na lista',
        'search_placeholder': 'Digite um título… ex. Inception, Breaking Bad',
        'genre_placeholder': '🎬 Explorar por gênero (opcional)',
        'all': 'Tudo', 'stream_on': 'Assistir em', 'reviews': 'Críticas',
        'read_review': 'Ler crítica completa ↗',
        'loading_seasons': 'Carregando temporadas…',
        'loading_streaming': 'Carregando plataformas…',
        'loading_reviews': 'Carregando críticas…',
        'seasons': 'Temporadas', 'season': 'Temporada', 'episodes': 'Episódios',
        'not_streaming': 'Não disponível em streaming na sua região.',
        'not_found': 'não encontrado — tente outro título.',
        'error': 'Algo deu errado. Por favor, tente novamente.',
        'top_results': 'Melhores títulos de {genre}',
        'trending_now': 'Em alta agora', 'top_movies': 'Melhores filmes', 'top_tv': 'Melhores séries',
        'action_adventure': 'Ação & Aventura', 'crime_thriller': 'Crime & Thriller',
        'comedy': 'Comédia', 'drama': 'Drama', 'scifi_fantasy': 'Ficção Científica & Fantasia',
        'horror': 'Terror', 'romance': 'Romance', 'documentary': 'Documentário',
        'animation': 'Animação', 'family_kids': 'Família & Crianças', 'history_war': 'História & Guerra',
        'african_stories': 'Histórias africanas', 'nollywood': 'Nollywood', 'south_african': 'Cinema sul-africano',
        'kdrama': 'K-Drama & Cinema coreano',
        'anime': 'Anime', 'bollywood': 'Bollywood & Cinema indiano', 'acclaimed': 'Aclamado pela crítica',
        'lgbtq': 'LGBTQ+', 'new_releases': 'Lançamentos recentes', 'trending_week': 'Tendências da semana',
        'watchlist_title': 'Minha lista', 'saved': 'salvos', 'search_add_placeholder': 'Buscar um título…',
        'add_btn': '+ Adicionar', 'remove': 'Remover', 'clear_all': 'Limpar tudo',
        'based_on_watchlist': 'Com base na sua lista', 'empty_watchlist': 'Sua lista está vazia.',
        'go_home': 'Ir para início', 'added_to_watchlist': 'adicionado à lista', 'refresh': 'Atualizar',
    },
}

# (translation_key, tmdb_genre_tags)
GENRE_ROWS = [
    ('action_adventure', ['Action', 'Adventure']),
    ('crime_thriller',   ['Crime', 'Thriller', 'Mystery']),
    ('comedy',           ['Comedy']),
    ('drama',            ['Drama']),
    ('scifi_fantasy',    ['Science Fiction', 'Fantasy']),
    ('horror',           ['Horror']),
    ('romance',          ['Romance']),
    ('documentary',      ['Documentary']),
    ('animation',        ['Animation']),
    ('family_kids',      ['Family', 'Kids']),
    ('history_war',      ['History', 'War']),
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

# Bayesian weighted-rating constants (IMDb formula) — precomputed once at startup
_VOTE_MEAN = float(movies['vote_average'].fillna(0).mean())
_VOTE_MIN  = float(movies['vote_count'].fillna(0).quantile(0.20))

# ── Sparse similarity helpers ────────────────────────────────────────────────
def _sim_row(idx):
    """Return (indices_array, scores_array) for the top neighbours of title idx."""
    if isinstance(similarity, dict):
        return similarity['indices'][idx], similarity['scores'][idx]
    # Legacy dense matrix — extract top 300 on the fly
    row     = similarity[idx]
    top_idx = np.argsort(row)[::-1][1:301]
    return top_idx, row[top_idx]


def _aggregate_scores(titles, exclude=None):
    """
    Sum neighbour scores across multiple source titles (watchlist/history).
    Returns dict {movie_idx: aggregated_score}.
    """
    exclude = exclude or set()
    acc     = {}
    for title in titles:
        match = movies[movies['title'] == title]
        if match.empty:
            continue
        indices, scores = _sim_row(match.index[0])
        for nbr_idx, score in zip(indices.tolist(), scores.tolist()):
            if movies.iloc[nbr_idx]['title'] not in exclude:
                acc[nbr_idx] = acc.get(nbr_idx, 0.0) + float(score)
    return acc


@app.context_processor
def inject_nav_context():
    lang   = _get_language()
    region = _get_region()
    t      = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
    return {
        'regions_list':     REGIONS_LIST,
        'current_region':   region,
        'languages_list':   LANGUAGES_LIST,
        'current_language': lang,
        't':                t,
        'wl_titles':        _wl_titles(),
    }


def _safe_float(val, default=0.0):
    try:
        v = float(val)
        return default if v != v else v  # NaN check
    except (TypeError, ValueError):
        return default

def _safe_int(val, default=0):
    try:
        v = float(val)
        return default if v != v else int(v)
    except (TypeError, ValueError):
        return default

def to_dict(row):
    pp = row.get('poster_path', '') if hasattr(row, 'get') else ''
    bp = row.get('backdrop_path', '') if hasattr(row, 'get') else ''
    pp = '' if str(pp) in ('nan', 'None', '') else str(pp)
    bp = '' if str(bp) in ('nan', 'None', '') else str(bp)
    return {
        'id':                _safe_int(row['id']),
        'title':             str(row['title']),
        'type':              str(row.get('type', 'Movie')) if has_type else 'Movie',
        'genres':            str(row.get('genres', '')),
        'overview':          str(row.get('overview', '')),
        'vote_average':      round(_safe_float(row.get('vote_average', 0)), 1),
        'vote_count':        _safe_int(row.get('vote_count', 0)),
        'popularity':        round(_safe_float(row.get('popularity', 0)), 1),
        'year':              str(row.get('release_date', ''))[:4],
        'poster_url':        f"{POSTER_BASE}{pp}" if pp else NO_POSTER,
        'backdrop_url':      f"{BACKDROP_BASE}{bp}" if bp else '',
        'original_language': str(row.get('original_language', '')),
        'is_lgbtq': 'lgbtq' in str(row.get('tags', '')).lower(),
    }


TMDB_LANG_MAP = {'fr': 'fr-FR', 'es': 'es-ES', 'de': 'de-DE', 'pt': 'pt-BR'}

def get_translated_overview(tmdb_id, is_tv, lang):
    if lang == 'en':
        return None
    mt       = 'tv' if is_tv else 'movie'
    tmdb_lang = TMDB_LANG_MAP.get(lang, lang)
    try:
        res = requests.get(
            f"https://api.themoviedb.org/3/{mt}/{tmdb_id}",
            params={'api_key': TMDB_KEY, 'language': tmdb_lang}, timeout=3
        ).json()
        return res.get('overview') or None
    except Exception:
        return None


def get_pool(region):
    if region == 'GLOBAL':
        return movies
    filtered = movies[movies['regions'].apply(lambda r: isinstance(r, list) and region in r)]
    return filtered if len(filtered) >= 20 else movies


def build_row(label, pool, min_items=4, n=20, sort_col='popularity'):
    items = [to_dict(r) for _, r in pool.nlargest(n, sort_col).iterrows()]
    return {'label': label, 'cards': items} if len(items) >= min_items else None


def _quality_score(row):
    """
    Blended quality score normalised to 0-1.
    Uses Bayesian weighted TMDB rating as the base, then blends in
    Rotten Tomatoes and Metacritic scores when available (from OMDB enrichment).
    """
    v  = _safe_float(row.get('vote_count', 0))
    R  = _safe_float(row.get('vote_average', 0))
    # Bayesian weighted rating (IMDb formula)
    tmdb_wr = (v / (v + _VOTE_MIN)) * R + (_VOTE_MIN / (v + _VOTE_MIN)) * _VOTE_MEAN
    tmdb_q  = tmdb_wr / 10.0

    scores, weights = [tmdb_q], [0.5]

    import pandas as _pd
    rt_raw = row.get('rt_score', None)
    if rt_raw is not None and not _pd.isna(rt_raw):
        scores.append(float(rt_raw) / 100.0)
        weights.append(0.3)

    mc_raw = row.get('metacritic_score', None)
    if mc_raw is not None and not _pd.isna(mc_raw):
        scores.append(float(mc_raw) / 100.0)
        weights.append(0.2)

    # Weighted average of available scores
    total_w = sum(weights)
    return sum(s * w for s, w in zip(scores, weights)) / total_w


def _recency_boost(row):
    """Small linear boost so newer titles surface more easily."""
    try:
        year = int(str(row.get('release_date', ''))[:4])
        if year >= 2024: return 0.08
        if year >= 2022: return 0.04
        return 0.0
    except Exception:
        return 0.0


def _diversify(ranked_indices, max_same_genre=4, top_n=10):
    """
    Interleave top-N results so no single genre dominates the first page
    (mirrors Netflix's diversity injection stage).
    Returns re-ordered index list.
    """
    genre_counts = {}
    result, rest = [], []
    for i in ranked_indices:
        row    = movies.iloc[i]
        genres = [g.strip() for g in str(row.get('genres', '')).split(',') if g.strip()]
        lead   = genres[0] if genres else '_none'
        cnt    = genre_counts.get(lead, 0)
        if len(result) < top_n and cnt < max_same_genre:
            genre_counts[lead] = cnt + 1
            result.append(i)
        else:
            rest.append(i)
        if len(result) == top_n:
            rest += ranked_indices[len(result) + len(rest):]
            break
    return result + rest


def _user_affinity_vector(user_id):
    """
    Item-based collaborative filtering: aggregate neighbour scores across
    every title the user has watched or watchlisted.
    Returns dict {movie_idx: score} or None if no history.
    """
    watched = WatchedItem.query.filter_by(user_id=user_id).all()
    wl      = WatchlistItem.query.filter_by(user_id=user_id).all()
    titles  = {w.title for w in watched} | {w.title for w in wl}
    if not titles:
        return None
    acc = _aggregate_scores(titles, exclude=titles)
    return acc if acc else None


def get_recs(title, offset=0, limit=20, user_id=None):
    idx        = movies[movies['title'] == title].index[0]
    source_row = movies.iloc[idx]
    is_lgbtq   = 'lgbtq' in str(source_row.get('tags', '')).lower()

    # ── Stage 1: candidate retrieval (top 300 by cosine similarity) ──────
    indices, scores = _sim_row(idx)
    candidates      = list(zip(indices.tolist(), scores.tolist()))[:300]

    # Optional: user affinity dict for personalised blending
    user_vec = _user_affinity_vector(user_id) if user_id else None

    # ── Stage 2: ranking — content + quality + recency (+ user affinity) ─
    ranked = []
    for i, sim in candidates:
        row = movies.iloc[i]
        q   = _quality_score(row)
        rb  = _recency_boost(row)
        if user_vec is not None:
            aff   = user_vec.get(i, 0.0)
            score = 0.50 * sim + 0.20 * aff + 0.20 * q + 0.10 * rb
        else:
            score = 0.60 * sim + 0.30 * q + 0.10 * rb
        ranked.append((i, score))
    ranked.sort(key=lambda x: x[1], reverse=True)

    # ── Stage 3: LGBTQ affinity boost ────────────────────────────────────
    if is_lgbtq:
        lgbtq = [(i, s) for i, s in ranked if 'lgbtq' in str(movies.iloc[i].get('tags', '')).lower()]
        other = [(i, s) for i, s in ranked if 'lgbtq' not in str(movies.iloc[i].get('tags', '')).lower()]
        ranked = lgbtq + other

    ordered_idx = [i for i, _ in ranked]

    # ── Stage 4: diversity injection (top-10 de-clustered by genre) ──────
    ordered_idx = _diversify(ordered_idx, max_same_genre=4, top_n=10)

    page_items = [movies.iloc[i] for i in ordered_idx[offset:offset + limit]]
    return {
        'items':    [to_dict(r) for r in page_items],
        'total':    len(ordered_idx),
        'has_more': offset + limit < len(ordered_idx),
        'offset':   offset + limit,
    }


# ── LGBTQ+ dataset signals (compiled once at startup) ────────────────────────
_LGBTQ_TAG_PAT = re.compile(
    r'lgbtq|lgbt(?!\+)|lesbian|bisexual|transgender|\btrans\b|queer|'
    r'homosexual|same.sex|coming.out|drag.queen|\bgay\b', re.IGNORECASE
)
_LGBTQ_OV_PAT = re.compile(
    r'\bgay\b|\blesbians?\b|\bbisexual\b|\btransgender\b|\btrans\b|'
    r'\bqueer\b|lgbtq|same.sex|coming out|drag queen|homosexual', re.IGNORECASE
)
_KIDS_GENRE_PAT = re.compile(r'\b(family|kids|children)\b', re.IGNORECASE)


def _lgbtq_central(genres_str, overview_str=''):
    """Exclude clear children's content from the LGBTQ+ row."""
    return not bool(_KIDS_GENRE_PAT.search(str(genres_str)))


def _lgbtq_pool(pool):
    """
    LGBTQ+ subset using dataset signals only — no external API.
    Vectorised str.contains for speed; excludes Family/Kids/Children genres.
    """
    if 'tags' in pool.columns:
        by_tag = pool['tags'].str.contains(_LGBTQ_TAG_PAT, na=False)
    else:
        # Return a proper bool-dtype Series of all-False so | works correctly
        by_tag = pool['overview'].str.contains('XXXXNOMATCH', na=False)

    by_ov    = pool['overview'].str.contains(_LGBTQ_OV_PAT, na=False)
    not_kids = ~pool['genres'].str.contains(_KIDS_GENRE_PAT, na=False)
    return pool[(by_tag | by_ov) & not_kids]


# ── Home-page row cache (in-process, per region+language, 5-min TTL) ─────────
_ROW_CACHE: dict = {}
_ROW_CACHE_TTL   = 300  # seconds


def _cached_genre_rows(region, lang, pool, tr):
    key   = f"{region}:{lang}"
    entry = _ROW_CACHE.get(key)
    if entry and (time.time() - entry['at']) < _ROW_CACHE_TTL:
        return entry['rows']
    try:
        rows = _build_genre_rows(pool, tr, region)
        _ROW_CACHE[key] = {'rows': rows, 'at': time.time()}
    except Exception as e:
        app.logger.error(f'Row build error: {e}')
        rows = _ROW_CACHE.get(key, {}).get('rows', [])
    return rows


def _build_genre_rows(pool, tr, region):
    """Compute all genre rows for the home page. Cached by _cached_genre_rows."""
    rows = []

    def add_row(key, subset, **kwargs):
        result = build_row(tr[key], subset, **kwargs)
        if result:
            result['key'] = key
            rows.append(result)

    add_row('trending_now', pool)

    recent = pool[pool['release_date'].apply(lambda d: str(d)[:4] >= '2024')]
    recent_sorted = recent.sort_values('release_date', ascending=False).head(20)
    if len(recent_sorted) >= 4:
        rows.append({'label': tr['new_releases'], 'key': 'new_releases',
                     'cards': [to_dict(r) for _, r in recent_sorted.iterrows()]})

    if has_type:
        add_row('top_movies', pool[pool['type'] == 'Movie'])
        add_row('top_tv',     pool[pool['type'] == 'TV Show'])

    for key, tags in GENRE_ROWS:
        subset = pool[pool['genres'].apply(lambda g: any(tag in str(g) for tag in tags))]
        add_row(key, subset)

    has_origin = 'origin_country' in pool.columns
    african_pool = pool[pool['original_language'].isin(AFRICAN_LANGS)]
    if has_origin:
        african_pool = pool[
            pool['original_language'].isin(AFRICAN_LANGS) |
            pool['origin_country'].isin(AFRICAN_COUNTRIES)
        ]
    add_row('african_stories', african_pool)

    if has_origin:
        nollywood_pool = pool[pool['origin_country'] == 'NG']
        if len(nollywood_pool) >= 4:
            result = build_row(tr.get('nollywood', 'Nollywood'), nollywood_pool)
            if result:
                result['key'] = 'nollywood'
                rows.append(result)
        sa_pool = pool[pool['origin_country'] == 'ZA']
        if len(sa_pool) >= 4:
            result = build_row(tr.get('south_african', 'South African Cinema'), sa_pool)
            if result:
                result['key'] = 'south_african'
                rows.append(result)

    add_row('kdrama',     pool[pool['original_language'] == 'ko'])
    add_row('anime',      pool[(pool['original_language'] == 'ja') &
                               pool['genres'].apply(lambda g: 'Animation' in str(g))])
    add_row('bollywood',  pool[pool['original_language'] == 'hi'])
    add_row('acclaimed',  pool[(pool['vote_average'].fillna(0) >= 8.0) &
                               (pool['vote_count'].fillna(0) >= 500)],
            sort_col='vote_count')
    add_row('lgbtq',      _lgbtq_pool(pool))
    return rows


# ── Pages ───────────────────────────────────────────────────────────────────
def _onboarding_picks(pool):
    """Return diverse picks for the onboarding modal (120 titles max)."""
    seen  = set()
    picks = []
    genre_buckets = [
        ('Action',      ['Action', 'Adventure']),
        ('Comedy',      ['Comedy']),
        ('Drama',       ['Drama']),
        ('Horror',      ['Horror']),
        ('Sci-Fi',      ['Science Fiction', 'Fantasy']),
        ('Thriller',    ['Thriller', 'Crime', 'Mystery']),
        ('Animation',   ['Animation']),
        ('Romance',     ['Romance']),
        ('Documentary', ['Documentary']),
        ('Family',      ['Family', 'Kids']),
    ]
    for genre_label, tags in genre_buckets:
        sub = pool[pool['genres'].apply(lambda g: any(t in str(g) for t in tags))]
        for _, row in sub.nlargest(14, 'popularity').iterrows():
            m = to_dict(row)
            if m['id'] not in seen and m['poster_url'] != NO_POSTER:
                seen.add(m['id'])
                picks.append({**m, 'ob_genre': genre_label})
    for _, row in pool.nlargest(40, 'popularity').iterrows():
        m = to_dict(row)
        if m['id'] not in seen and m['poster_url'] != NO_POSTER:
            seen.add(m['id'])
            picks.append({**m, 'ob_genre': 'Popular'})
    return picks[:120]


@app.route('/')
def home():
    region = _get_region()
    lang   = _get_language()
    tr     = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
    pool   = get_pool(region)

    # Hero — fast single nlargest; translated overview only when needed
    hero = to_dict(pool.nlargest(1, 'popularity').iloc[0])
    if lang != 'en':
        translated = get_translated_overview(hero['id'], hero['type'] == 'TV Show', lang)
        if translated:
            hero = dict(hero)
            hero['overview'] = translated

    # Genre rows — cached per (region, lang) for 5 minutes
    rows = _cached_genre_rows(region, lang, pool, tr)

    show_ob = current_user.is_authenticated and not current_user.onboarded
    return render_template('index.html', hero=hero, genre_rows=rows, region=region,
                           show_ob=show_ob)


@app.route('/onboarding')
def onboarding():
    # Onboarding is now a modal on the homepage; redirect any direct visits
    return redirect('/')


@app.route('/api/onboarding/complete', methods=['POST'])
@login_required
def onboarding_complete():
    titles = request.json.get('titles', [])
    for title in titles:
        row = movies[movies['title'] == title]
        if row.empty:
            continue
        m = to_dict(row.iloc[0])
        if not WatchedItem.query.filter_by(user_id=current_user.id, title=title).first():
            db.session.add(WatchedItem(
                user_id    = current_user.id,
                title      = title,
                poster_url = m['poster_url'],
                year       = m['year'],
                media_type = m['type'],
                rating     = m['vote_average'],
            ))
    current_user.onboarded = True
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/watchlist')
def watchlist_page():
    wl_titles = _wl_titles()
    wl_items  = [to_dict(movies[movies['title']==t].iloc[0]) for t in wl_titles if not movies[movies['title']==t].empty]
    watched_items = []
    if current_user.is_authenticated:
        watched_items = WatchedItem.query.filter_by(user_id=current_user.id)\
                            .order_by(WatchedItem.watched_at.desc()).all()
    suggestions = []
    if wl_titles:
        acc = _aggregate_scores(wl_titles, exclude=set(wl_titles))
        top = sorted(acc.items(), key=lambda x: x[1], reverse=True)[:5]
        suggestions = [to_dict(movies.iloc[i]) for i, _ in top]
    return render_template('watchlist.html', watchlist=wl_items, suggestions=suggestions,
                           watched=watched_items)


# ── API ─────────────────────────────────────────────────────────────────────
@app.route('/api/trending_live')
def trending_live():
    lang   = _get_language()
    results = []
    try:
        tmdb_lang = TMDB_LANG_MAP.get(lang, 'en-US')
        for media in ('movie', 'tv'):
            res = requests.get(
                f"https://api.themoviedb.org/3/trending/{media}/week",
                params={'api_key': TMDB_KEY, 'language': tmdb_lang}, timeout=5
            ).json()
            gmap = {g['id']: g['name'] for g in requests.get(
                f"https://api.themoviedb.org/3/genre/{media}/list",
                params={'api_key': TMDB_KEY, 'language': tmdb_lang}, timeout=3
            ).json().get('genres', [])}
            nk = 'title' if media == 'movie' else 'name'
            dk = 'release_date' if media == 'movie' else 'first_air_date'
            for item in res.get('results', [])[:10]:
                pp = item.get('poster_path', '') or ''
                bp = item.get('backdrop_path', '') or ''
                gnames = ', '.join(gmap.get(gid, '') for gid in item.get('genre_ids', []) if gmap.get(gid))
                results.append({
                    'id':           item['id'],
                    'title':        item.get(nk, ''),
                    'type':         'Movie' if media == 'movie' else 'TV Show',
                    'genres':       gnames,
                    'overview':     item.get('overview', ''),
                    'vote_average': round(_safe_float(item.get('vote_average', 0)), 1),
                    'vote_count':   _safe_int(item.get('vote_count', 0)),
                    'popularity':   round(_safe_float(item.get('popularity', 0)), 1),
                    'year':         str(item.get(dk, ''))[:4],
                    'poster_url':   f"{POSTER_BASE}{pp}" if pp else NO_POSTER,
                    'backdrop_url': f"{BACKDROP_BASE}{bp}" if bp else '',
                    'original_language': item.get('original_language', ''),
                    'is_lgbtq': False,
                })
        results.sort(key=lambda x: x['popularity'], reverse=True)
    except Exception:
        pass
    return jsonify(results[:20])


@app.route('/api/overview/<int:tmdb_id>')
def get_overview(tmdb_id):
    lang  = request.args.get('lang', 'en')
    is_tv = request.args.get('tv', 'false') == 'true'
    overview = get_translated_overview(tmdb_id, is_tv, lang)
    return jsonify({'overview': overview or ''})


@app.route('/api/reviews/<int:tmdb_id>')
def reviews(tmdb_id):
    is_tv = request.args.get('tv', 'false') == 'true'
    media = 'tv' if is_tv else 'movie'
    try:
        data = requests.get(
            f"https://api.themoviedb.org/3/{media}/{tmdb_id}/reviews",
            params={'api_key': TMDB_KEY, 'language': 'en-US'}, timeout=4
        ).json()
        results = []
        for r in data.get('results', [])[:4]:
            details = r.get('author_details', {})
            rating  = details.get('rating')
            avatar  = details.get('avatar_path', '')
            if avatar and str(avatar) not in ('None', 'nan', ''):
                avatar = f"https://image.tmdb.org/t/p/w45{avatar}" if not avatar.startswith('http') else avatar
            else:
                avatar = ''
            results.append({
                'author':  r.get('author', 'Anonymous'),
                'rating':  round(float(rating), 1) if rating else None,
                'content': r.get('content', ''),
                'url':     r.get('url', ''),
                'date':    r.get('created_at', '')[:10],
                'avatar':  avatar,
            })
        return jsonify(results)
    except Exception:
        return jsonify([])


@app.route('/api/tv_info/<int:tmdb_id>')
def tv_info(tmdb_id):
    try:
        data = requests.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}",
            params={'api_key': TMDB_KEY}, timeout=4
        ).json()
        return jsonify({
            'seasons':  data.get('number_of_seasons', 0),
            'episodes': data.get('number_of_episodes', 0),
            'status':   data.get('status', ''),
            'network':  data.get('networks', [{}])[0].get('name', '') if data.get('networks') else '',
            'season_list': [
                {'number': s['season_number'], 'name': s['name'], 'episodes': s['episode_count']}
                for s in data.get('seasons', [])
                if s['season_number'] > 0
            ],
        })
    except Exception:
        return jsonify({'seasons': 0, 'episodes': 0, 'status': '', 'network': '', 'season_list': []})


@app.route('/api/genre_top')
def genre_top():
    genres = request.args.getlist('genres[]') or ([request.args.get('genre', '')] if request.args.get('genre') else [])
    genres = [g for g in genres if g]
    media  = request.args.get('type', '')
    region = _get_region()
    if not genres:
        return jsonify([])
    pool = get_pool(region)

    genre = genres[0] if len(genres) == 1 else None
    if 'LGBTQ+' in genres:
        subset = _lgbtq_pool(pool)
        if media in ('Movie', 'TV Show') and has_type:
            subset = subset[subset['type'] == media]
        items = [to_dict(r) for _, r in subset.nlargest(20, 'popularity').iterrows()]
        return jsonify({'items': items, 'has_more': False, 'offset': len(items)})

    subset = pool[pool['genres'].apply(lambda g: any(gen in str(g) for gen in genres))]
    if media in ('Movie', 'TV Show') and has_type:
        subset = subset[subset['type'] == media]
    offset   = int(request.args.get('offset', 0))
    per_page = 20
    all_items_sorted = [to_dict(r) for _, r in subset.nlargest(500, 'popularity').iterrows()]
    page_items = all_items_sorted[offset:offset + per_page]
    return jsonify({
        'items':    page_items,
        'total':    len(all_items_sorted),
        'has_more': offset + per_page < len(all_items_sorted),
        'offset':   offset + per_page,
    })


def _ranked_titles(q):
    ql    = q.strip().lower()
    exact = [t for t in all_titles if t.lower() == ql]
    start = [t for t in all_titles if t.lower().startswith(ql) and t.lower() != ql]
    cont  = [t for t in all_titles if ql in t.lower() and not t.lower().startswith(ql)]
    return (exact + start + cont)[:40]


@app.route('/api/for_you')
def for_you():
    """
    Personalised feed based on the user's full watch + watchlist history.
    Falls back to trending for anonymous users.
    """
    uid      = current_user.id if current_user.is_authenticated else None
    user_vec = _user_affinity_vector(uid) if uid else None

    if user_vec is None:
        # Anonymous fallback: return top popularity titles
        region = _get_region()
        pool   = get_pool(region)
        items  = [to_dict(r) for _, r in pool.nlargest(20, 'popularity').iterrows()]
        return jsonify({'personalised': False, 'items': items})

    # Exclude titles the user has already interacted with
    seen_titles = {w.title for w in WatchedItem.query.filter_by(user_id=uid).all()} | \
                  {w.title for w in WatchlistItem.query.filter_by(user_id=uid).all()}

    # Rank candidates by user affinity + quality
    scored = []
    for i, aff in user_vec.items():
        row = movies.iloc[i]
        if row['title'] in seen_titles:
            continue
        q     = _quality_score(row)
        rb    = _recency_boost(row)
        score = 0.60 * float(aff) + 0.30 * q + 0.10 * rb
        scored.append((i, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    ordered = _diversify([i for i, _ in scored], max_same_genre=3, top_n=10)
    items   = [to_dict(movies.iloc[i]) for i in ordered[:20]]
    return jsonify({'personalised': True, 'items': items})


@app.route('/api/watchlist_suggestions')
def watchlist_suggestions():
    import random
    wl      = _wl_titles()
    exclude = set(wl)
    if not wl:
        return jsonify([])
    acc  = _aggregate_scores(wl, exclude=exclude)
    top  = sorted(acc.items(), key=lambda x: x[1], reverse=True)[:40]
    pool = [i for i, _ in top]
    chosen = random.sample(pool, min(8, len(pool)))
    return jsonify([to_dict(movies.iloc[i]) for i in chosen])


@app.route('/api/movie_data')
def movie_data():
    title = request.args.get('title', '')
    row   = movies[movies['title'] == title]
    if row.empty:
        return jsonify(None), 404
    return jsonify(to_dict(row.iloc[0]))


@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    ranked = _ranked_titles(q)
    result = []
    for t in ranked:
        row = movies[movies['title'] == t]
        if not row.empty:
            result.append({'title': t, 'type': str(row.iloc[0].get('type', 'Movie')) if has_type else 'Movie'})
    return jsonify(result)


@app.route('/api/search_cards')
def search_cards():
    q        = request.args.get('q', '').strip()
    offset   = int(request.args.get('offset', 0))
    per_page = 20
    if not q: return jsonify({'items': [], 'has_more': False, 'offset': 0, 'total': 0})
    ranked  = _ranked_titles(q)
    all_items_sorted = []
    for t in ranked:
        row = movies[movies['title'] == t]
        if not row.empty:
            all_items_sorted.append(to_dict(row.iloc[0]))
    return jsonify({
        'items':    all_items_sorted[offset:offset + per_page],
        'total':    len(all_items_sorted),
        'has_more': offset + per_page < len(all_items_sorted),
        'offset':   offset + per_page,
    })


@app.route('/api/recommend', methods=['POST'])
def recommend():
    title  = request.json.get('title', '')
    offset = int(request.json.get('offset', 0))
    if title not in all_titles:
        matches = [t for t in all_titles if title.lower() in t.lower()]
        if not matches:
            return jsonify({'error': 'Not found'}), 404
        title = matches[0]
    uid  = current_user.id if current_user.is_authenticated else None
    recs = get_recs(title, offset=offset, user_id=uid)
    if offset == 0:
        return jsonify({'selected': to_dict(movies[movies['title']==title].iloc[0]), **recs})
    return jsonify(recs)


@app.route('/api/random')
def random_pick():
    row   = movies.sample(1).iloc[0]
    title = row['title']
    uid   = current_user.id if current_user.is_authenticated else None
    recs  = get_recs(title, user_id=uid)
    return jsonify({'selected': to_dict(row), **recs})


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
    except Exception:
        return jsonify({'country_code': 'GLOBAL'})


@app.route('/api/set_region', methods=['POST'])
def set_region():
    region = request.json.get('region', 'GLOBAL')
    _save_region(region)
    return jsonify({'region': region})


@app.route('/api/set_language', methods=['POST'])
def set_language():
    language = request.json.get('language', 'en')
    _save_language(language)
    return jsonify({'language': language})


@app.route('/api/watched/add', methods=['POST'])
def watched_add():
    data  = request.json
    title = data.get('title', '')
    if not title:
        return jsonify({'ok': False})
    if current_user.is_authenticated:
        if not WatchedItem.query.filter_by(user_id=current_user.id, title=title).first():
            db.session.add(WatchedItem(
                user_id    = current_user.id,
                title      = title,
                poster_url = data.get('poster_url', ''),
                year       = data.get('year', ''),
                media_type = data.get('type', ''),
                rating     = data.get('vote_average', 0),
            ))
            db.session.commit()
        # Auto-remove from watchlist when marked watched
        WatchlistItem.query.filter_by(user_id=current_user.id, title=title).delete()
        db.session.commit()
    else:
        watched = session.get('watched', [])
        if title not in watched:
            session['watched'] = watched + [title]
        wl = session.get('watchlist', [])
        session['watchlist'] = [t for t in wl if t != title]
    return jsonify({'ok': True})


@app.route('/api/watchlist/add', methods=['POST'])
def wl_add():
    title = request.json.get('title', '')
    if title in all_titles:
        _wl_add(title)
    return jsonify({'count': len(_wl_titles())})


@app.route('/api/watchlist/remove', methods=['POST'])
def wl_remove():
    title = request.json.get('title', '')
    _wl_remove(title)
    return jsonify({'count': len(_wl_titles())})


# ── Email helpers ────────────────────────────────────────────────────────────
def _send_verification_email(user):
    if not app.config['MAIL_USERNAME']:
        return  # email not configured — skip silently
    token = secrets.token_urlsafe(32)
    user.verification_token = token
    db.session.commit()
    verify_url = url_for('verify_email', token=token, _external=True)
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0a0c14;color:#f2f2f6;padding:2rem;border-radius:14px">
      <h1 style="color:#fff;font-size:1.5rem;margin-bottom:.25rem">
        <span style="color:#fff;font-weight:900">MOV.IE</span><span style="color:#9333ea;font-weight:900"> REC</span>
      </h1>
      <h2 style="color:#f2f2f6;font-size:1.2rem;margin-top:1.5rem">Welcome, {user.display_name}! 🎬</h2>
      <p style="color:#7c809a;line-height:1.7">
        Thanks for joining MOV.IE REC — your personal movie &amp; TV show recommender.<br/>
        Please verify your email address to unlock all features.
      </p>
      <a href="{verify_url}"
         style="display:inline-block;margin:1.5rem 0;background:#59005c;color:#fff;text-decoration:none;
                padding:.75rem 2rem;border-radius:10px;font-weight:700;font-size:.95rem">
        Verify my email
      </a>
      <p style="color:#7c809a;font-size:.8rem">This link expires in 24 hours. If you didn't register, ignore this email.</p>
    </div>"""
    try:
        msg = Message('Verify your MOV.IE REC email', recipients=[user.email], html=html)
        mail.send(msg)
    except Exception:
        pass  # don't block registration if email fails


def _send_welcome_email(user):
    if not app.config['MAIL_USERNAME']:
        return
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0a0c14;color:#f2f2f6;padding:2rem;border-radius:14px">
      <h1 style="color:#fff;font-size:1.5rem;margin-bottom:.25rem">
        <span style="color:#fff;font-weight:900">MOV.IE</span><span style="color:#9333ea;font-weight:900"> REC</span>
      </h1>
      <h2 style="color:#f2f2f6;font-size:1.2rem;margin-top:1.5rem">You're in, {user.display_name}! 🎉</h2>
      <p style="color:#7c809a;line-height:1.7">
        Your account is set up and ready to go. Here's what you can do:
      </p>
      <ul style="color:#7c809a;line-height:2">
        <li>🔍 Search any movie or TV show for instant recommendations</li>
        <li>🎲 Use the dice button for a random pick</li>
        <li>📋 Build your personal watchlist</li>
        <li>🎬 Mark titles as watched to improve your recommendations</li>
        <li>🌍 Filter by region to find what's available near you</li>
      </ul>
      <a href="https://movierec-gzsa.onrender.com"
         style="display:inline-block;margin:1.5rem 0;background:#59005c;color:#fff;text-decoration:none;
                padding:.75rem 2rem;border-radius:10px;font-weight:700;font-size:.95rem">
        Start watching
      </a>
      <p style="color:#7c809a;font-size:.8rem">Made with ❤️ by 3N4</p>
    </div>"""
    try:
        msg = Message('Welcome to MOV.IE REC 🎬', recipients=[user.email], html=html)
        mail.send(msg)
    except Exception:
        pass


# ── Auth routes ──────────────────────────────────────────────────────────────
@app.route('/auth/register', methods=['GET', 'POST'])
def register_page():
    if current_user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        name     = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')
        if not email or not password:
            flash('Email and password are required.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('An account with that email already exists. Try signing in instead.', 'error')
        elif name and User.query.filter(
            db.func.lower(User.display_name) == name.lower()
        ).first():
            flash('That display name is already taken. Please choose another.', 'error')
        else:
            user = User(
                email=email,
                display_name=name or email.split('@')[0],
                password_hash=generate_password_hash(password),
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            _migrate_session_wl()
            _send_verification_email(user)
            _send_welcome_email(user)
            return redirect('/')
    return render_template('auth/register.html')


@app.route('/auth/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash('Invalid or expired verification link.', 'error')
        return redirect('/')
    user.email_verified     = True
    user.verification_token = None
    db.session.commit()
    flash('Email verified! Your account is fully active.', 'success')
    return redirect('/')


@app.route('/auth/login', methods=['GET', 'POST'])
def login_page():
    if current_user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user)
            _migrate_session_wl()
            return redirect(request.args.get('next') or '/')
        flash('Invalid email or password.', 'error')
    return render_template('auth/login.html')


@app.route('/auth/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')


@app.route('/auth/google')
def google_auth():
    redirect_uri = url_for('google_callback', _external=True)
    return google_oauth.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def google_callback():
    # ── Stage 1: exchange code for token (Authlib / Google) ─────────────
    try:
        token    = google_oauth.authorize_access_token()
        userinfo = token.get('userinfo') or google_oauth.userinfo()
    except Exception as e:
        app.logger.error(f'Google OAuth token error: {type(e).__name__}: {e}')
        flash('Google sign-in failed. Please try again.', 'error')
        return redirect(url_for('login_page'))

    # ── Stage 2: user lookup / creation (DB ops wrapped separately) ─────
    try:
        email     = (userinfo.get('email') or '').strip().lower()
        google_id = userinfo.get('sub')

        if not email or not google_id:
            flash('Google did not return your email. Please try again.', 'error')
            return redirect(url_for('login_page'))

        # 1. Already linked this Google account
        user = User.query.filter_by(google_id=google_id).first()

        if not user:
            # 2. Email already registered → link Google to existing account
            user = User.query.filter_by(email=email).first()
            if user:
                user.google_id = google_id
                user.avatar    = userinfo.get('picture', '') or user.avatar
                db.session.commit()
            else:
                # 3. Brand new user — ensure display name is unique
                base_name    = userinfo.get('name', email.split('@')[0]).strip()
                display_name = base_name
                counter      = 1
                while User.query.filter(
                    db.func.lower(User.display_name) == display_name.lower()
                ).first():
                    display_name = f"{base_name}{counter}"
                    counter += 1
                user = User(
                    email=email,
                    display_name=display_name,
                    google_id=google_id,
                    avatar=userinfo.get('picture', ''),
                    email_verified=True,
                )
                db.session.add(user)
                db.session.commit()
                _send_welcome_email(user)

        login_user(user)
        _migrate_session_wl()
        return redirect('/')

    except Exception as e:
        app.logger.error(f'Google OAuth callback error: {type(e).__name__}: {e}')
        db.session.rollback()
        flash('Sign-in failed. Please try again.', 'error')
        return redirect(url_for('login_page'))


# ── Create DB tables + migrate new columns ───────────────────────────────────
with app.app_context():
    db.create_all()
    # Add columns introduced after initial deploy (safe — IF NOT EXISTS is PostgreSQL syntax)
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE'))
            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS verification_token VARCHAR(64)'))
            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS onboarded BOOLEAN DEFAULT FALSE'))
            conn.commit()
    except Exception:
        pass  # SQLite doesn't support IF NOT EXISTS — no-op on local dev


if __name__ == '__main__':
    app.run(debug=True, port=5000)
