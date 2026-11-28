# SPDX-License-Identifier: Apache-2.0
"""Offline Maps viewer: shows the PMTiles map archives on this box, with no internet needed.

Part of the Offline Knowledge bundle (REC-NOMAD-01). The browser draws vector maps with MapLibre
GL JS and the Protomaps basemap style, reading tiles straight out of a .pmtiles file with HTTP
range requests. This server:

- serves the viewer page, and the map archives in MAPS_DIR (GET with Range support only);
- on first start, downloads the viewer's browser libraries, fonts and icons once, each checked
  against a pinned hash (ASSETS below), into ASSETS_DIR. After that the box needs no internet.

Read-only towards the maps: it never writes, renames or deletes an archive. Making a map is the
owner's step (README, "Add a map"). Python standard library only.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import stat
import struct
import sys
import tarfile
import threading
import urllib.parse
import urllib.request
import zlib
from collections import OrderedDict
from collections.abc import Iterator
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO

PORT = int(os.environ.get("PORT", "8080"))
MAPS_DIR = Path(os.environ.get("MAPS_DIR", "/data/maps"))
ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", "/data/assets"))
LANG = re.sub(r"[^a-z-]", "", os.environ.get("MAPS_LANG", "") or "en")[:8] or "en"
FLAVOR = os.environ.get("MAPS_FLAVOR", "") or "light"
if FLAVOR not in ("light", "dark", "white", "grayscale", "black"):
    FLAVOR = "light"

# Pinned browser assets: (url, hash algorithm, expected digest (base64 for sha512 as npm gives it,
# hex for sha256), {path inside the archive: path under ASSETS_DIR}). A prefix ending in "/"
# copies a whole folder. (The pmtiles and basemaps npm packages ship no licence file; both are
# BSD-3-Clause per their package.json, recorded in research-output/evidence/license-matrix.csv.) Versions and digests read from the npm registry and GitHub on 2026-11-14.
ASSETS = [
    ("https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-5.24.1.tgz", "sha512",
     "HyiYBwtsbk3L1n1EPLJHWqdoyMiF80n7tEYXFZyu2m1TjvaNx6KMLiFeDdmszt1/mq2zvsR1TJuX/NMu5BonXQ==",
     {"package/dist/maplibre-gl.js": "maplibre-gl.js", "package/dist/maplibre-gl.css": "maplibre-gl.css",
      "package/LICENSE.txt": "licences/maplibre-gl.txt"}),
    ("https://registry.npmjs.org/pmtiles/-/pmtiles-4.5.0.tgz", "sha512",
     "CBeD4SoUluFziGdy/8k7FOjQxQy486n+929W/tWophauvMICpkZ26vGBWhDt/6b1FZQWNaf4jFdT/5+q0Wii5w==",
     {"package/dist/pmtiles.js": "pmtiles.js"}),
    ("https://registry.npmjs.org/@protomaps/basemaps/-/basemaps-5.7.2.tgz", "sha512",
     "K1Yk6bWdULulYg+R2QRVXx4NzJZan5YQhpejEG0c1/sXruJrfPIPZuakpf3jwAgVmjIRVQwAv+yRafDeN0aaUQ==",
     {"package/dist/basemaps.js": "basemaps.js"}),
    # protomaps/basemaps-assets at commit 028c18f713ba: fonts (SIL OFL 1.1) and sprites (MIT).
    ("https://codeload.github.com/protomaps/basemaps-assets/tar.gz/028c18f713baecad011301ff7a69acc39bcc2ae7",
     "sha256", "57e40e8c512bd8042d0a3a251f19d0d1c8523ad963c666c3c6643bada4dc92d0",
     {"basemaps-assets-028c18f713baecad011301ff7a69acc39bcc2ae7/fonts/": "fonts/",
      "basemaps-assets-028c18f713baecad011301ff7a69acc39bcc2ae7/sprites/v3/": "sprites/v3/"}),
]
READY = ASSETS_DIR / ".ready-v1"
STATE = {"assets": "missing", "detail": ""}
PACK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ARCHIVE_FILE = "archive.pmtiles"
PACKS_FOLDER = "packs"
ETAG_CACHE_SIZE = 64
_etag_lock = threading.Lock()
_etags: OrderedDict[tuple[int, ...], str] = OrderedDict()
PMTILES_HEADER_SIZE = 127
PMTILES_TYPE = "application/vnd.pmtiles"
PMTILES_UNCOMPRESSED = 1
PMTILES_GZIP = 2
MAX_METADATA_BYTES = 256 * 1024


def digest_ok(data: bytes, algo: str, want: str) -> bool:
    h = hashlib.new(algo, data).digest()
    return (base64.b64encode(h).decode() if algo == "sha512" else h.hex()) == want


def unpack(data: bytes, mapping: dict[str, str], dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            for src, dst in mapping.items():
                if src.endswith("/") and m.name.startswith(src):
                    rel = dst + m.name[len(src):]
                elif m.name == src:
                    rel = dst
                else:
                    continue
                target = (dest / rel).resolve()
                if dest.resolve() not in target.parents:  # no path escapes the assets folder
                    raise ValueError(f"unsafe path in archive: {m.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as f, open(target, "wb") as out:
                    shutil.copyfileobj(f, out)


def fetch_assets() -> None:
    if READY.exists():
        STATE["assets"] = "ready"
        return
    STATE["assets"] = "downloading"
    tmp = ASSETS_DIR.with_name(ASSETS_DIR.name + ".new")
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        for url, algo, want, mapping in ASSETS:
            req = urllib.request.Request(url, headers={"User-Agent": "onemind-offline-maps"})
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 (pinned URLs above)
                data = r.read(64 * 1024 * 1024)
            if not digest_ok(data, algo, want):
                raise ValueError(f"hash mismatch for {url}: refusing it")
            unpack(data, mapping, tmp)
        (tmp / READY.name).write_text("ok\n")
        shutil.rmtree(ASSETS_DIR, ignore_errors=True)
        tmp.rename(ASSETS_DIR)
        STATE.update(assets="ready", detail="")
        print("offline-maps: viewer assets downloaded and verified", flush=True)
    except Exception as e:  # noqa: BLE001 (report any failure on the page, retry on restart)
        shutil.rmtree(tmp, ignore_errors=True)
        STATE.update(assets="failed", detail=str(e)[:300])
        print(f"offline-maps: viewer assets not ready: {e}", file=sys.stderr, flush=True)


def _open_archive(folder: int, entry_name: str, managed: bool) -> BinaryIO | None:
    child = None
    try:
        if managed:
            child = os.open(entry_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
            folder, entry_name = child, ARCHIVE_FILE
        fd = os.open(entry_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    except OSError:
        return None
    finally:
        if child is not None:
            os.close(child)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        return None
    return os.fdopen(fd, "rb")


def _archives(managed: bool, wanted: str | None = None) -> Iterator[tuple[str, BinaryIO]]:
    if wanted is not None and not PACK_ID.fullmatch(wanted):
        return
    directory = Path(os.environ.get("MAP_PACKS_DIR", MAPS_DIR / PACKS_FOLDER)) if managed else MAPS_DIR
    try:
        folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if managed:
                    pack_id = entry.name
                elif entry.name.endswith(".pmtiles"):
                    pack_id = entry.name.removesuffix(".pmtiles")
                else:
                    continue
                if (wanted is not None and pack_id != wanted) or not PACK_ID.fullmatch(pack_id):
                    continue
                # The request only selects an enumerated entry. Open its name from the directory
                # listing, with symlinks refused for both the pack directory and the archive file.
                archive = _open_archive(folder, entry.name, managed)
                if archive is not None:
                    yield pack_id, archive
    finally:
        os.close(folder)


def _archive_etag(file: BinaryIO) -> str:
    st = os.fstat(file.fileno())
    key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    with _etag_lock:
        cached = _etags.get(key)
        if cached is not None:
            _etags.move_to_end(key)
            return cached
    digest = hashlib.sha256()
    file.seek(0)
    while chunk := file.read(1024 * 1024):
        digest.update(chunk)
    etag = '"' + digest.hexdigest() + '"'
    with _etag_lock:
        _etags[key] = etag
        _etags.move_to_end(key)
        if len(_etags) > ETAG_CACHE_SIZE:
            _etags.popitem(last=False)
    return etag


class AttributionText(HTMLParser):
    """Collect a plain-text label from archive attribution, which may contain links."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def map_attribution(archive: BinaryIO, offset: int, length: int, compression: int) -> str | None:
    if length > MAX_METADATA_BYTES or compression not in (PMTILES_UNCOMPRESSED, PMTILES_GZIP):
        return None
    try:
        archive.seek(offset)
        data = archive.read(length)
        if len(data) != length:
            return None
        if compression == PMTILES_GZIP:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                data = compressed.read(MAX_METADATA_BYTES + 1)
        if len(data) > MAX_METADATA_BYTES:
            return None
        metadata = json.loads(data)
        attribution = metadata.get("attribution") if isinstance(metadata, dict) else None
        if not isinstance(attribution, str) or len(attribution) > 4096:
            return None
        text = AttributionText()
        text.feed(attribution)
        text.close()
        return " ".join("".join(text.parts).split()) or None
    except (EOFError, OSError, ValueError, RecursionError, zlib.error, AssertionError):
        return None


