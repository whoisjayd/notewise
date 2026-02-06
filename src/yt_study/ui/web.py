from pathlib import Path
from typing import Any

from nicegui import ui
from nicegui.elements.html import Html

from ..config import config


class WebVisualizer:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.projects = self._scan_projects()
        self.current_project: dict[str, Any] | None = None
        self.video_player: Html | None = None
        self.content_area: ui.column = None  # type: ignore

    def _scan_projects(self) -> list[dict[str, Any]]:
        projects = []
        # Support both flat and playlist structures
        for md_file in self.output_dir.glob("**/*.md"):
            # Skip files in 'chapters' directory as they are partial
            if "chapters" in md_file.parts:
                continue

            # The slug is usually the parent directory name and also the filename
            slug = md_file.stem
            if md_file.parent.name == slug:
                # This matches our structure: slug/slug.md
                # Try to extract video ID from slug (usually at the end after _)
                video_id = slug.split("_")[-1] if "_" in slug else ""

                # Check if it's in a playlist folder
                playlist = ""
                if md_file.parent.parent != self.output_dir:
                    playlist = md_file.parent.parent.name

                projects.append(
                    {
                        "title": slug.rsplit("_", 1)[0] if "_" in slug else slug,
                        "id": video_id,
                        "path": md_file,
                        "playlist": playlist,
                        "slug": slug,
                    }
                )

        # Sort by playlist and then title
        return sorted(projects, key=lambda x: (x["playlist"], x["title"]))

    def _get_video_url(self, video_id: str, t: int = 0) -> str:
        url = f"https://www.youtube.com/embed/{video_id}?enablejsapi=1"
        if t > 0:
            url += f"&start={t}"
        return url

    def _parse_timestamp(self, ts_str: str) -> int:
        """Convert HH:MM:SS or MM:SS to seconds."""
        parts = ts_str.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return 0
        except ValueError:
            return 0

    def render(self) -> None:
        with ui.header().classes("items-center justify-between"):
            ui.label("yt-study Visualizer").classes("text-2xl font-bold")
            with ui.row():
                ui.button("Refresh", on_click=self.refresh).props(
                    "flat color=white icon=refresh"
                )

        with ui.left_drawer(value=True).classes("bg-slate-100"):
            ui.label("Projects").classes("text-xl font-semibold mb-4")

            # Group projects by playlist
            current_playlist = None
            for p in self.projects:
                if p["playlist"] != current_playlist:
                    current_playlist = p["playlist"]
                    ui.label(current_playlist or "Single Videos").classes(
                        "text-sm font-bold mt-4 mb-1 text-slate-500 uppercase"
                    )

                ui.button(
                    p["title"], on_click=lambda p=p: self.select_project(p)
                ).props("flat align=left").classes("w-full")

        with ui.column().classes("w-full p-4") as self.content_area:
            if not self.projects:
                ui.label("No projects found in output directory.").classes(
                    "text-xl italic text-slate-400"
                )
            else:
                ui.label("Select a project from the sidebar to view details.").classes(
                    "text-xl italic text-slate-400"
                )

    def select_project(self, project: dict[str, Any]) -> None:
        self.current_project = project
        self.content_area.clear()

        with self.content_area:
            ui.label(project["title"]).classes("text-3xl font-bold mb-2")

            with ui.row().classes("w-full gap-4 items-start"):
                # Video Player Section (sticky or fixed width)
                with ui.column().classes("flex-1 max-w-3xl"):
                    self.video_player = ui.html(
                        f'<iframe id="yt-player" width="100%" height="450" '
                        f'src="{self._get_video_url(project["id"])}" '
                        f'frameborder="0" allow="accelerometer; autoplay; '
                        f"clipboard-write; encrypted-media; gyroscope; "
                        f'picture-in-picture" allowfullscreen></iframe>'
                    ).classes("w-full aspect-video shadow-lg rounded-lg mb-4")

                    ui.label(f"Video ID: {project['id']}").classes(
                        "text-sm text-slate-500"
                    )

                # Content Section
                with ui.column().classes(
                    "flex-1 min-w-[400px] max-h-[80vh] overflow-y-auto"
                ):
                    ui.label("Study Notes").classes(
                        "text-2xl font-bold mb-4 border-b w-full"
                    )

                    try:
                        content = project["path"].read_text(encoding="utf-8")
                    except Exception as e:
                        content = f"Error reading file: {e}"

                    # Replace timestamps with clickable links
                    # Pattern matches [HH:MM:SS] or [MM:SS]
                    def replace_ts(match: Any) -> str:
                        ts = match.group(1)
                        seconds = self._parse_timestamp(ts)
                        url = (
                            f"{self._get_video_url(project['id'], seconds)}&autoplay=1"
                        )
                        return (
                            f'<a href="javascript:void(0)" onclick="'
                            "document.getElementById('yt-player').src="
                            f"'{url}'\" class=\"text-blue-600 "
                            f'hover:underline font-mono">[{ts}]</a>'
                        )

                    ui.markdown(content).classes("prose max-w-none")

                    # NiceGUI's markdown doesn't easily support custom link handling
                    # for JS calls inside the markdown block without some hacks
                    # or post-processing.
                    # Alternative: use a regex to find timestamps and wrap them
                    # in something we can intercept.
                    # For now, let's keep it simple. If we want clickable,
                    # we might need to process the markdown ourselves.

                    # Improved timestamp handling:
                    # We can use ui.html if we want full control, or just use
                    # markdown and inject some JS to handle clicks.
                    ui.run_javascript("""
                        document.addEventListener('click', function(e) {
                            if (e.target && e.target.tagName === 'A' &&
                                e.target.textContent.match(
                                    /\\[\\d{1,2}:\\d{2}(:\\d{2})?\\]/
                                )) {
                                const ts = e.target.textContent.replace('[', '')
                                           .replace(']', '');
                                const parts = ts.split(':').reverse();
                                let seconds = 0;
                                if (parts[0]) seconds += parseInt(parts[0]);
                                if (parts[1]) seconds += parseInt(parts[1]) * 60;
                                if (parts[2]) seconds += parseInt(parts[2]) * 3600;

                                const player = document.getElementById('yt-player');
                                const baseUrl = player.src.split('?')[0];
                                player.src = baseUrl + '?enablejsapi=1&start=' +
                                             seconds + '&autoplay=1';
                                e.preventDefault();
                            }
                        });
                    """)

    def refresh(self) -> None:
        self.projects = self._scan_projects()
        ui.notify("Projects refreshed")
        # We might need to refresh the whole page or just the drawer
        # For simplicity, let's just reload the page
        ui.run_javascript("window.location.reload()")


def start_web_ui(
    port: int = 8080, host: str = "0.0.0.0", output_dir: Path | None = None
) -> None:
    if output_dir is None:
        output_dir = config.default_output_dir

    visualizer = WebVisualizer(output_dir)
    visualizer.render()

    ui.run(title="yt-study Visualizer", port=port, host=host, reload=False, show=True)


if __name__ in {"__main__", "__mp_main__"}:
    start_web_ui()
