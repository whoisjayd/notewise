# 🙋 Frequently Asked Questions

Common questions and troubleshooting tips for `yt-study`.

---

## 🔍 General

### What exactly does `yt-study` do?
It's a CLI tool that downloads YouTube transcripts and uses Large Language Models (LLMs) to transform them into structured, academic-quality study notes, complete with summaries, code blocks, and clickable timestamps.

### Is it free to use?
The tool is open-source and free. However, you are responsible for any costs associated with the LLM APIs you use.
**Pro-tip**: Google Gemini (`gemini-2.0-flash`) currently offers a very generous free tier that works excellently with this tool.

### Does it download the actual video?
No, `yt-study` only downloads metadata and transcripts. This keeps the tool fast and avoids the legal/technical complexities of video downloading.

---

## 🛠️ Troubleshooting

### 🔴 Error: "YouTube IP Block Detected"
**Cause**: YouTube rate-limits requests from certain IP ranges (especially cloud providers like AWS/GCP).
**Solutions**:
1.  **Wait**: Simply wait ~1 hour for the limit to reset.
2.  **Slow Down**: Reduce `MAX_CONCURRENT_VIDEOS` to `1` in your config.
3.  **VPN**: Use a residential VPN or proxy.

### 🔇 Error: "Transcripts Disabled"
**Cause**: The video creator has explicitly turned off captions for that video.
**Solution**: Unfortunately, `yt-study` cannot process these videos as it requires transcript data to function.

### ⚪ Why are some sections missing?
**Cause**: Usually due to LLM context limits or the model skipping content.
**Solutions**:
- Try a more capable model like `claude-3-5-sonnet`.
- Decrease the `CHUNK_SIZE` in your config to process smaller, more manageable segments.

---

## 🤖 Models & Providers

### Which model is the best?
- **Best Formatting**: `anthropic/claude-3-5-sonnet-20241022`
- **Best Value/Free**: `gemini/gemini-2.0-flash`
- **Best for Long Content**: `gemini/gemini-1.5-pro` (huge context window)

### Can I use local models?
Yes! Through [LiteLLM](https://docs.litellm.ai/), you can use **Ollama**.
1. Start Ollama.
2. Run `yt-study process "URL" --model ollama/llama3`.

---

## 📂 Features & Integration

### Can I export to Obsidian?
Yes! Since the output is standard Markdown, you can set your `OUTPUT_DIR` directly to your Obsidian Vault directory.

### Does it support playlists?
Yes! Simply provide the playlist URL to the `process` command, and it will handle everything in parallel.

### Is there a GUI?
Yes! Run `yt-study serve` to launch the local web visualizer and browse your notes library in your browser.
