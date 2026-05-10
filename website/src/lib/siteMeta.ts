export const SITE_URL = "https://notewise.click";
export const SITE_NAME = "NoteWise";
export const SITE_TITLE = "NoteWise — YouTube videos into study notes you actually keep";
export const SITE_DESCRIPTION =
  "A terminal-native CLI that turns YouTube videos and playlists into hierarchical Markdown study notes, quizzes, transcripts, and PDF / DOCX / HTML exports — through the LLM provider you already pay for.";
export const GITHUB_URL = "https://github.com/whoisjayd/notewise";
export const PYPI_URL = "https://pypi.org/project/notewise/";
export const DOCS_URL = `${SITE_URL}/docs`;
export const X_PROFILE_URL = "https://x.com/whynotjaydeep";
export const OG_IMAGE = `${SITE_URL}/og-image.png`;

export function absoluteSiteUrl(path: string) {
  return `${SITE_URL}${path}`;
}
