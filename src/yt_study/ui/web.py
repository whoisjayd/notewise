from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from nicegui import ui
from nicegui.elements.html import Html

from ..core.telemetry import POSTHOG_API_KEY, POSTHOG_HOST, telemetry
from ..config import config


class WebVisualizer:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.tree_data: List[Dict[str, Any]] = []
        self.current_video_id: Optional[str] = None
        self.current_path: Optional[Path] = None
        self.is_editing = False

        # UI Elements (initialized in render)
        self.tree: ui.tree = None  # type: ignore
        self.markdown_view: ui.markdown = None  # type: ignore
        self.editor_container: ui.column = None  # type: ignore
        self.editor: ui.textarea = None  # type: ignore
        self.video_player: ui.html = None  # type: ignore
        self.title_label: ui.label = None  # type: ignore
        self.edit_btn: ui.button = None  # type: ignore
        self.save_btn: ui.button = None  # type: ignore

        self.refresh_data()

    def refresh_data(self) -> None:
        """Scan output directory and build tree data."""
        self.tree_data = []

        # 1. Group by playlist/standalone
        playlists: Dict[str, List[Path]] = {}
        standalone: List[Path] = []

        if not self.output_dir.exists():
            return

        for item in self.output_dir.iterdir():
            if item.is_dir():
                # Check if it's a playlist dir (contains subdirs which are videos)
                # or a video dir (contains .md file with same name)
                is_video_dir = (item / f"{item.name}.md").exists() or (item / "chapters").exists()

                if is_video_dir:
                    standalone.append(item)
                else:
                    # Likely a playlist directory
                    videos = []
                    for sub in item.iterdir():
                        if sub.is_dir() and ((sub / f"{sub.name}.md").exists() or (sub / "chapters").exists()):
                            videos.append(sub)
                    if videos:
                        playlists[item.name] = sorted(videos)

        # 2. Build Tree Nodes
        # Playlists
        for pl_name, video_dirs in sorted(playlists.items()):
            pl_node = {
                "id": f"pl_{pl_name}",
                "label": pl_name,
                "icon": "folder",
                "children": [],
            }
            for v_dir in video_dirs:
                pl_node["children"].append(self._build_video_node(v_dir)) # type: ignore
            self.tree_data.append(pl_node)

        # Standalone videos
        if standalone:
            standalone_node = {
                "id": "standalone",
                "label": "Videos",
                "icon": "video_library",
                "children": [],
            }
            for v_dir in sorted(standalone):
                standalone_node["children"].append(self._build_video_node(v_dir)) # type: ignore
            self.tree_data.append(standalone_node)

    def _build_video_node(self, v_dir: Path) -> Dict[str, Any]:
        slug = v_dir.name
        video_id = slug.split("_")[-1] if "_" in slug else ""
        title = slug.rsplit("_", 1)[0] if "_" in slug else slug

        main_md = v_dir / f"{slug}.md"
        chapters_dir = v_dir / "chapters"

        children = []
        if main_md.exists():
            children.append({
                "id": str(main_md),
                "label": "Full Summary",
                "icon": "description",
                "video_id": video_id,
                "path": str(main_md)
            })

        if chapters_dir.exists():
            chapters_node = {
                "id": f"chapters_{slug}",
                "label": "Chapters",
                "icon": "folder",
                "children": []
            }
            for ch_file in sorted(chapters_dir.glob("*.md")):
                chapters_node["children"].append({
                    "id": str(ch_file),
                    "label": ch_file.stem.replace("_", " "),
                    "icon": "segment",
                    "video_id": video_id,
                    "path": str(ch_file)
                })
            if chapters_node["children"]:
                children.append(chapters_node)

        return {
            "id": f"video_{slug}",
            "label": title,
            "icon": "movie",
            "children": children
        }

    def _get_video_url(self, video_id: str, t: int = 0) -> str:
        url = f"https://www.youtube.com/embed/{video_id}?enablejsapi=1&rel=0"
        if t > 0:
            url += f"&start={t}"
        return url

    def _parse_timestamp(self, ts_str: str) -> int:
        parts = ts_str.strip("[]").split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return 0
        except ValueError:
            return 0

    def handle_tree_select(self, e: Any) -> None:
        """Handle selection in the navigation tree."""
        node_id = e.value
        if not node_id:
            return

        # Find the node in tree_data (recursive search)
        node = self._find_node(self.tree_data, node_id)
        if node and "path" in node:
            self.load_content(node["path"], node.get("video_id"))

    def _find_node(self, nodes: List[Dict[str, Any]], target_id: str) -> Optional[Dict[str, Any]]:
        for n in nodes:
            if n["id"] == target_id:
                return n
            if "children" in n:
                found = self._find_node(n["children"], target_id)
                if found:
                    return found
        return None

    def load_content(self, path: Any, video_id: Optional[str]) -> None:
        if path is None:
            return
        path = Path(path)
        self.current_path = path
        self.current_video_id = video_id

        try:
            content = path.read_text(encoding="utf-8")
            # Process timestamps for markdown
            # Pattern: [00:00:00] or [00:00]
            processed_content = re.sub(
                r"\[(\d{1,2}:\d{2}(?::\d{2})?)\](?:\([^)]+\))?",
                r'<span class="timestamp-link" data-timestamp="\1">[\1]</span>',
                content
            )
            self.current_content = content
            self.markdown_view.content = processed_content
            self.title_label.text = path.stem.replace("_", " ")

            if video_id:
                self.update_video(video_id)

            self.markdown_view.set_visibility(True)
            self.editor_container.set_visibility(False)
            self.is_editing = False
            self.edit_btn.set_visibility(True)
        except Exception as e:
            ui.notify(f"Error loading content: {e}", type="negative")

    def update_video(self, video_id: str, t: int = 0) -> None:
        url = self._get_video_url(video_id, t)
        if t > 0:
            url += "&autoplay=1"
        self.video_player.content = (
            f'<iframe id="yt-player" width="100%" height="100%" '
            f'src="{url}" frameborder="0" allow="accelerometer; autoplay; '
            f'clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
            f'allowfullscreen></iframe>'
        )

    def toggle_edit(self) -> None:
        if self.is_editing:
            # Save (called from save button)
            pass
        else:
            self.is_editing = True
            self.editor.value = self.current_content
            self.markdown_view.set_visibility(False)
            self.editor_container.set_visibility(True)
            self.edit_btn.set_visibility(False)

    async def save_content(self) -> None:
        if not self.current_path:
            return

        try:
            new_content = self.editor.value
            self.current_path.write_text(new_content, encoding="utf-8")
            ui.notify("Saved successfully", color="positive")
            self.load_content(self.current_path, self.current_video_id)
        except Exception as e:
            ui.notify(f"Error saving: {e}", type="negative")

    def render(self) -> None:
        ui.dark_mode().enable()

        # Inject PostHog Telemetry and Session Replay
        if telemetry.is_enabled:
            ui.add_head_html(f"""
                <script>
                !function(t,e){{var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){{function g(t,e){{var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){{t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}}}((p=t.createElement("script")).type="text/javascript",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){{var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e}},u.capture=function(t,o,n){{u.push(["capture",t,o,n])}},u.set_config=function(t){{u.push(["set_config",t])}},u.register=function(t){{u.push(["register",t])}},u.register_once=function(t){{u.push(["register_once",t])}},u.unregister=function(t){{u.push(["unregister",t])}},u.identify=function(t,o){{u.push(["identify",t,o])}},u.alias=function(t,o){{u.push(["alias",t,o])}},u.set_person_properties=function(t,o){{u.push(["set_person_properties",t,o])}},u.group=function(t,o,n,p){{u.push(["group",t,o,n,p])}},u.page_view=function(t,o){{u.push(["page_view",t,o])}},u.reset=function(t){{u.push(["reset",t])}},u.get_distinct_id=function(t){{return u.get_property("distinct_id")}},u.get_groups=function(){{return u.get_property("$groups")}},u.get_group_id=function(t){{return u.get_property("$group_0")}},u.get_property=function(t){{return u._get_prop(t)}},u.on=function(t,e){{u.push(["on",t,e])}},u.off=function(t,e){{u.push(["off",t,e])}},u.get_session_id=function(){{return u.get_property("$session_id")}},u.get_session_replay_url=function(){{return u.get_property("$session_replay_url")}},o=["capture","identify","alias","people.set","people.set_once","people.unset","people.increment","people.append","people.union","people.track_charge","people.clear_charges","people.delete_user","set_config","register","register_once","unregister","group","on","off","get_session_id","get_session_replay_url"],n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])}},e.__SV=1.0)}}(document,window.posthog||[]);
                posthog.init('{POSTHOG_API_KEY}',{{api_host:'{POSTHOG_HOST}', person_profiles: 'identified_only', disable_session_recording: false}})
                posthog.identify('{telemetry.distinct_id}')
                </script>
            """)

        ui.add_head_html("""
            <style>
                .prose h1 { font-size: 2.25rem; font-weight: 800; margin-bottom: 1.5rem; color: #f8fafc; }
                .prose h2 { font-size: 1.5rem; font-weight: 700; margin-top: 2rem; margin-bottom: 1rem; color: #f1f5f9; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }
                .prose h3 { font-size: 1.25rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.75rem; color: #e2e8f0; }
                .prose p { margin-bottom: 1.25rem; line-height: 1.75; color: #cbd5e1; }
                .prose a { color: #38bdf8; text-decoration: none; }
                .prose a:hover { text-decoration: underline; }
                .prose code { background-color: #1e293b; padding: 0.2rem 0.4rem; border-radius: 0.25rem; font-family: monospace; }
                .prose blockquote { border-left: 4px solid #38bdf8; padding-left: 1rem; font-style: italic; color: #94a3b8; margin: 1.5rem 0; }
                .timestamp-link { color: #38bdf8; font-family: monospace; cursor: pointer; font-weight: bold; }
                .timestamp-link:hover { text-decoration: underline; color: #7dd3fc; }
            </style>
            <script>
                document.addEventListener('click', function(e) {
                    const target = e.target.closest('.timestamp-link');
                    if (target) {
                        const ts = target.dataset.timestamp;
                        const parts = ts.split(':').reverse();
                        let seconds = 0;
                        if (parts[0]) seconds += parseInt(parts[0]);
                        if (parts[1]) seconds += parseInt(parts[1]) * 60;
                        if (parts[2]) seconds += parseInt(parts[2]) * 3600;

                        const player = document.getElementById('yt-player');
                        if (player) {
                            const baseUrl = player.src.split('?')[0];
                            player.src = baseUrl + '?enablejsapi=1&autoplay=1&start=' + seconds;
                        }
                    }
                });
            </script>
        """)

        with ui.header().classes("bg-slate-900 border-b border-slate-800 items-center justify-between"):
            with ui.row().classes("items-center gap-4"):
                ui.icon("smart_display", size="32px").classes("text-blue-500")
                ui.label("yt-study Pro").classes("text-2xl font-black tracking-tight")

            with ui.row().classes("items-center gap-2"):
                ui.button(icon="refresh", on_click=lambda: ui.run_javascript("window.location.reload()")).props("flat color=slate-400")
                ui.button("GitHub", on_click=lambda: ui.open("https://github.com/jayss/yt-study")).props("flat color=slate-400")

        with ui.splitter(value=20, limits=(15, 40)).classes("w-full h-[calc(100vh-64px)]") as main_splitter:
            # Left Pane: Navigation
            with main_splitter.before:
                with ui.column().classes("w-full h-full bg-slate-900/50 p-4 overflow-y-auto border-r border-slate-800"):
                    ui.label("EXPLORER").classes("text-xs font-bold text-slate-500 uppercase tracking-widest mb-4")
                    self.tree = ui.tree(self.tree_data, label_key="label", on_select=self.handle_tree_select).classes("w-full text-slate-300")
                    self.tree.props('no-connectors dark color="blue-5"')

            # Right Pane: Content & Video
            with main_splitter.after:
                with ui.splitter(value=60, limits=(30, 80)).classes("w-full h-full") as content_splitter:
                    # Content Area (Left side of right pane)
                    with content_splitter.before:
                        with ui.column().classes("w-full h-full p-8 overflow-y-auto bg-slate-950"):
                            with ui.row().classes("w-full items-center justify-between mb-6"):
                                self.title_label = ui.label("Select a video to begin").classes("text-3xl font-bold text-slate-100")
                                self.edit_btn = ui.button("Edit", icon="edit", on_click=self.toggle_edit).props("flat color=blue-400").classes("hidden")

                            self.markdown_view = ui.markdown().classes("prose max-w-none w-full")

                            with ui.column().classes("w-full gap-4 hidden") as self.editor_container:
                                self.editor = ui.textarea(label="Markdown Content").classes("w-full h-[60vh] font-mono").props('outlined dark autogrow color="blue-5"')
                                with ui.row().classes("gap-2"):
                                    self.save_btn = ui.button("Save", icon="save", on_click=self.save_content).props("color=blue-600")
                                    ui.button("Cancel", icon="close", on_click=lambda: self.load_content(self.current_path, self.current_video_id)).props("flat color=slate-400")

                    # Video Area (Right side of right pane)
                    with content_splitter.after:
                        with ui.column().classes("w-full h-full bg-slate-900 p-6 border-l border-slate-800 overflow-y-auto"):
                            with ui.column().classes("w-full sticky top-0 gap-6"):
                                ui.label("VIDEO PLAYER").classes("text-xs font-bold text-slate-500 uppercase tracking-widest")
                                with ui.card().classes("w-full aspect-video bg-black p-0 overflow-hidden shadow-2xl rounded-xl border border-slate-700"):
                                    self.video_player = ui.html(
                                        '<div class="flex items-center justify-center w-full h-full text-slate-600 italic">No video selected</div>'
                                    ).classes("w-full h-full")

                                with ui.column().classes("gap-2"):
                                    ui.label("QUICK ACTIONS").classes("text-xs font-bold text-slate-500 uppercase tracking-widest")
                                    with ui.row().classes("gap-2"):
                                        ui.button("Open in YouTube", icon="open_in_new",
                                                  on_click=lambda: ui.open(f"https://youtube.com/watch?v={self.current_video_id}") if self.current_video_id else None
                                                 ).props("flat size=sm color=slate-400")


def start_web_ui(
    port: int = 8000, host: str = "0.0.0.0", output_dir: Optional[Path] = None
) -> None:
    if output_dir is None:
        output_dir = config.default_output_dir

    @ui.page("/")
    def init_ui() -> None:
        visualizer = WebVisualizer(output_dir)
        visualizer.render()

    ui.run(title="yt-study Pro", port=port, host=host, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    start_web_ui()
