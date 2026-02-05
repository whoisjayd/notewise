## General

### What is `yt-study`?
It is a command-line tool that downloads YouTube transcripts and uses AI (LLMs) to generate structured, academic-quality notes.

### Is it free?
The tool itself is open-source and free. However, it relies on LLM providers (like OpenAI or Anthropic) which may cost money depending on your usage. We recommend **Google Gemini** (specifically `gemini-2.0-flash` or `gemini-1.5-flash`) as it currently offers a generous free tier.

---

## Troubleshooting

### 🔴 Error: "YouTube IP Block Detected"
**Cause:** YouTube aggressively rate-limits requests from data center IP addresses (like AWS, GCP, Azure) and sometimes even residential IPs if too many requests are made quickly.
**Solution:**
1.  **Wait**: Pause for 1-2 hours.
2.  **Concurrency**: Reduce `MAX_CONCURRENT_VIDEOS` in your config to `1` or `2`.
3.  **VPN/Proxy**: Use a residential VPN or proxy service.
4.  **Cookies**: (Coming Soon) Authenticated requests are less likely to be blocked.

### 🟡 Error: "Transcripts Disabled"
**Cause:** The video owner has explicitly disabled captions/transcripts for that video.
**Solution:** Unfortunately, `yt-study` cannot generate notes without a transcript.

### ⚪ No Chapters found
**Cause:** Some videos don't have native YouTube chapters defined by the creator.
**Solution:** `yt-study` now includes a **Synthetic Chapter Engine**. By default, it will use AI to identify logical sections in the transcript and generate chapters for you. You can disable this with `--no-synthetic`.

### 🟡 Error: "No transcript found in supported languages"
**Cause:** The video does not have manual or auto-generated captions in the languages specified.
**Solution:**
-   Try running with `-l en` (default) to see if English auto-generated captions exist.
-   The tool attempts to translate transcripts to English automatically, but this requires at least *one* source transcript to exist.

### ⚪ Output is cut off or incomplete
**Cause:** The LLM output limit (`max_tokens`) might be too low, or the context window was exceeded.
**Solution:**
-   Try a model with a larger context window (e.g., `gemini-1.5-pro` or `claude-3-5-sonnet`).
-   Adjust `chunk_size` in the configuration or use the `--chunk-size` flag to process smaller segments.

---

## Configuration & Models

### Which model should I use?
-   **Best Value**: `gemini/gemini-2.0-flash` (Fast, often free, large context).
-   **Best Quality**: `anthropic/claude-3-5-sonnet-20241022` (Excellent formatting and reasoning).
-   **Local/Private**: You can use Ollama models via LiteLLM (e.g., `ollama/llama3`), but performance varies.

### How do I change the default model?
Run `yt-study setup` again, or edit `~/.yt-study/config.env` and change `DEFAULT_MODEL`.

### Can I process private playlists?
Currently, `yt-study` only supports public and unlisted videos. Support for private playlists (requiring authentication cookies) is on the roadmap.

---

## Features

### Does it support other sites (Twitch, Vimeo)?
Not yet. Currently, it is optimized specifically for YouTube's transcript API.

### Can I export to Notion/Obsidian?
The output files are standard Markdown (`.md`).
-   **Obsidian**: Just set your `OUTPUT_DIR` to your Obsidian vault.
-   **Notion**: You can copy-paste the markdown content. Direct Notion sync is planned for a future release.
