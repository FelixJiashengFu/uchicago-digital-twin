#!/bin/sh
# Download the raw OpenStreetMap extract for Hyde Park into data/osm/.
# The public Overpass servers are often busy, so each query falls back to a mirror.
set -e
cd "$(dirname "$0")/.."
OUT=data/osm
mkdir -p "$OUT"
UA="uchicago-digital-twin/1.0"
B='41.7795,-87.6115,41.8015,-87.5830'

fetch() { # fetch <outfile> <query>
  for API in https://overpass-api.de/api/interpreter https://maps.mail.ru/osm/tools/overpass/api/interpreter; do
    if curl -sf -m 200 -A "$UA" -o "$1" --data-urlencode "data=$2" "$API" && head -c 64 "$1" | grep -q '"version"'; then
      return 0
    fi
    echo "  $API failed, trying next" >&2
  done
  echo "could not download $1" >&2
  return 1
}

# everything except multipolygon members: buildings, streets, ground cover, rails, trees, artworks
fetch "$OUT/data.json" "[out:json][timeout:180];
( way[\"building\"]($B); relation[\"building\"]($B); way[\"building:part\"]($B);
  way[\"highway\"]($B);
  way[\"leisure\"]($B); relation[\"leisure\"]($B);
  way[\"landuse\"]($B);
  way[\"natural\"]($B); relation[\"natural\"]($B);
  way[\"railway\"]($B);
  way[\"amenity\"=\"university\"]($B); relation[\"amenity\"=\"university\"]($B);
  node[\"natural\"=\"tree\"]($B);
  node[\"historic\"]($B);
  node[\"artwork_type\"]($B); );
out geom tags;"

# multipolygon relations with their member geometry (campus boundary, Midway, multi-part buildings)
fetch "$OUT/rels.json" "[out:json][timeout:180];
( relation[\"building\"]($B); relation[\"leisure\"]($B); relation[\"natural\"]($B);
  relation[\"landuse\"]($B); relation[\"amenity\"=\"university\"]($B); );
out geom;"

ls -la "$OUT"
