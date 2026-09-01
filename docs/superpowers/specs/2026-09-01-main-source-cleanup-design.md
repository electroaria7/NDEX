# Main Source Cleanup Design

## Goal

Keep the `main` branch as a clean, developer-facing source tree while keeping
the `distribution` branch and GitHub Releases as the install-and-use surfaces.
Align English and Korean user documentation, terms, and patch notes with that
workflow.

## Repository boundaries

The repository has three distinct surfaces:

1. `main` contains maintained source, tests, build definitions, licenses, and
   public documentation.
2. `distribution` contains the source-free portable Windows package.
3. GitHub Releases provide the recommended `NDEX_v1.0.0.zip` download.

The root of `main` keeps GitHub-standard public files:

- `README.md`
- `README.ko.md`
- `LICENSE`
- `TERMS.md`
- `TERMS.ko.md`
- `PATCH_NOTES.md`
- `THIRD_PARTY_NOTICES.md`

Developer reviews, architecture notes, specifications, and plans remain under
lowercase `docs/`. App-specific documentation remains with its app.

## Source-tree cleanup

Remove generated PyInstaller files currently tracked under:

- `dsb_image_manager/build/`
- `ndex_auto_selector/build/`
- `ndex_launcher/build/`

Remove ignored local build, cache, distribution, release, and app-data output by
running the maintained cleanup script with distribution cleanup enabled.

Preserve maintained build inputs:

- `build/build.ps1`
- `build/installer.iss`
- `build/NDEX_One.spec`
- `build/NDEX_One.onefile.spec`
- each app's `build_package.ps1`
- `build_all.ps1`
- `cleanup.ps1`

The existing ignore rule for per-app `build/` directories remains the boundary
that prevents regenerated PyInstaller output from returning to source control.

## README content

`README.md` and `README.ko.md` use matching sections and equivalent content.
They lead with two explicit paths:

- Users download the release ZIP and start `NDEX_Launcher.exe`.
- Developers clone `main`, install dependencies, and run or build from source.

Both documents link the GitHub Release, identify `distribution` as source-free,
show the installed/portable `Apps\` and `Docs\` layout, show the clean `main`
source layout, and explain where generated build output appears.

## Terms

The English and Korean terms remain separate root files with matching meaning.
They retain the MIT permission grant and no-warranty language and clarify:

- NDEX runs locally and has no account or subscription.
- photographs remain the user's property;
- the user remains responsible for backups;
- existing Master and export files are protected by the documented workflow;
- official packages come from this repository's Releases or `distribution`
  branch;
- third-party components retain their licenses;
- deleting the portable folder or uninstalling the installed application ends
  use.

## Patch notes

Add a dated suite-level entry to `PATCH_NOTES.md` covering:

- source-only `main` cleanup;
- generated artifact removal;
- the `main`/`distribution`/Releases workflow;
- synchronized English and Korean docs and terms;
- active branch rulesets and removal of merged feature branches;
- stability and security audit results, including the Pillow upgrade requirement
  and unsigned-binary status.

App-specific Frame history remains in `ndex_frame/PATCH_NOTES.md`; this cleanup
does not duplicate suite-only changes there.

## Verification

Verification must prove:

- no generated per-app build outputs are tracked;
- maintained root build scripts and specs remain tracked;
- the packaging ignore regression test passes;
- English and Korean README/terms links and section intent remain aligned;
- all non-GUI tests pass;
- the five packaged executables still have the previously verified startup
  result, without rebuilding during this source-tree cleanup;
- the working tree contains only intentional cleanup and documentation changes.

The known local Tk installation problem is reported separately because it
prevents one source-layout GUI test from running but did not prevent the
packaged launcher from starting.
