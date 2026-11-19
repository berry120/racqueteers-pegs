# Name pegs

Edit `names.txt`, push to `main`, and a GitHub Action regenerates:

- `stl/` - one binary STL per name
- `3mf/` - one Bambu Studio project per name, with your printer/filament/process settings,
  tree supports and the pause (colour-change stop) already in place

The folders always mirror `names.txt`: add a name and its files appear, remove a name and its
files are deleted.

## Repository contents

| File | What it is |
| --- | --- |
| `names.txt` | The list of names, one per line. Blank lines and lines starting with `#` are ignored. |
| `peg.scad` | The parametric OpenSCAD model. The text auto-shrinks to fit. |
| `template.3mf` | Bambu Studio project holding the settings, supports and the colour-change stop. |
| `make_pegs.py` | Renders each name with OpenSCAD and swaps the mesh into the template. |
| `.github/workflows/build-pegs.yml` | The GitHub Action. |

## Setting up on GitHub

1. Create a new empty repository on GitHub (the branch must be called `main`).
2. Push this folder to it. Using git is the most reliable way, because the hidden `.github` folder
   can be missed by drag-and-drop uploads:
   ```
   git init -b main
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. Open the **Actions** tab. If the first build didn't start by itself, choose
   **Build pegs -> Run workflow**.
4. If the build fails at the "Commit changes" step with a permissions error, go to
   **Settings -> Actions -> General -> Workflow permissions** and choose
   **Read and write permissions**.

After that, any commit to `main` that changes `names.txt` (including editing it in the GitHub web
editor) triggers a rebuild. The Action commits the result back as "Update pegs from names.txt".
Those commits don't trigger another build.

If `main` is protected and requires pull requests, the Action's push will be rejected. Either allow
GitHub Actions to bypass the rule, or run the script locally (below) and commit the output yourself.

## Changing the design

- **Model:** edit `peg.scad` (dimensions, font, text size limits). Changing it rebuilds everything.
- **Print settings, supports or colour-change stops:** open `template.3mf` in Bambu Studio, change
  them, save over `template.3mf`, and commit it. Everything rebuilds with the new settings.
- The template is tied to the part's overall size (110 x 20 x 10.2 mm). If you change the body
  dimensions in `peg.scad`, rebuild the template from the new STL, or the script will stop and tell
  you the sizes no longer match.
- The width table in `peg.scad` is measured for Liberation Sans Bold. Another font will still
  work but the auto-fit will only be approximate.

## Running it locally

You need Python 3.8+ and OpenSCAD.

```
python make_pegs.py --template template.3mf --scad peg.scad --names-file names.txt --sync
```

Or for a few one-off names without touching the folders' other contents:

```
python make_pegs.py --template template.3mf --scad peg.scad Alice Bob
```

On Windows, if OpenSCAD isn't on your PATH, add `--openscad "C:\Program Files\OpenSCAD\openscad.exe"`.

## Notes

- Names that need the text smaller than 4 mm are flagged in the build log as hard to read.
- A name that can't be built fails the run, and nothing is committed or deleted.
- Accented Latin letters (José, Muñoz) work, but their width in the auto-fit is estimated rather than
  measured, and the file names are written without accents (`Jose_Munoz`). Scripts that Liberation
  Sans doesn't cover (for example Chinese or Arabic) may come out as placeholder boxes or blank, and the
  build only fails if no text at all is produced, so check those pegs in the preview.