def map_entry(name: str, archive: BinaryIO) -> dict | None:
    # PMTiles v3 fixed header. Reads are limited to the header and bounded metadata.
    # https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md#3-header
    header = archive.read(PMTILES_HEADER_SIZE)
    size = os.fstat(archive.fileno()).st_size
    if len(header) != PMTILES_HEADER_SIZE or header[:8] != b"PMTiles\x03":
        return None
    root_offset, root_bytes, metadata_offset, metadata_bytes, leaf_offset, leaf_bytes, tile_offset, tile_bytes = (
        struct.unpack_from("<8Q", header, 8)
    )
    sections = ((root_offset, root_bytes), (metadata_offset, metadata_bytes),
                (leaf_offset, leaf_bytes), (tile_offset, tile_bytes))
    if not root_bytes or not tile_bytes or not metadata_bytes or root_offset + root_bytes > 16_384:
        return None
    if any(length and not PMTILES_HEADER_SIZE <= offset < offset + length <= size
           for offset, length in sections):
        return None
    west, south, east, north = (value / 10_000_000 for value in struct.unpack_from("<4i", header, 102))
    min_zoom, max_zoom = header[100:102]
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90 and min_zoom <= max_zoom):
        return None
    return {"name": name, "bytes": size, "bounds": [west, south, east, north],
            "min_zoom": min_zoom, "max_zoom": max_zoom,
            "attribution": map_attribution(archive, metadata_offset, metadata_bytes, header[97])}


