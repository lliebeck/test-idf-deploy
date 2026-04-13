from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


CHIP_FAMILY_MAP = {
    "esp32": "ESP32",
    "esp32c2": "ESP32-C2",
    "esp32c3": "ESP32-C3",
    "esp32c5": "ESP32-C5",
    "esp32c6": "ESP32-C6",
    "esp32c61": "ESP32-C61",
    "esp32h2": "ESP32-H2",
    "esp32h21": "ESP32-H21",
    "esp32h4": "ESP32-H4",
    "esp32p4": "ESP32-P4",
    "esp32s2": "ESP32-S2",
    "esp32s3": "ESP32-S3",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a GitHub Pages site for ESP Web Tools from an ESP-IDF build."
    )
    parser.add_argument("--build-dir", default="build", help="Path to the ESP-IDF build directory")
    parser.add_argument("--output-dir", default="site", help="Output directory for the static site")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def chip_family_for(target: str) -> str:
    normalized = target.strip().lower()
    return CHIP_FAMILY_MAP.get(normalized, normalized.upper())


def build_version(project_description: dict) -> str:
    project_version = str(project_description.get("project_version") or "dev")
    ref_name = os.environ.get("GITHUB_REF_NAME")
    run_number = os.environ.get("GITHUB_RUN_NUMBER")
    if ref_name and run_number:
        return f"{project_version}-{ref_name}.{run_number}"
    return project_version


def build_release_info(project_description: dict, chip_family: str, parts: list[dict]) -> dict:
    sha = os.environ.get("GITHUB_SHA", "")
    short_sha = sha[:7] if sha else "local"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    source_url = f"{server_url}/{repository}/commit/{sha}" if repository and sha else ""

    return {
        "project_name": project_description["project_name"],
        "version": build_version(project_description),
        "chip_family": chip_family,
        "target": project_description["target"],
        "build_time": timestamp,
        "commit": short_sha,
        "source_url": source_url,
        "parts": parts,
    }


def copy_firmware_parts(build_dir: Path, firmware_dir: Path, flash_files: dict[str, str]) -> list[dict]:
    parts: list[dict] = []
    for offset, relative_source in sorted(flash_files.items(), key=lambda item: int(item[0], 16)):
        source = build_dir / relative_source
        if not source.exists():
            raise FileNotFoundError(f"Expected firmware part missing: {source}")

        destination_name = Path(relative_source).name
        destination = firmware_dir / destination_name
        shutil.copy2(source, destination)
        parts.append(
            {
                "path": destination_name,
                "offset": int(offset, 16),
            }
        )
    return parts


def render_index(template_path: Path, output_path: Path, release_info: dict) -> None:
    download_links = [
        '<li><a href="./firmware/manifest.json">Manifest herunterladen</a></li>',
        '<li><a href="./firmware/release.json">Build-Metadaten herunterladen</a></li>',
    ]
    for part in release_info["parts"]:
        file_name = part["path"]
        label = Path(file_name).stem.replace("-", " ")
        download_links.append(f'<li><a href="./firmware/{file_name}">{label}</a></li>')

    source_link = (
        f'<a href="{release_info["source_url"]}">Commit auf GitHub ansehen</a>'
        if release_info["source_url"]
        else "Lokaler Build ohne GitHub-Commit-Link"
    )

    replacements = {
        "__PROJECT_NAME__": release_info["project_name"],
        "__CHIP_FAMILY__": release_info["chip_family"],
        "__TARGET__": release_info["target"],
        "__VERSION__": release_info["version"],
        "__BUILD_TIME__": release_info["build_time"],
        "__COMMIT__": release_info["commit"],
        "__MANIFEST_PATH__": "firmware/manifest.json",
        "__DOWNLOAD_LINKS__": "\n            ".join(download_links),
        "__SOURCE_LINK__": source_link,
    }

    content = template_path.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    output_path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    build_dir = (root_dir / args.build_dir).resolve()
    output_dir = (root_dir / args.output_dir).resolve()
    firmware_dir = output_dir / "firmware"
    template_dir = root_dir / "web"

    flasher_args = load_json(build_dir / "flasher_args.json")
    project_description = load_json(build_dir / "project_description.json")
    chip_family = chip_family_for(project_description["target"])

    ensure_clean_dir(output_dir)
    firmware_dir.mkdir(parents=True, exist_ok=True)

    parts = copy_firmware_parts(build_dir, firmware_dir, flasher_args["flash_files"])
    manifest = {
        "name": project_description["project_name"],
        "version": build_version(project_description),
        "builds": [
            {
                "chipFamily": chip_family,
                "parts": parts,
            }
        ],
    }

    release_info = build_release_info(project_description, chip_family, parts)

    shutil.copy2(template_dir / "styles.css", output_dir / "styles.css")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    render_index(template_dir / "index.html", output_dir / "index.html", release_info)
    (firmware_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (firmware_dir / "release.json").write_text(json.dumps(release_info, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
