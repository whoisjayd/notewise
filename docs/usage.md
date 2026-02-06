# 📖 Usage Guide

`yt-study` provides a streamlined CLI for transforming YouTube content into high-quality study notes.

---

## 🚀 The `process` Command

The core functionality of `yt-study` is the `process` command.

```bash
yt-study process [OPTIONS] URL_OR_FILE
```

### 1️⃣ Processing a Single Video
```bash
yt-study process "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```
**What happens**: The video transcript is fetched, logical chapters are identified (either from YouTube or via AI), and detailed study notes are generated for each section.

### 2️⃣ Processing a Playlist
```bash
yt-study process "https://www.youtube.com/playlist?list=PL..."
```
**What happens**: Metadata for all videos is fetched in parallel. Videos are processed concurrently up to your `MAX_CONCURRENT_VIDEOS` setting.

### 3️⃣ Batch Processing from a File
Save your links in a text file (one per line):
```bash
yt-study process links.txt
```

---

## 🌐 Web Visualizer

Browse your generated notes in a beautiful, searchable web interface:

```bash
yt-study serve
```
Then open `http://localhost:8000` in your browser.

---

## 🛠️ Options & Flags

| Flag | Shorthand | Description |
| :--- | :--- | :--- |
| `--output` | `-o` | Custom directory for generated notes. |
| `--model` | `-m` | Override the default LLM model. |
| `--language` | `-l` | Specify preferred transcript languages. |
| `--temperature` | `-t` | LLM response temperature (0.0 to 1.0). |
| `--export-transcript` | `--raw` | Save the raw timestamped transcript. |
| `--no-synthetic` | | Disable AI-powered chapter detection. |

---

## 📂 Output Structure

`yt-study` organizes content into a structured directory named after the video:

```text
output/
└── {video_title}_{video_id}/
    ├── {video_title}_{video_id}.md  # Combined study notes
    ├── transcript.txt               # Raw transcript (if requested)
    ├── chapters.json                # Raw chapter metadata and structure
    ├── chapters/                    # Individual chapter notes
    └── chunks/                      # Intermediate processing segments
```

---

## ⚠️ Common Issues

### 🚫 IP Blocking
If you see a `YouTube IP Block Detected` warning, YouTube is rate-limiting your requests.
**Solution**: Wait ~1 hour, use a VPN, or reduce concurrency to 1.

### 🔇 Transcripts Disabled
If a video owner has disabled captions, `yt-study` cannot process the video as it relies on transcript data.
