# Usage Guide

## The `process` Command

The core functionality of `yt-study` is the `process` command.

```bash
yt-study process [OPTIONS] URL_OR_FILE
```

### 1. Processing a Single Video

```bash
yt-study process "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**What Happens:**
-   A dynamic dashboard appears showing metadata fetching.
-   The video transcript is downloaded (handling auto-translation if needed).
-   If chapters are detected, notes are generated per chapter.
-   A final summary table shows success/failure status.

### 2. Processing a Playlist

```bash
yt-study process "https://www.youtube.com/playlist?list=PL..."
```

**What Happens:**
-   Metadata for all videos is fetched in parallel.
-   Videos are processed concurrently (up to `MAX_CONCURRENT_VIDEOS`).
-   The dashboard shows real-time status for each active worker thread.
-   Failed videos (e.g., due to IP blocks) are skipped and reported in the summary.

### 3. Batch Processing (File Input)

If you have a list of disparate videos, save them to a file (e.g., `links.txt`):

```text
https://youtu.be/video1
https://youtu.be/video2
# This is a comment
https://youtu.be/video3
```

Run:
```bash
yt-study process links.txt
```

---

## Options & Flags

### `--output` / `-o`
Specify a custom directory for the generated notes.

```bash
yt-study process "URL" -o ~/Documents/StudyNotes
```

### `--model` / `-m`
Override the default LLM model for this specific run.

```bash
yt-study process "URL" -m gpt-4-turbo
```

### `--language` / `-l`
Specify preferred transcript languages. `yt-study` tries to find a manual transcript in this language first. If not found, it falls back to auto-generated, then translation.

```bash
# Prefer Hindi, then English
yt-study process "URL" -l hi -l en
```

---

## Handling Issues

### IP Blocking
If you see a red warning: `🚫 YouTube IP Block Detected`, it means YouTube is rate-limiting your requests (common with cloud IPs).
**Solution**: Use a residential proxy or VPN, or wait ~1 hour before retrying.

### "Transcripts Disabled"
Some videos have captions completely disabled by the creator. `yt-study` cannot process these videos.
