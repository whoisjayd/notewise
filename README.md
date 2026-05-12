<div align="center">

# 🎓 NoteWise

**Convert YouTube videos and playlists into local study notes from your terminal.**

<br />

<img src="https://img.shields.io/pypi/v/notewise?style=flat-square&label=version" alt="version" /> <img src="https://img.shields.io/badge/status-stable-10b981?style=flat-square" alt="stable" /> <img src="https://img.shields.io/badge/license-MIT--Attribution-10b981?style=flat-square" alt="license" /> <img src="https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13%20|%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="python versions" /> <img src="https://img.shields.io/github/actions/workflow/status/whoisjayd/notewise/ci-main.yml?branch=main&style=flat-square&label=CI&logo=github" alt="CI" /> <img src="https://img.shields.io/badge/LiteLLM-powered-ff6b35?style=flat-square" alt="litellm" /> <a href="https://codecov.io/gh/whoisjayd/notewise" >
<img src="https://codecov.io/gh/whoisjayd/notewise/branch/main/graph/badge.svg?token=BY08LAOBWV"/>
</a>
<br /><br />

[Website](https://notewise.click) · [Docs](https://notewise.click/docs) · [Install](https://notewise.click/install) · [Quickstart](https://notewise.click/docs/start/quickstart) · [Contributing](CONTRIBUTING.md)

</div>

## 💡 Why NoteWise?

YouTube has become one of the richest learning platforms on the planet — university lectures, conference talks, technical deep-dives, language lessons, and entire courses are all freely available. But video is a passive medium. You watch, you nod, and two days later the details are gone.

**NoteWise was built to fix that gap.**

The idea is simple: your time watching a video is valuable. The notes that _should_ come from it — the structured, searchable, reviewable kind — should not require an extra hour of your day. NoteWise automates that step. Point it at a YouTube URL and walk away with local Markdown study notes that are deeper and more useful than most people would write by hand.

**Where it shines:**

- 📚 **Students** catching up on lecture recordings or supplementing textbooks with YouTube explanations
- 🧑‍💻 **Developers** staying on top of conference talks, tutorials, and technical deep-dives without watching at 3x speed
- 🌍 **Language learners** extracting structured notes from native-language content
- 📋 **Researchers** quickly distilling hours of talks into organized, searchable reference material
- 🏢 **Teams** turning internal video presentations into shareable written documentation

The output is not just a transcript summary. It is structured, hierarchical Markdown with headers, sub-topics, definitions, examples, and concepts explained in depth. Chapter-aware videos can be split into per-chapter files, and long courses can be processed into organized local notes. Everything lands in your filesystem: portable, searchable, and permanently yours.

## Quick start

```bash
uv tool install notewise
notewise setup
notewise process "https://youtu.be/VIDEO_ID"
```

Generated notes land in `./output` by default.

Prefer another install method?

```bash
# Try without installing
uvx notewise --help

# Standalone binary installer
curl -fsSL https://notewise.click/install | sh
```

Windows PowerShell:

```powershell
irm https://notewise.click/install | iex
```

See the full [installation guide](https://notewise.click/docs/start/install) for `uv`, `uvx`, `pipx`, `pip`, Docker, and standalone binaries.

## Demo

<p align="center">
  <img src="demo/notewise.gif" alt="NoteWise CLI demo" />
</p>

<p align="center">
  <sub>Watch the full demo: <a href="demo/notewise.mp4">demo/notewise.mp4</a></sub>
</p>

## Documentation

| Need                         | Go here                                                                  |
| ---------------------------- | ------------------------------------------------------------------------ |
| Install choices              | [Install NoteWise](https://notewise.click/docs/start/install)            |
| First successful run         | [Quickstart](https://notewise.click/docs/start/quickstart)               |
| Processing flags and formats | [Process videos](https://notewise.click/docs/use/process)                |
| Provider/model setup         | [Providers](https://notewise.click/docs/config/providers)                |
| OAuth providers              | [OAuth](https://notewise.click/docs/config/oauth)                        |
| Playlists and batches        | [Playlists & batches](https://notewise.click/docs/use/playlists-batches) |
| Troubleshooting              | [Troubleshooting](https://notewise.click/docs/operate/troubleshooting)   |
| CLI command reference        | [Commands](https://notewise.click/docs/operate/commands)                 |

## Common commands

```bash
notewise process "https://youtu.be/VIDEO_ID" --format md,docx --quiz
notewise process "https://youtube.com/playlist?list=PLAYLIST_ID"
notewise doctor
notewise update
```

`notewise update` checks the latest release and prints the right upgrade command group for standalone binary or Python package installs. Run `notewise --help` or open the [command reference](https://notewise.click/docs/operate/commands) for the full CLI surface.

## Development

```bash
git clone https://github.com/whoisjayd/notewise
cd notewise
uv sync --dev
make test
```

Website work uses Bun from `website/`:

```bash
bun install --frozen-lockfile
bun run lint
bunx tsc --noEmit
bun run build
```

Docs live in `docs/`. Do not run Prettier on Mintlify MDX; validate docs config with:

```bash
python -m json.tool docs/docs.json
node --check docs/umami.js
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

## License

[MIT with Attribution](LICENSE). If you use NoteWise in a project or build on top of it, include credit and a link back to this repository.

## Thanks

NoteWise is built on a great open-source ecosystem. See [GRATITUDE.md](GRATITUDE.md) for acknowledgements.

Found a bug? [Open an issue](https://github.com/whoisjayd/notewise/issues/new/choose). Security concern? See [SECURITY.md](SECURITY.md).
