"""Parse LinkedIn and Facebook data export archives for About Me."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from typing import Optional


def _find_in_zip(z: zipfile.ZipFile, *names: str) -> Optional[tuple[str, bytes]]:
    """Find first file matching any of the names (case-insensitive) in zip. Returns (path, content)."""
    names_lower = [n.lower() for n in names]
    for info in z.infolist():
        if info.is_dir():
            continue
        base = info.filename.replace("\\", "/").split("/")[-1].lower()
        for n in names_lower:
            if base == n:
                try:
                    return info.filename, z.read(info.filename)
                except Exception:
                    pass
    return None


def _find_csv_in_zip(z: zipfile.ZipFile, *substrings: str) -> Optional[tuple[str, bytes]]:
    """Find CSV file whose name contains any of the substrings (case-insensitive)."""
    subs = [s.lower() for s in substrings]
    for info in z.infolist():
        if info.is_dir():
            continue
        base = info.filename.replace("\\", "/").split("/")[-1].lower()
        if not base.endswith(".csv"):
            continue
        for sub in subs:
            if sub in base:
                try:
                    return info.filename, z.read(info.filename)
                except Exception:
                    pass
    return None


def _csv_to_text(content: bytes) -> str:
    """Parse CSV and return as readable text lines."""
    try:
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return ""
        lines = []
        for row in rows:
            parts = [f"{k}: {v}" for k, v in row.items() if v and str(v).strip()]
            if parts:
                lines.append(" | ".join(parts))
        return "\n".join(lines) if lines else ""
    except Exception:
        return ""


def parse_linkedin_archive(zip_bytes: bytes) -> str:
    """
    Parse LinkedIn data export ZIP. Returns formatted text suitable for About Me.
    LinkedIn sends: Profile (Basic_Profile.csv), Positions.csv, Education.csv, etc.
    """
    sections = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
            # Profile / Basic info
            found = _find_in_zip(z, "Basic_Profile.csv", "Profile.csv", "basic_profile.csv")
            if not found:
                found = _find_csv_in_zip(z, "profile", "basic")
            if found:
                path, content = found
                text = _csv_to_text(content)
                if text:
                    sections.append("**Profile:**\n" + text)

            # Work history
            found = _find_in_zip(z, "Positions.csv", "positions.csv", "Position.csv")
            if not found:
                found = _find_csv_in_zip(z, "position", "experience", "work")
            if found:
                path, content = found
                text = _csv_to_text(content)
                if text:
                    sections.append("**Work experience:**\n" + text)

            # Education
            found = _find_in_zip(z, "Education.csv", "education.csv")
            if not found:
                found = _find_csv_in_zip(z, "education")
            if found:
                path, content = found
                text = _csv_to_text(content)
                if text:
                    sections.append("**Education:**\n" + text)

            # Skills
            found = _find_in_zip(z, "Skills.csv", "skills.csv")
            if not found:
                found = _find_csv_in_zip(z, "skill")
            if found:
                path, content = found
                text = _csv_to_text(content)
                if text:
                    sections.append("**Skills:**\n" + text)

            # Certifications
            found = _find_in_zip(z, "Certifications.csv", "certifications.csv")
            if not found:
                found = _find_csv_in_zip(z, "certification")
            if found:
                path, content = found
                text = _csv_to_text(content)
                if text:
                    sections.append("**Certifications:**\n" + text)
    except zipfile.BadZipFile:
        return ""
    except Exception:
        return ""

    if not sections:
        return ""
    return "\n\n".join(sections)


def _extract_from_fb_profile(data: dict, prefix: str = "") -> list[str]:
    """Recursively extract meaningful strings from Facebook profile JSON."""
    lines = []
    if isinstance(data, dict):
        for k, v in data.items():
            if v is None or v == "":
                continue
            if isinstance(v, (dict, list)):
                lines.extend(_extract_from_fb_profile(v, f"{prefix}{k}: "))
            else:
                s = str(v).strip()
                if s and len(s) < 500:  # Skip huge blobs
                    lines.append(f"{prefix}{k}: {s}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                lines.extend(_extract_from_fb_profile(item, prefix))
            elif item:
                s = str(item).strip()
                if s and len(s) < 500:
                    lines.append(f"{prefix}{s}")
    return lines


def _find_json_in_zip(z: zipfile.ZipFile, *substrings: str) -> Optional[tuple[str, bytes]]:
    """Find JSON file whose path contains any of the substrings (case-insensitive)."""
    subs = [s.lower() for s in substrings]
    for info in z.infolist():
        if info.is_dir():
            continue
        path_lower = info.filename.replace("\\", "/").lower()
        if not path_lower.endswith(".json"):
            continue
        for sub in subs:
            if sub in path_lower:
                try:
                    return info.filename, z.read(info.filename)
                except Exception:
                    pass
    return None


def parse_facebook_archive(zip_bytes: bytes) -> str:
    """
    Parse Facebook data export ZIP. Returns formatted text suitable for About Me.
    Facebook sends: profile_information/profile_information.json or about_you.html
    """
    sections = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
            # Prefer JSON (structured)
            found = _find_in_zip(z, "profile_information.json", "about_you.json")
            if not found:
                found = _find_json_in_zip(z, "profile", "about")
            if found:
                path, content = found
                try:
                    data = json.loads(content.decode("utf-8", errors="replace"))
                    lines = _extract_from_fb_profile(data)
                    # Filter to useful profile fields (work, education, about, etc.)
                    useful = []
                    skip_keys = ("timestamp", "uri", "href", "media_metadata")
                    for line in lines:
                        if any(sk in line.lower() for sk in skip_keys):
                            continue
                        useful.append(line)
                    if useful:
                        sections.append("\n".join(useful[:80]))  # Cap size
                except json.JSONDecodeError:
                    pass

            # Fallback: about_you.html - strip HTML
            if not sections:
                found = _find_in_zip(z, "about_you.html", "profile_information.html")
                if found:
                    path, content = found
                    try:
                        html = content.decode("utf-8", errors="replace")
                        # Remove script/style, get text
                        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
                        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
                        text = re.sub(r"<[^>]+>", " ", text)
                        text = re.sub(r"\s+", " ", text).strip()
                        if len(text) > 50:
                            sections.append(text[:2000])
                    except Exception:
                        pass
    except zipfile.BadZipFile:
        return ""
    except Exception:
        return ""

    if not sections:
        return ""
    return "\n\n".join(sections)
