# 芝加哥大学数字孪生 · UChicago Hyde Park Digital Twin

A browser-based 3D model of the University of Chicago's Hyde Park campus and its
surroundings, built from OpenStreetMap data and rendered with Three.js, in a
"Chicago style":

- **Chicago flag palette**: white field, lake-blue water, landmarks marked with the
  flag's red six-point stars; UChicago maroon for the selected building.
- **Chicago address grid**: hover anywhere for its grid coordinate (800 numbers per
  mile from State & Madison); street names are drawn as green Chicago street signs.
- **Chicago architecture**: a style view separates Collegiate Gothic, Prairie School
  (Robie House), Chicago modernism (Mies, Saarinen, SOM) and contemporary work.
- **Chicago Manual of Style**: building notes carry footnotes and a bibliography in
  CMOS notes-bibliography form.

**Live:** https://felixjiashengfu.github.io/uchicago-digital-twin/

## What it does

- **Real geometry**: 3,857 building footprints (218 University buildings), roads,
  green space and water, the Metra Electric line, and 436 mapped trees.
- **Real sun**: sun position computed for Hyde Park at any date and time in Chicago
  local time, with shadows, sky colour, sunrise/sunset and a night palette.
- **Views**: massing model, architectural style, height, and a *simulated* activity
  layer driven by a schedule model per building type.
- **Inspect**: click any building for its address, grid coordinate, height and the
  source of that height, footprint area, and OSM citation; 25 landmarks have
  curated notes and a guided list.
- **Smooth zoom**: every wheel notch, pinch or `+`/`-` key press eases out over about
  0.3 s (frame-rate independent) and zooms about the exact point under the cursor;
  dragging keeps the grabbed point under the pointer. `tools/qa.mjs` measures one notch
  frame by frame: 95% of it is done after 0.33 s, no frame carries more than 14% of it,
  and the point under the cursor does not move (0.00 px).

Most heights are estimated: OSM gives measured heights for only two buildings, so
the rest use `levels × 3.6 m` or a per-type default, and a few landmarks are hand
estimated. The info panel names the source for every building. The activity layer
is a simulation, not sensor or card-swipe data.

## Layout

```
tools/fetch_osm.sh        download raw Overpass extracts into data/osm/
tools/process.py          project, clean and classify into data/campus.json
tools/build.mjs           inline the dataset into the viewer → dist/
tools/qa.mjs              automated browser checks (headless Chrome): zoom smoothness,
                          pan/rotate/pinch, fly-to; writes qa/report.json and screenshots
src/index.html            viewer source (data placeholder: __TWIN_DATA__)
dist/index.html           standalone page — open directly in a browser
dist/uchicago-twin.html   same page without a document skeleton (for publishing)
.github/workflows/        deploys dist/ to GitHub Pages on every push to main
```

## Rebuild

Processing the raw OSM data needs Python 3; building and checking the page run under
Deno (or Node 20+).

```sh
./tools/fetch_osm.sh                      # download raw OSM data (not stored in git)
python3 -I tools/process.py data/osm data/campus.json
deno run -A tools/build.mjs               # → dist/uchicago-twin.html, dist/index.html
deno install                              # playwright-core, for the checks
deno run -A --unsafe-proto tools/qa.mjs   # 16 checks in headless Chrome; add a URL to check the live site
```

## Controls

Drag to pan · right-drag to rotate and tilt (or Ctrl-drag) · scroll, pinch, middle-drag or
double-click to zoom (Shift + double-click zooms out) · two fingers: pinch to zoom, twist to
rotate, move up or down together to tilt · arrow keys pan, `+` / `-` zoom, `Q` / `E` turn ·
`Esc` closes the about panel and the mobile drawer.

Map data © OpenStreetMap contributors, available under the
[Open Database License](https://opendatacommons.org/licenses/odbl/). The derived
dataset in `data/campus.json` (and embedded in `dist/`) is likewise available under the ODbL.
Unofficial project, not affiliated with the University of Chicago.
