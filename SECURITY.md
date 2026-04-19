# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability within `notewise`, please do **NOT** open a public issue on GitHub.

Instead, please send an email to:
**contactjaydeepsolanki@gmail.com**

We will review the issue and respond as soon as possible.

## Supported Versions

Security fixes are provided for the latest maintained release line.

| Version | Supported          |
| ------- | ------------------ |
| 1.2.x   | :white_check_mark: |
| < 1.2.0 | :x:                |

## Security Best Practices

`notewise` handles API keys for various LLM providers.
- Keys are stored locally in `~/.notewise/config.env`.
- Keys are loaded into environment variables only at runtime.
- We **NEVER** log API keys to the console or log files.
- We rely on `litellm` and official provider libraries for secure API communication over HTTPS.

Please ensure you keep your local `config.env` file secure and do not share it.
