import re

from pathvalidate import sanitize_filename as strict_sanitize


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string to be used as a filename.
    Respects OS constraints (Windows reserved names, length, etc.).
    """
    # Use pathvalidate for robust cross-platform sanitization
    sanitized = strict_sanitize(name, replacement_text="_")

    # Replace multiple spaces with single space
    sanitized = re.sub(r"\s+", " ", sanitized)

    # Trim and limit length
    # pathvalidate handles length but we keep a conservative limit
    sanitized = sanitized.strip()[:100]

    return sanitized if sanitized else "untitled"


def get_video_slug(title: str, video_id: str) -> str:
    """
    Generate a unique slug for a video using its title and ID.
    Format: {sanitized_title}_{video_id}
    """
    safe_title = sanitize_filename(title)
    return f"{safe_title}_{video_id}"
