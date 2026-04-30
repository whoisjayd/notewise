import { createRootRoute } from "@tanstack/react-router";

import { NotFound } from "@/components/NotFound";
import { RootComponent, RootShell } from "@/components/RootDocument";

import appCss from "../styles.css?url";

const SITE_URL = "https://notewise.click";
const SITE_NAME = "NoteWise";
const SITE_TITLE = "NoteWise — YouTube videos into study notes you actually keep";
const SITE_DESCRIPTION =
  "A terminal-native CLI that turns YouTube videos and playlists into hierarchical Markdown study notes, quizzes, transcripts, and PDF / DOCX / HTML exports — through the LLM provider you already pay for.";
const OG_IMAGE = `${SITE_URL}/og-image.png`;
const GITHUB_URL = "https://github.com/whoisjayd/notewise";
const PYPI_URL = "https://pypi.org/project/notewise/";
const DOCS_URL = "https://docs.notewise.click";
const X_PROFILE_URL = "https://x.com/whynotjaydeep";

const SOFTWARE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: SITE_NAME,
  applicationCategory: "DeveloperApplication",
  operatingSystem: "macOS, Linux, Windows",
  description: SITE_DESCRIPTION,
  url: SITE_URL,
  image: OG_IMAGE,
  license: `${GITHUB_URL}/blob/main/LICENSE`,
  downloadUrl: GITHUB_URL,
  codeRepository: GITHUB_URL,
  sameAs: [GITHUB_URL, PYPI_URL, DOCS_URL, X_PROFILE_URL],
  programmingLanguage: "Python",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  author: {
    "@type": "Person",
    name: "Jaydeep Solanki",
    url: X_PROFILE_URL,
    sameAs: ["https://github.com/whoisjayd", X_PROFILE_URL],
  },
};

const ORGANIZATION_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: SITE_NAME,
  url: SITE_URL,
  logo: `${SITE_URL}/favicon.png`,
  sameAs: [GITHUB_URL, PYPI_URL, DOCS_URL, X_PROFILE_URL],
};

const WEBSITE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: SITE_NAME,
  url: SITE_URL,
  description: SITE_DESCRIPTION,
};

const THEME_BOOT_SCRIPT = `(() => {
  try {
    const stored = localStorage.getItem("nw-theme");
    const dark = stored === "dark" || (!stored && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch {
    document.documentElement.classList.toggle("dark", matchMedia("(prefers-color-scheme: dark)").matches);
  }
})();`;

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      {
        name: "viewport",
        content: "width=device-width, initial-scale=1, viewport-fit=cover",
      },
      { title: SITE_TITLE },
      { name: "description", content: SITE_DESCRIPTION },

      {
        name: "robots",
        content: "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1",
      },
      { name: "googlebot", content: "index,follow" },

      {
        name: "theme-color",
        content: "#f8fafc",
        media: "(prefers-color-scheme: light)",
      },
      { name: "theme-color", content: "#0b1118", media: "(prefers-color-scheme: dark)" },
      { name: "color-scheme", content: "light dark" },

      { name: "author", content: "Jaydeep Solanki" },
      { name: "application-name", content: SITE_NAME },
      { name: "apple-mobile-web-app-title", content: SITE_NAME },
      { name: "mobile-web-app-capable", content: "yes" },
      { name: "apple-mobile-web-app-capable", content: "yes" },
      { name: "format-detection", content: "telephone=no" },

      {
        name: "keywords",
        content:
          "youtube to notes, ai study notes, video transcript, markdown notes, study cli, litellm, gemini, openai cli, transcript to pdf, lecture notes, playlist transcripts",
      },

      { property: "og:type", content: "website" },
      { property: "og:site_name", content: SITE_NAME },
      { property: "og:url", content: SITE_URL },
      { property: "og:title", content: SITE_TITLE },
      { property: "og:description", content: SITE_DESCRIPTION },
      { property: "og:locale", content: "en_US" },
      { property: "og:image", content: OG_IMAGE },
      { property: "og:image:secure_url", content: OG_IMAGE },
      { property: "og:image:type", content: "image/png" },
      { property: "og:image:width", content: "1280" },
      { property: "og:image:height", content: "672" },
      {
        property: "og:image:alt",
        content: "NoteWise — A YouTube link, turned into study notes you actually keep.",
      },

      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:url", content: SITE_URL },
      { name: "twitter:title", content: SITE_TITLE },
      { name: "twitter:description", content: SITE_DESCRIPTION },
      { name: "twitter:image", content: OG_IMAGE },
      {
        name: "twitter:image:alt",
        content: "NoteWise — A YouTube link, turned into study notes you actually keep.",
      },
      { name: "twitter:site", content: "@whynotjaydeep" },
      { name: "twitter:creator", content: "@whynotjaydeep" },
    ],
    links: [
      { rel: "canonical", href: SITE_URL },
      { rel: "icon", type: "image/png", href: "/favicon.png" },
      { rel: "apple-touch-icon", href: "/favicon.png" },
      { rel: "manifest", href: "/site.webmanifest" },
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      {
        rel: "preconnect",
        href: "https://fonts.gstatic.com",
        crossOrigin: "anonymous",
      },
    ],
    scripts: [
      {
        children: THEME_BOOT_SCRIPT,
      },
      {
        src: "https://cloud.umami.is/script.js",
        defer: true,
        "data-website-id": "677faf96-24fb-41fd-8edc-5a04c791ef9e",
      },
      {
        type: "application/ld+json",
        children: JSON.stringify(SOFTWARE_JSON_LD),
      },
      {
        type: "application/ld+json",
        children: JSON.stringify(ORGANIZATION_JSON_LD),
      },
      {
        type: "application/ld+json",
        children: JSON.stringify(WEBSITE_JSON_LD),
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFound,
});
