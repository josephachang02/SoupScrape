"""Offline tests for the HTML parser, using a small hand-written simple-index page."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # import the script from the repo root

from gis_package_tracker import parse_index, summarize

SAMPLE = """<!DOCTYPE html><html><body><h1>Links for demo</h1>
<a href="https://files.example/demo-1.0.0.tar.gz#sha256=aa" data-requires-python="&gt;=3.9">demo-1.0.0.tar.gz</a><br />
<a href="https://files.example/demo-1.0.0-py3-none-any.whl#sha256=bb" data-requires-python="&gt;=3.9">demo-1.0.0-py3-none-any.whl</a><br />
<a href="https://files.example/demo-1.1.0.tar.gz#sha256=cc" data-requires-python="&gt;=3.10">demo-1.1.0.tar.gz</a><br />
<a href="https://files.example/demo-1.1.0-cp312-cp312-win_amd64.whl#sha256=dd" data-requires-python="&gt;=3.10">demo-1.1.0-cp312-cp312-win_amd64.whl</a><br />
<a href="https://files.example/demo-1.1.0-cp312-cp312-macosx_11_0_arm64.whl#sha256=ee" data-requires-python="&gt;=3.10">demo-1.1.0-cp312-cp312-macosx_11_0_arm64.whl</a><br />
<a href="https://files.example/demo-1.1.0-cp312-cp312-manylinux_2_28_x86_64.whl#sha256=ff" data-requires-python="&gt;=3.10">demo-1.1.0-cp312-cp312-manylinux_2_28_x86_64.whl</a><br />
<a href="https://files.example/demo-1.2.0.tar.gz#sha256=gg" data-yanked="broken build">demo-1.2.0.tar.gz</a><br />
<a href="https://files.example/demo-2.0.0rc1.tar.gz#sha256=hh">demo-2.0.0rc1.tar.gz</a><br />
<a href="https://files.example/demo-0.1.win32.exe#sha256=ii">demo-0.1.win32.exe</a><br />
</body></html>"""


def test_parses_files_and_attributes():
    files = parse_index("demo", SAMPLE)
    assert len(files) == 8  # the legacy .exe installer is skipped
    first = files[0]
    assert (first.version, first.kind, first.requires_python) == ("1.0.0", "sdist", ">=3.9")  # &gt; un-escaped
    assert files[1].platforms == "any"
    assert files[6].yanked is True


def test_summary_ignores_yanked_and_prereleases():
    s = summarize("demo", parse_index("demo", SAMPLE))
    assert s["stable_releases"] == 2          # 1.0.0 and 1.1.0; 1.2.0 is yanked, 2.0.0rc1 is a pre-release
    assert s["latest_version"] == "1.1.0"
    assert s["requires_python"] == ">=3.10"
    assert s["wheels_in_latest"] == 3
    assert s["wheel_platforms"] == "linux, macos, windows"
