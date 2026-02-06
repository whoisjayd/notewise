#!/usr/bin/env python3
"""Build standalone executable using PyInstaller with compression."""

import os
import platform
import shutil
import subprocess
import sys
import zipfile
import tarfile
from pathlib import Path


def create_zip_archive(source_file: Path, output_file: Path):
    """Create a ZIP archive."""
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(source_file, source_file.name)
    print(f"[OK] Created archive: {output_file}")


def create_tar_gz_archive(source_file: Path, output_file: Path):
    """Create a tar.gz archive."""
    with tarfile.open(output_file, 'w:gz') as tf:
        tf.add(source_file, arcname=source_file.name)
    print(f"[OK] Created archive: {output_file}")


def main():
    """Build executable for current platform."""
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Clean previous builds
    for path in ["build", "dist", "launcher.py", "*.spec"]:
        path_obj = Path(path)
        if path_obj.exists():
            if path_obj.is_dir():
                shutil.rmtree(path_obj)
            else:
                path_obj.unlink()

    # Create launcher script
    launcher_content = """from yt_study.cli import app
import sys
sys.exit(app())
"""
    Path("launcher.py").write_text(launcher_content)

    # Determine output name and archive format
    system = platform.system().lower()
    if system == "windows":
        exe_name = "yt-study"
        output_name = "yt-study-windows"
        archive_ext = ".zip"
        use_zip = True
    elif system == "darwin":
        exe_name = "yt-study"
        output_name = "yt-study-macos"
        archive_ext = ".tar.gz"
        use_zip = False
    else:
        exe_name = "yt-study"
        output_name = "yt-study-linux"
        archive_ext = ".tar.gz"
        use_zip = False

    # Build with PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        exe_name,
        "--collect-all",
        "litellm",
        "--collect-all",
        "pydantic",
        "--paths",
        "src",
        "launcher.py",
    ]

    print(f"Building executable: {exe_name}")
    print(f"Command: {' '.join(cmd)}")

    subprocess.run(cmd, check=True)

    # Prepare release directory
    release_dir = Path("dist/release")
    release_dir.mkdir(parents=True, exist_ok=True)

    # Find the built executable
    if system == "windows":
        exe_file = Path("dist") / f"{exe_name}.exe"
        final_exe = release_dir / f"{output_name}.exe"
    else:
        exe_file = Path("dist") / exe_name
        final_exe = release_dir / output_name

    if not exe_file.exists():
        print(f"[ERROR] Executable not found: {exe_file}")
        sys.exit(1)

    # Move executable to release directory
    shutil.move(str(exe_file), str(final_exe))
    print(f"[OK] Executable built: {final_exe}")

    # Create compressed archive
    archive_name = release_dir / f"{output_name}{archive_ext}"
    if use_zip:
        create_zip_archive(final_exe, archive_name)
    else:
        create_tar_gz_archive(final_exe, archive_name)

    # Clean up launcher
    Path("launcher.py").unlink(missing_ok=True)

    print(f"\n[OK] Build complete!")
    print(f"  Executable: {final_exe}")
    print(f"  Archive: {archive_name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
