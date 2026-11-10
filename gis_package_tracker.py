"""GIS Python package tracker: scrape PyPI's package index with BeautifulSoup.

For each package in the Python GIS stack, reads its PyPI "simple" index page (plain HTML,
one link per uploaded file) and reports how many releases it has, its latest stable version,
the Python versions that release requires, and which operating systems get prebuilt wheels.
"""

import argparse
import csv
import time
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from packaging.utils import parse_sdist_filename, parse_wheel_filename
from packaging.version import InvalidVersion, Version

INDEX_URL = "https://pypi.org/simple/{name}/"
PACKAGES = ["geopandas", "shapely", "pyproj", "fiona", "pyogrio", "rasterio", "gdal", "folium", "osmnx", "bokeh"]
HEADERS = {"User-Agent": "gis-package-tracker (portfolio project; github.com/josephachang02/SoupScrape)"}
DELAY_SECONDS = 1.0  # pause between requests to be polite to PyPI


@dataclass
class DistFile:
    package: str
    filename: str
    version: str
    kind: str              # "wheel" or "sdist"
    requires_python: str   # from the data-requires-python attribute, "" if absent
    platforms: str         # "windows;macos;linux", "any" for pure-Python wheels, "" for sdists
    yanked: bool


def fetch_index(name: str, session: requests.Session) -> str:
    resp = session.get(INDEX_URL.format(name=name), headers=HEADERS, timeout=30)
    resp.raise_for_status()  # surface 404s (typo in a package name) instead of parsing an error page
    return resp.text


def platforms_from_tags(tags) -> set[str]:
    found = set()
    for tag in tags:
        plat = tag.platform
        if plat == "any":
            found.add("any")
        elif plat.startswith("win"):
            found.add("windows")
        elif plat.startswith("macosx"):
            found.add("macos")
        elif "linux" in plat:  # covers manylinux, musllinux, and plain linux tags
            found.add("linux")
    return found


def parse_index(name: str, html: str) -> list[DistFile]:
    soup = BeautifulSoup(html, "html.parser")
    files = []
    for a in soup.find_all("a"):  # every <a> on a simple-index page is one uploaded file
        filename = a.get_text(strip=True)
        try:
            if filename.endswith(".whl"):
                _, version, _, tags = parse_wheel_filename(filename)
                kind, plats = "wheel", platforms_from_tags(tags)
            elif filename.endswith((".tar.gz", ".zip")):
                _, version = parse_sdist_filename(filename)
                kind, plats = "sdist", set()
            else:
                continue  # skip legacy formats like .exe or .egg
        except (InvalidVersion, ValueError):
            continue  # very old uploads sometimes use non-standard names; ignore them
        files.append(DistFile(
            package=name,
            filename=filename,
            version=str(version),
            kind=kind,
            requires_python=a.get("data-requires-python", ""),  # BeautifulSoup un-escapes &gt; to >
            platforms=";".join(sorted(plats)),
            yanked=a.has_attr("data-yanked"),
        ))
    return files


def summarize(name: str, files: list[DistFile]) -> dict:
    live = [f for f in files if not f.yanked]
    versions = {Version(f.version) for f in live}
    stable = sorted(v for v in versions if not v.is_prerelease and not v.is_devrelease)
    latest = stable[-1] if stable else max(versions)
    latest_files = [f for f in live if Version(f.version) == latest]
    plats = Counter(p for f in latest_files for p in f.platforms.split(";") if p)
    req = next((f.requires_python for f in latest_files if f.requires_python), "")
    return {
        "package": name,
        "stable_releases": len(stable),
        "first_release": str(stable[0]) if stable else "",
        "latest_version": str(latest),
        "requires_python": req,
        "files_in_latest": len(latest_files),
        "wheels_in_latest": sum(f.kind == "wheel" for f in latest_files),
        "wheel_platforms": "pure Python" if plats.keys() == {"any"} else ", ".join(sorted(plats.keys() - {"any"})) or "sdist only",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_summary(summary: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt  # imported here so the scraper itself runs without matplotlib

    rows = sorted(summary, key=lambda r: r["stable_releases"])
    fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    bars = ax.barh([r["package"] for r in rows], [r["stable_releases"] for r in rows], color="#3b6ea5")
    for bar, r in zip(bars, rows):  # label each bar with the latest version and its Python requirement
        label = f"  v{r['latest_version']}   {r['requires_python'] or 'no Python pin'}   {r['wheel_platforms']}"
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, label, va="center", fontsize=9, color="#333")
    ax.set_xlabel("Stable releases on PyPI")
    ax.set_xlim(0, max(r["stable_releases"] for r in rows) * 1.9)  # room for the bar labels
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("The Python GIS stack on PyPI: releases, latest version, Python requirement, wheel platforms",
                 loc="left", fontsize=11)
    fig.text(0.01, 0.005, f"Scraped from pypi.org/simple on {time.strftime('%Y-%m-%d')} with BeautifulSoup.",
             fontsize=8, color="#666")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main(packages: list[str], out_dir: Path, chart: bool) -> list[dict]:
    session = requests.Session()
    all_files, summary = [], []
    for i, name in enumerate(packages):
        if i:
            time.sleep(DELAY_SECONDS)
        files = parse_index(name, fetch_index(name, session))
        all_files += files
        summary.append(summarize(name, files))
        print(f"{name:<10} {summary[-1]['stable_releases']:>4} releases   latest {summary[-1]['latest_version']:<10} "
              f"{summary[-1]['requires_python']:<8} {summary[-1]['wheel_platforms']}")

    write_csv(out_dir / "files.csv", [asdict(f) for f in all_files])
    write_csv(out_dir / "summary.csv", summary)
    if chart:
        plot_summary(summary, out_dir / "summary.png")
    print(f"\nSaved {len(all_files):,} file records and a {len(summary)}-package summary to {out_dir}/")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="*", default=PACKAGES, help="PyPI package names (default: GIS stack)")
    parser.add_argument("--out", type=Path, default=Path("outputs"), help="output folder for CSVs and chart")
    parser.add_argument("--no-chart", action="store_true", help="skip the matplotlib chart")
    args = parser.parse_args()
    main(args.packages, args.out, chart=not args.no_chart)
