"""Top-level application-wide constants for NoteWise."""

from __future__ import annotations


# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DB_FILENAME = ".notewise_cache.db"
STATE_DIR_NAME = ".notewise"
LOGS_DIR_NAME = "logs"
CONFIG_FILENAME = "config.env"
SESSION_LOG_PREFIX = "notewise"
CHECKSUM_FILENAME = "SHA256SUMS.txt"
GITHUB_REPOSITORY_OWNER = "whoisjayd"
GITHUB_REPOSITORY_NAME = "notewise"
LATEST_RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY_OWNER}/"
    f"{GITHUB_REPOSITORY_NAME}/releases/latest"
)
RELEASES_PAGE_URL = (
    f"https://github.com/{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}/releases"
)
UPDATER_USER_AGENT = "NoteWise-Updater"
UPDATE_HTTP_TIMEOUT_SECONDS = 30
UPDATE_COMMAND_UV = "uv tool upgrade notewise"
UPDATE_COMMAND_PIPX = "pipx upgrade notewise"
UPDATE_COMMAND_PIP = "pip install --upgrade notewise"
UPDATE_INSTALLER_UNIX_URL = (
    f"https://github.com/{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}/"
    "releases/latest/download/install.sh"
)
UPDATE_INSTALLER_WINDOWS_URL = (
    f"https://github.com/{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}/"
    "releases/latest/download/install.ps1"
)
UPDATE_COMMAND_BINARY_UNIX = f"curl -fsSL {UPDATE_INSTALLER_UNIX_URL} | sh"
UPDATE_COMMAND_BINARY_WINDOWS = f"irm {UPDATE_INSTALLER_WINDOWS_URL} | iex"
LEGACY_CONFIG_KEYS = frozenset(
    {
        "YOUTUBE_USE_OAUTH",
        "YOUTUBE_SAVE_OAUTH_TOKEN",
        "YOUTUBE_OAUTH_TOKEN_FILE",
        "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN",
    }
)

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_OUTPUT_DIR = "./output"
DEFAULT_LANGUAGES = ["en"]
DEFAULT_TARGET_LANGUAGE = "English"
DEFAULT_RENDERED_HTML_LANG = "en"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_CONCURRENT_VIDEOS = 5
DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE = 10
DEFAULT_THROTTLE_SECONDS = 0.0
DEFAULT_CHUNK_SIZE = 4000  # tokens
DEFAULT_CHUNK_OVERLAP = 200  # tokens
DEFAULT_CHAPTER_MIN_DURATION = 3600  # seconds (1 hour)
DEFAULT_MAX_CONCURRENT_CHAPTERS = 3
DEFAULT_USE_COMBINE_CHUNK = False
DEFAULT_STITCH_SECTION_BOUNDARY_COUNT = 2
DEFAULT_STITCH_CHAR_BOUNDARY = 6000

# ── Retry ─────────────────────────────────────────────────────────────────────
TRANSCRIPT_MAX_RETRIES = 3
PLAYLIST_MAX_RETRIES = 3
LLM_NUM_RETRIES = 3
HTTP_MAX_RETRIES = 3
HTTP_BACKOFF_BASE = 1.0

# ── Output ────────────────────────────────────────────────────────────────────
MAX_FILENAME_LENGTH = 100
LITELLM_MODELS_SNAPSHOT_FILENAME = "litellm_models_snapshot.json"
DEFAULT_NOTES_OUTPUT_FORMAT = "md"
SUPPORTED_NOTES_OUTPUT_FORMATS = ("md", "html", "pdf", "docx")
OUTPUT_FORMAT_SEPARATOR = ","
NOTES_OUTPUT_EXTENSIONS = {
    "md": ".md",
    "html": ".html",
    "pdf": ".pdf",
    "docx": ".docx",
}
HTML_LANGUAGE_ALIASES = {
    "arabic": "ar",
    "bengali": "bn",
    "english": "en",
    "french": "fr",
    "german": "de",
    "gujarati": "gu",
    "hindi": "hi",
    "italian": "it",
    "japanese": "ja",
    "kannada": "kn",
    "korean": "ko",
    "malayalam": "ml",
    "marathi": "mr",
    "polish": "pl",
    "portuguese": "pt",
    "portuguese (brazil)": "pt-BR",
    "portuguese-brazil": "pt-BR",
    "pt-br": "pt-BR",
    "punjabi": "pa",
    "russian": "ru",
    "spanish": "es",
    "tamil": "ta",
    "telugu": "te",
    "turkish": "tr",
    "urdu": "ur",
}
PDF_UNSUPPORTED_UNICODE_ERROR = (
    "PDF output currently supports Latin-script text only. "
    "Use Markdown, HTML, or DOCX for {target_language} output."
)
MARKDOWN_RENDER_EXTENSIONS = ("extra", "sane_lists")
CHAPTER_BUNDLE_SEPARATOR = "\n\n---\n\n"
DOCX_BODY_FONT_NAME = "Aptos"
DOCX_HEADING_FONT_NAME = "Aptos Display"
DOCX_BODY_FONT_SIZE_PT = 11
DOCX_TITLE_FONT_SIZE_PT = 22
DOCX_HEADING_ONE_FONT_SIZE_PT = 16
DOCX_HEADING_TWO_FONT_SIZE_PT = 13
DOCX_HEADING_THREE_FONT_SIZE_PT = 11
DOCX_BODY_SPACE_AFTER_PT = 6
DOCX_HEADING_SPACE_BEFORE_PT = 10
DOCX_HEADING_SPACE_AFTER_PT = 4
DOCX_SECTION_MARGIN_INCHES = 0.75
DEFAULT_RENDERED_HTML_STYLES = """
body {
    background: #f3f0ea;
    color: #171717;
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 16px;
    line-height: 1.55;
    margin: 0;
}

.document {
    background: #ffffff;
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
    margin: 0 auto;
    max-width: 820px;
    padding: 32px 40px;
}

h1,
h2,
h3,
h4,
h5,
h6 {
    color: #111827;
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.2;
    margin-bottom: 0.35em;
}

h1 {
    border-bottom: 1px solid #e5e7eb;
    font-size: 2rem;
    margin-top: 0;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 1.35rem;
    margin-top: 1.3em;
}

h3 {
    font-size: 1.05rem;
    margin-top: 1.1em;
}

p,
blockquote,
pre,
table {
    margin: 0.55em 0 0.85em;
}

ul,
ol {
    margin: 0.4em 0 0.85em 1.25em;
    padding-left: 0.4em;
}

li {
    margin: 0.2em 0;
}

p code,
li code,
td code,
blockquote code {
    background: #f4f1ea;
    border-radius: 4px;
    font-family: "Courier New", Courier, monospace;
    padding: 0.15em 0.35em;
}

pre {
    background: #171717;
    border-radius: 8px;
    color: #fafaf9;
    overflow-x: auto;
    padding: 14px 16px;
}

pre code {
    background: transparent;
    color: inherit;
    padding: 0;
}

blockquote {
    border-left: 3px solid #d6d3d1;
    color: #57534e;
    margin-left: 0;
    padding-left: 14px;
}

table {
    border-collapse: collapse;
    font-size: 0.95rem;
    width: 100%;
}

th,
td {
    border: 1px solid #d6d3d1;
    padding: 8px 10px;
    text-align: left;
}

th {
    background: #fafaf9;
}

hr {
    border: 0;
    border-top: 1px solid #e7e5e4;
    margin: 1.5em 0;
}
"""
