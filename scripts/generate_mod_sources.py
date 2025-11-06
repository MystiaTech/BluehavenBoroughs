#!/usr/bin/env python3
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from difflib import SequenceMatcher
from urllib.error import HTTPError

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
MODLIST_PATH = REPO_ROOT / "docs" / "SOURCE_MODLIST.md"
OUTPUT_PATH = Path(__file__).resolve().parent / "mod_sources.json"
PACK_TOML_PATH = REPO_ROOT / "pack.toml"

MODRINTH_SEARCH = "https://api.modrinth.com/v2/search"
MODRINTH_VERSIONS = "https://api.modrinth.com/v2/project/{slug}/version"

CURSEFORGE_WIDGET = "https://api.cfwidget.com/minecraft/mc-mods/{slug}"

NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
DEFAULT_HEADERS = {"User-Agent": "BluehavenSlugFetcher/1.0"}


def normalize(text: str) -> str:
    return NORMALIZE_RE.sub("", text.lower())


def fetch_json(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request_headers = DEFAULT_HEADERS if headers is None else {**DEFAULT_HEADERS, **headers}
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        data = json.loads(resp.read().decode(charset))
    # Be courteous to public APIs by pacing our requests.
    time.sleep(0.1)
    return data

def parse_modlist() -> list[tuple[str, str]]:
    mods: list[tuple[str, str]] = []
    for line in MODLIST_PATH.read_text().splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        entry = line[2:]
        if "[" in entry and "]" in entry:
            name, version = entry.split("[", 1)
            version = version.split("]", 1)[0]
        else:
            name, version = entry, ""
        name = name.strip()
        mods.append((name, version.replace("\\", "")))
    return mods

def find_modrinth_project(name: str) -> dict | None:
    try:
        data = fetch_json(
            MODRINTH_SEARCH,
            {
                "query": name,
                "limit": 5,
                "facets": json.dumps([["project_type:mod"]]),
            },
        )
    except Exception:
        return None
    target = normalize(name)
    best: tuple[float, dict] | None = None
    for hit in data.get("hits", []):
        score = SequenceMatcher(None, target, normalize(hit.get("title", ""))).ratio()
        if best is None or score > best[0]:
            best = (score, hit)
    if not best:
        return None
    score, hit = best
    candidate_slug_norm = normalize(hit.get("slug", ""))
    # Require a strong similarity score or an exact slug-normalized match to
    # avoid mismatching unrelated projects that share a keyword.
    if score < 0.7 and candidate_slug_norm != target:
        return None
    return {"slug": hit["slug"], "title": hit["title"], "score": score}


def guess_curseforge_slugs(name: str) -> list[str]:
    ascii_text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", ascii_text)
    ascii_text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", ascii_text)
    ascii_text = ascii_text.replace("'s ", "s ")
    ascii_text = ascii_text.replace("'", "")
    ascii_text = ascii_text.replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    candidates = [slug]
    compact = slug.replace("-", "")
    if compact != slug:
        candidates.append(compact)
    if slug.endswith("-mod"):
        candidates.append(slug[:-4])
    return [candidate for candidate in dict.fromkeys(candidate for candidate in candidates if candidate)]


def find_curseforge_project(name: str) -> tuple[dict | None, dict | None]:
    for slug in guess_curseforge_slugs(name):
        try:
            data = fetch_json(CURSEFORGE_WIDGET.format(slug=slug), headers=CURSEFORGE_HEADERS)
        except HTTPError as error:
            if error.code == 404:
                continue
            return None, None
        except Exception:
            return None, None
        project = {
            "id": data.get("id"),
            "slug": slug,
            "title": data.get("title"),
        }
        return project, data
    return None, None

def get_pack_environment() -> tuple[str | None, str | None]:
    if not PACK_TOML_PATH.exists():
        return None, None
    data = tomllib.loads(PACK_TOML_PATH.read_text())
    versions = data.get("versions", {}) if isinstance(data, dict) else {}
    minecraft = versions.get("minecraft")
    loader: str | None = None
    for candidate in ("forge", "neoforge", "fabric", "quilt"):
        if candidate in versions:
            loader = candidate
            break
    return minecraft, loader


TARGET_MINECRAFT, TARGET_LOADER = get_pack_environment()


def environment_matches(release: dict) -> bool:
    if TARGET_MINECRAFT:
        game_versions = release.get("game_versions") or []
        if TARGET_MINECRAFT not in game_versions:
            return False
    if TARGET_LOADER:
        loaders = [loader.lower() for loader in (release.get("loaders") or [])]
        if TARGET_LOADER not in loaders:
            return False
    return True


CURSEFORGE_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BluehavenSlugFetcher/1.0)"}


