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

- A dynamic dashboard appears showing metadata fetching.
- The video transcript is downloaded (handling auto-translation if needed).
- If chapters are detected, notes are generated per chapter.
- A final summary table shows success/failure status.

### 2. Processing a Playlist

```bash
yt-study process "https://www.youtube.com/playlist?list=PL..."
```

**What Happens:**

- Metadata for all videos is fetched in parallel.
- Videos are processed concurrently (up to `MAX_CONCURRENT_VIDEOS`).
- The dashboard shows real-time status for each active worker thread.
- Failed videos (e.g., due to IP blocks) are skipped and reported in the summary.

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

### `--temperature` / `-t`

Override the LLM response temperature (default: 0.7). Range: 0.0 (precise/predictable) to 1.0 (creative/prolific).

### `--max-tokens` / `-k`

Set the maximum number of tokens for the LLM response. Useful for controlling costs or preventing truncated output on smaller models.

### `--export-transcript` / `--raw`

Save the raw, timestamped transcript to a text file in the output directory. Useful for verification or manual reference.

### `--no-chapters`

Disable the use of native YouTube chapters. `yt-study` will ignore any chapters provided by the video creator.

### `--no-synthetic`

Disable the generation of synthetic chapters. By default, if a video lacks native chapters, AI is used to identify logical sections.

### `--chunk-size`

Override the default token limit for transcript chunks (default: 4000).

### `--chunk-overlap`

Override the default token overlap between chunks (default: 200).

---

## Output Structure

`yt-study` organizes all generated materials into a structured directory named after the video slug (`{title}_{video_id}`):

```text
output/
└── {video_title}_{video_id}/
    ├── {video_title}_{video_id}.md  # Final combined study notes
    ├── {video_title}_transcript.txt  # Raw transcript (if --export-transcript is used)
    ├── chapters/                     # Individual chapter notes (for videos > 1hr)
    │   ├── 01_Introduction.md
    │   ├── 02_Deep_Dive.md
    │   └── ...
    └── chunks/                       # Intermediate chunk notes (for multi-chunk processing)
        ├── 01_chunk.md
        ├── 02_chunk.md
        └── ...
```

### Directory Logic

- **`chapters/` folder**: Created only for videos longer than 1 hour where chapters (native or synthetic) are available.
- **`chunks/` folder**: Created whenever the transcript is too long for a single LLM pass and must be processed in segments. Each file contains a segment of the notes before they are merged into the final document.


### Metadata (YAML Frontmatter)

Intermediate files in the `chunks/` directory include YAML frontmatter containing useful metadata:

```markdown
---
{
  "video_id": "dQw4w9WgXcQ",
  "chunk_index": 1,
  "total_chunks": 5,
  "video_title": "Never Gonna Give You Up"
}
---

# Chunk Content Starts Here...
```

This structure ensures that you not only get a polished final document but also have access to the granular building blocks used to create it.

---

## Handling Issues

### IP Blocking

If you see a red warning: `🚫 YouTube IP Block Detected`, it means YouTube is rate-limiting your requests (common with cloud IPs).
**Solution**: Use a residential proxy or VPN, or wait ~1 hour before retrying.

### "Transcripts Disabled"

Some videos have captions completely disabled by the creator. `yt-study` cannot process these videos.
