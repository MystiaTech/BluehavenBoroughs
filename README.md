# Bluehaven Borough (packwiz)

**Public, ARR-safe distribution using packwiz + GitHub Pages.**

## What this repo contains
- `pack.toml` and `index.toml` (packwiz manifest — **no mod JARs**).
- `overrides/` for configs, resourcepacks, shaderpacks, defaultconfigs, scripts.
- Helper scripts to add mods from CurseForge/Modrinth without rehosting.

## Quick start (developer)
1) Install **packwiz**: https://packwiz.infra.link/
2) Ensure your repo is public. Enable **GitHub Pages** to serve this repo (Settings → Pages).
3) Edit `pack.toml` author/version if desired.
4) Add mods via CurseForge/Modrinth providers (examples below).
5) Commit & push. Your Pages URL will host `pack.toml`, e.g.:  
   `https://<YOUR_USER>.github.io/<YOUR_REPO>/pack.toml`

## Adding mods
Use one of the following (fill the IDs/slugs):
- CurseForge by **project ID**:  
  `packwiz curseforge add <projectId>`
- Modrinth by **slug or project ID**:  
  `packwiz modrinth add <slug-or-id>`

Then lock hashes (optional) and commit updates:
```
packwiz refresh
```

> Tip: Use `packwiz cf export` / `packwiz mr export` at your discretion, but for ARR safety prefer **installer bootstrap** + Pages URL.

## Prism Launcher (players)
- Create a new instance (your preferred loader & MC version).
- Download **packwiz-installer-bootstrap.jar** from the official releases:  
  https://github.com/packwiz/packwiz-installer-bootstrap/releases
- Place it into the instance’s `.minecraft/` folder.
- In Prism: **Edit Instance → Settings → Custom Commands → Pre-Launch command**:
```
"$INST_JAVA" -jar packwiz-installer-bootstrap.jar https://<YOUR_USER>.github.io/<YOUR_REPO>/pack.toml
```
- Launch. Mods will auto-download from CurseForge/Modrinth (ARR-compliant).

## Notes
- Do **not** commit mod JARs. Only manifests and `overrides/`.
- If you add configs/resourcepacks/shaders, put them under `overrides/`.
- To update mods, run the `packwiz ... add/update` commands, commit, push. Clients update next launch.

---

### Helper: candidate add commands
These lines are **placeholders**; replace `<id-or-slug>` with the right CurseForge **project ID** or Modrinth **slug** before running.

(You can delete this section after you add mods.)