CURSEFORGE_LOADER_MAP = {
    "forge": "Forge",
    "fabric": "Fabric",
    "quilt": "Quilt",
    "neoforge": "NeoForge",
}


def curseforge_environment_matches(file_entry: dict) -> bool:
    versions = file_entry.get("gameVersions") or file_entry.get("versions") or []
    if TARGET_MINECRAFT and TARGET_MINECRAFT not in versions:
        return False
    if TARGET_LOADER:
        loader_label = CURSEFORGE_LOADER_MAP.get(TARGET_LOADER)
        if loader_label and loader_label not in versions:
            return False
    return True


def find_modrinth_version(slug: str, version: str) -> dict | None:
    if not version:
        return None
    try:
        versions = fetch_json(MODRINTH_VERSIONS.format(slug=slug), {"index": "published", "limit": 100})
    except Exception:
        return None
    cleaned = re.sub(r"\s+", "", version).lower()
    exact_match: dict | None = None
    case_insensitive_match: dict | None = None
    substring_match: dict | None = None
    for release in versions:
        if not environment_matches(release):
            continue
        number = release.get("version_number", "")
        number_cleaned = re.sub(r"\s+", "", number).lower()
        if number_cleaned == cleaned:
            exact_match = release
            break
        if version.lower() == number.lower():
            case_insensitive_match = case_insensitive_match or release
        elif cleaned and cleaned in number_cleaned:
            substring_match = substring_match or release
    for candidate in (exact_match, case_insensitive_match, substring_match):
        if candidate:
            return {"id": candidate["id"], "number": candidate.get("version_number", "")}
    return None


def match_version(candidate: str, version: str) -> str | None:
    candidate_stripped = re.sub(r"\s+", "", candidate).lower()
    version_cleaned = re.sub(r"\s+", "", version).lower()
    if not version_cleaned:
        return None
    if candidate_stripped == version_cleaned:
        return "exact"
    if candidate.lower() == version.lower():
        return "case"
    if version_cleaned and version_cleaned in candidate_stripped:
        return "substring"
    return None


def find_curseforge_version(project_data: dict | None, version: str) -> dict | None:
    if not project_data or not version:
        return None
    files = project_data.get("files") or []
    best_case: dict | None = None
    best_partial: dict | None = None
    for file_entry in files:
        if not curseforge_environment_matches(file_entry):
            continue
        for field in (
            file_entry.get("display") or "",
            file_entry.get("name") or "",
            file_entry.get("version") or "",
        ):
            match_kind = match_version(field, version)
            if match_kind == "exact":
                return {
                    "id": file_entry.get("id"),
                    "displayName": file_entry.get("display"),
                    "fileName": file_entry.get("name"),
                }
            if match_kind == "case" and best_case is None:
                best_case = file_entry
            elif match_kind == "substring" and best_partial is None:
                best_partial = file_entry
    for candidate in (best_case, best_partial):
        if candidate:
            return {
                "id": candidate.get("id"),
                "displayName": candidate.get("display"),
                "fileName": candidate.get("name"),
            }
    return None

def main() -> None:
    mods = parse_modlist()
    results: list[dict] = []
    total = len(mods)
    for index, (name, version) in enumerate(mods, 1):
        mr_project = find_modrinth_project(name)
        mr_version = find_modrinth_version(mr_project["slug"], version) if mr_project else None
        cf_project = None
        cf_version = None
        cf_data = None
        if not mr_project or not mr_version:
            cf_project, cf_data = find_curseforge_project(name)
            if cf_project:
                cf_version = find_curseforge_version(cf_data, version)
        print(
            f"[{index}/{total}] {name} -> "
            f"modrinth slug={mr_project['slug'] if mr_project else '∅'}"
            f" version={'∅' if not mr_version else mr_version.get('number')} | "
            f"curseforge slug={cf_project['slug'] if cf_project else '∅'}"
            f" file={'∅' if not cf_version else cf_version.get('id')}",
            flush=True,
        )
        results.append(
            {
                "name": name,
                "version": version,
                "modrinth": mr_project,
                "modrinth_version": mr_version,
                "curseforge": cf_project,
                "curseforge_file": cf_version,
            }
        )
        # Respect Modrinth rate limits (300 requests/minute) with a short pause.
        time.sleep(0.15)
    OUTPUT_PATH.write_text(json.dumps({"mods": results}, indent=2, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
