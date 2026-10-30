"""Pick the newest APK of a package for one ABI from an F-Droid index-v2 document."""
from __future__ import annotations

FDROID_REPO = "https://f-droid.org/repo"
INDEX_URL = f"{FDROID_REPO}/index-v2.json"


def newest_apk(index: dict, package: str, abi: str) -> tuple[str, int, str]:
    """(download URL, versionCode, versionName) of the highest versionCode built for `abi`."""
    versions = index.get("packages", {}).get(package, {}).get("versions")
    if not versions:
        raise LookupError(f"{package} is not in the F-Droid index")
    best: tuple[int, str, str] | None = None
    for version in versions.values():
        manifest = version.get("manifest", {})
        if abi not in manifest.get("nativecode", []):
            continue
        code = int(manifest["versionCode"])
        if best is None or code > best[0]:
            best = (code, version["file"]["name"], manifest.get("versionName", ""))
    if best is None:
        raise LookupError(f"{package} has no {abi} build in the F-Droid index")
    code, name, version_name = best
    return f"{FDROID_REPO}/{name.lstrip('/')}", code, version_name