def list_maps() -> list[dict]:
    maps = []
    for managed in (True, False):
        for pack_id, archive in _archives(managed):
            with archive:
                entry = map_entry(f"{pack_id}.pmtiles", archive)
            if entry is not None:
                if managed:
                    entry["path"] = f"packs/{pack_id}"
                maps.append(entry)
    return sorted(maps, key=lambda entry: entry["name"])


def parse_range(header: str, size: int) -> tuple[int, int] | None:
    """One 'bytes=a-b' / 'bytes=a-' / 'bytes=-n' range, clamped; None if unusable."""
    m = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", header.strip())
    if not m or (not m.group(1) and not m.group(2)) or size == 0:
        return None
    if m.group(1):
        start = int(m.group(1))
        end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
    else:
        start, end = max(0, size - int(m.group(2))), size - 1
    return (start, end) if start <= end and start < size else None


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline Maps</title>
<link rel="stylesheet" href="assets/maplibre-gl.css">
<style>
:root{color-scheme:light dark;--bg:#f7f7f5;--fg:#1d1d1b;--muted:#5d5d58;--card:#fff;--line:#dcdcd6}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--muted:#a3a39d;--card:#20201f;--line:#3a3a37}}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
#bar{position:absolute;z-index:2;top:.75rem;left:.75rem;right:.75rem;max-width:28rem;background:var(--card);border:1px solid var(--line);border-radius:.6rem;padding:.6rem .75rem}
#bar h1{font-size:1rem;margin:0 0 .25rem}select{max-width:100%;font:inherit}.muted{color:var(--muted);font-size:.85rem}
#map{position:absolute;inset:0}
</style></head><body>
<div id="bar"><h1>Offline Maps</h1><div id="msg" class="muted">Loading…</div><select id="pick" aria-label="Map archive" hidden></select>
<fieldset id="tools" disabled><legend>Local map tools</legend>
<label><input id="measure" type="checkbox"> Measure two points</label>
<button id="reset" type="button">Clear measurement</button>
<p id="distance" role="status">Enable measurement, then click two places on the map.</p>
<label>GeoJSON overlay <input id="overlay" type="file" accept=".geojson,.json,application/geo+json,application/json"></label>
<button id="clear-overlay" type="button">Clear overlay</button>
<p id="overlay-status" role="status">Stays in this tab; never uploaded. Maximum 2 MiB.</p>
</fieldset></div>
<div id="map"></div>
<script src="assets/maplibre-gl.js"></script><script src="assets/pmtiles.js"></script><script src="assets/basemaps.js"></script>
<script src="map_tools.js"></script>
<script>
const msg=document.getElementById('msg'),pick=document.getElementById('pick');
const CONF=__CONF__;let map;
const tools=document.getElementById('tools'),measure=document.getElementById('measure');
const distance=document.getElementById('distance'),overlayStatus=document.getElementById('overlay-status');
const empty=()=>({type:'FeatureCollection',features:[]});
let points=[],overlayData=empty(),showGeneration=0,overlayGeneration=0;
function drawMeasurement(){
  const features=points.map(p=>({type:'Feature',properties:{},geometry:{type:'Point',coordinates:p}}));
  if(points.length===2){
    const end=points[1].slice();
    while(end[0]-points[0][0]>180)end[0]-=360;
    while(end[0]-points[0][0]<-180)end[0]+=360;
    features.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[points[0],end]}});
  }
  OneMindMapTools.draw(map,'measurement',{type:'FeatureCollection',features},'#b54d17');
}
document.getElementById('reset').onclick=()=>{points=[];drawMeasurement();distance.textContent='Enable measurement, then click two places on the map.'};
document.getElementById('overlay').onchange=async(e)=>{
  const generation=++overlayGeneration;
  const file=e.target.files[0];if(!file)return;
  try{
    if(file.size>2*1024*1024)throw new Error('Choose a GeoJSON file smaller than 2 MiB.');
    const data=OneMindMapTools.overlay(await file.text());
    if(generation!==overlayGeneration)return;
    overlayData=data;
    if(!tools.disabled)OneMindMapTools.draw(map,'overlay',overlayData,'#176ba0');
    overlayStatus.textContent=file.name+' · '+data.features.length+' features (this tab only)';
  }catch(error){if(generation===overlayGeneration)overlayStatus.textContent='Could not add overlay: '+error.message}
  if(generation===overlayGeneration)e.target.value='';
};
document.getElementById('clear-overlay').onclick=()=>{
  ++overlayGeneration;
  overlayData=empty();OneMindMapTools.draw(map,'overlay',overlayData,'#176ba0');overlayStatus.textContent='Overlay cleared.';
};
function say(t){msg.textContent=t}
async function show(name,path){
  const generation=++showGeneration;
  tools.disabled=true;points=[];distance.textContent='Enable measurement, then click two places on the map.';
  const url=new URL(path||'maps/'+encodeURIComponent(name),location.href).href;
  const p=new pmtiles.PMTiles(url);const h=await p.getHeader();
  if(generation!==showGeneration)return;
  const base=new URL('.',location.href).href;  // the {tokens} must stay unescaped
  const style={version:8,glyphs:base+'assets/fonts/{fontstack}/{range}.pbf',
    sprite:base+'assets/sprites/v3/'+CONF.flavor,
    sources:{protomaps:{type:'vector',url:'pmtiles://'+url,attribution:'<a href="https://openstreetmap.org/copyright">© OpenStreetMap contributors</a>, Protomaps'}},
    layers:basemaps.layers('protomaps',basemaps.namedFlavor(CONF.flavor),{lang:CONF.lang})};
  if(map)map.remove();
  const currentMap=new maplibregl.Map({container:'map',style,bounds:[[h.minLon,h.minLat],[h.maxLon,h.maxLat]],maxZoom:Math.max(h.maxZoom+2,4)});
  map=currentMap;
  map.addControl(new maplibregl.NavigationControl());map.addControl(new maplibregl.ScaleControl());
  map.on('load',()=>{
    if(generation!==showGeneration)return;
    drawMeasurement();OneMindMapTools.draw(map,'overlay',overlayData,'#176ba0');tools.disabled=false;
  });
  map.on('click',(e)=>{
    if(generation!==showGeneration||!measure.checked||tools.disabled)return;
    if(points.length===2)points=[];
    points.push([e.lngLat.wrap().lng,e.lngLat.lat]);drawMeasurement();
    distance.textContent=points.length<2?'Choose the second point.':
      'Approximate straight-line distance: '+(OneMindMapTools.distance(...points)/1000).toFixed(2)+' km. Not a route.';
  });
  say(name+' · zoom '+h.minZoom+'–'+h.maxZoom);
}
(async()=>{
  if(CONF.assets!=='ready'){say(CONF.assets==='downloading'?'Getting the map viewer ready (first start needs internet once). Reload in a minute.':'The map viewer could not be prepared: '+CONF.detail);return}
  maplibregl.addProtocol('pmtiles',new pmtiles.Protocol().tile);
  const maps=await (await fetch('api/maps')).json();
  if(!maps.length){say('No maps yet. The owner adds one (README, "Add a map").');return}
  for(const [i,m] of maps.entries()){const o=document.createElement('option');o.value=i;o.textContent=m.name+' ('+Math.round(m.bytes/1048576)+' MiB)';pick.append(o)}
  pick.hidden=maps.length<2;pick.onchange=()=>show(maps[Number(pick.value)].name,maps[Number(pick.value)].path).catch(e=>say('Could not open the map: '+e));
  show(maps[0].name,maps[0].path).catch(e=>say('Could not open the map: '+e));
})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "onemind-offline-maps"
    sys_version = ""

    def _headers(self, code: int, ctype: str, length: int, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data: blob:; worker-src 'self' blob:; child-src blob:; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self._headers(code, ctype, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, path: Path) -> None:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".pbf":
            ctype = "application/x-protobuf"
        with path.open("rb") as file:
            self._stream(file, ctype, ranged=False)

    def _stream(self, file: BinaryIO, ctype: str, ranged: bool) -> None:
        size = os.fstat(file.fileno()).st_size
        range_header = self.headers.get("Range") if ranged else None
        etag = _archive_etag(file) if ranged else None
        if range_header is not None and self.headers.get("If-Range", etag) != etag:
            range_header = None
        rng = parse_range(range_header, size) if range_header is not None else None
        if range_header is not None and rng is None:
            return self._headers(416, "text/plain", 0, {"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes",
                                                       "ETag": etag})
        start, end = rng or (0, size - 1)
        length = end - start + 1 if size else 0
        extra = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache" if ranged else "max-age=86400"}
        if etag is not None:
            extra["ETag"] = etag
        if rng:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._headers(206 if rng else 200, ctype, length, extra)
        if self.command == "HEAD" or not length:
            return
        file.seek(start)
        left = length
        while left:
            chunk = file.read(min(left, 256 * 1024))
            if not chunk:
                break
            self.wfile.write(chunk)
            left -= len(chunk)

    def do_GET(self):  # noqa: N802
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/":
            conf = json.dumps({"assets": STATE["assets"], "detail": STATE["detail"], "lang": LANG, "flavor": FLAVOR})
            return self._send(200, PAGE.replace("__CONF__", conf.replace("<", "\\u003c")).encode(),
                              "text/html; charset=utf-8")
        if path == "/healthz":
            return self._send(200, b"ok\n", "text/plain")
        if path == "/api/maps":
            return self._send(200, json.dumps(list_maps()).encode(), "application/json")
        if path == "/map_tools.js":
            return self._file(Path(__file__).with_name("map_tools.js"))
        if path.startswith(("/maps/", "/packs/")):
            managed = path.startswith("/packs/")
            pack_id = path.split("/", 2)[2]
            if not managed:
                pack_id = pack_id.removesuffix(".pmtiles") if pack_id.endswith(".pmtiles") else ""
            for _, archive in _archives(managed, pack_id):
                with archive:
                    return self._stream(archive, PMTILES_TYPE, ranged=True)
        elif path.startswith("/assets/") and STATE["assets"] == "ready":
            target = (ASSETS_DIR / path[len("/assets/"):]).resolve()
            if ASSETS_DIR.resolve() in target.parents and target.is_file() and not target.name.startswith("."):
                return self._file(target)
        self._send(404, b"not found\n", "text/plain")

    do_HEAD = do_GET

    def log_message(self, fmt, *args):
        pass  # tile requests are many and say nothing useful; errors go to stderr above


def main() -> None:
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=fetch_assets, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)  # noqa: S104 (pod network only)
    srv.daemon_threads = True
    print(f"offline-maps viewer on :{PORT}, maps in {MAPS_DIR}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
