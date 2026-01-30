# Configuration

`yt-study` leverages LiteLLM to support virtually any LLM provider.

## Setup Wizard

The easiest way to configure is via the interactive wizard:

```bash
yt-study setup
```

This will prompt you for:
1.  **Provider**: (e.g., Google, OpenAI, Anthropic)
2.  **Model**: (e.g., `gemini-1.5-flash`)
3.  **API Key**: Securely saved to `~/.yt-study/config.env`
4.  **Concurrency**: Max parallel video processing threads (Default: 5)

## Environment Variables

You can manually configure `yt-study` by creating or editing `~/.yt-study/config.env`. You can also set these variables in your shell environment.

### Core Settings

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DEFAULT_MODEL` | The LLM model string to use. | `gemini/gemini-2.0-flash` |
| `OUTPUT_DIR` | Directory to save notes. | `./output` |
| `MAX_CONCURRENT_VIDEOS` | Number of parallel downloads. | `5` |

### API Keys

The application automatically syncs these keys to the process environment for the underlying LLM libraries.

| Provider | Environment Variable |
| :--- | :--- |
| **Google Gemini** | `GEMINI_API_KEY` |
| **OpenAI** | `OPENAI_API_KEY` |
| **Anthropic** | `ANTHROPIC_API_KEY` |
| **Groq** | `GROQ_API_KEY` |
| **xAI (Grok)** | `XAI_API_KEY` |
| **Mistral** | `MISTRAL_API_KEY` |
| **DeepSeek** | `DEEPSEEK_API_KEY` |

## Advanced Model Selection

You can use any model string supported by [LiteLLM](https://docs.litellm.ai/docs/providers).

### Recommended Models

-   **Speed & Cost**: `gemini/gemini-1.5-flash`, `gpt-4o-mini`, `groq/llama-3.1-8b-instant`
-   **Quality & Reasoning**: `gemini/gemini-1.5-pro`, `gpt-4o`, `anthropic/claude-3-5-sonnet-20241022`
-   **Long Context**: `gemini/gemini-1.5-pro` (2M context window is excellent for 10h+ videos)

### Testing a Model

You can override the configured model for a single run:

```bash
yt-study process "URL" --model ollama/llama3
```
