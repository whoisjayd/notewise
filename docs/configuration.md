# ⚙️ Configuration

`yt-study` is designed to be highly customizable. You can configure it via the interactive wizard or environment variables.

---

## 🧙 Setup Wizard

The easiest way to configure the application is by running:

```bash
yt-study setup
```

This interactive tool will help you set up:
1.  **Provider**: Choose your LLM provider (Google, OpenAI, Anthropic, etc.)
2.  **Model**: Select your preferred model (e.g., `gemini-2.0-flash`).
3.  **API Key**: Securely stored in your local configuration.

---

## 📄 Environment Variables

You can manually configure settings by editing `~/.yt-study/config.env` or setting variables in your shell.

### 核心设置 (Core Settings)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DEFAULT_MODEL` | The LLM model string to use. | `gemini/gemini-2.0-flash` |
| `OUTPUT_DIR` | Directory to save generated notes. | `./output` |
| `MAX_CONCURRENT_VIDEOS` | Max parallel video threads. | `5` |
| `TEMPERATURE` | LLM creativity (0.0 to 1.0). | `0.7` |

### 🔑 API Keys

| Provider | Environment Variable |
| :--- | :--- |
| **Google Gemini** | `GEMINI_API_KEY` |
| **OpenAI** | `OPENAI_API_KEY` |
| **Anthropic** | `ANTHROPIC_API_KEY` |
| **Groq** | `GROQ_API_KEY` |
| **Mistral** | `MISTRAL_API_KEY` |

---

## 🤖 Advanced Model Selection

We use [LiteLLM](https://docs.litellm.ai/docs/providers), which supports hundreds of models.

### Recommended Models
- **Speed & Cost**: `gemini/gemini-1.5-flash` or `gpt-4o-mini`
- **Quality**: `claude-3-5-sonnet-20241022` or `gemini/gemini-1.5-pro`
- **Local**: `ollama/llama3` (Requires Ollama to be running)

### On-the-fly Override
You can override the model for a single command without changing your config:
```bash
yt-study process "URL" --model gpt-4o
```
