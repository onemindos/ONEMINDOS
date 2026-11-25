# SPDX-License-Identifier: Apache-2.0
"""Exercise the shipped map tools in Node and the viewer HTTP route locally (#126)."""
import gzip
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
VIEWER = ROOT / "apps/offline-maps/manifests/map_viewer.py"
TOOLS = VIEWER.with_name("map_tools.js")


def pmtiles_fixture(attribution=None, compressed=False) -> tuple[bytes, bytes, int]:
    # One clustered z0 tile with an empty MVT layer.
    tile = b"\x1a\x0b\x0a\x07fixture\x78\x02"
    root = bytes([1, 0, 1, len(tile), 1])
    metadata_fields = {"vector_layers": [{"id": "fixture", "fields": {}}]}
    if attribution is not None:
        metadata_fields["attribution"] = attribution
    metadata = json.dumps(metadata_fields).encode()
    if compressed:
        root, metadata = gzip.compress(root, mtime=0), gzip.compress(metadata, mtime=0)
    root_offset = 127
    metadata_offset = root_offset + len(root)
    tile_offset = metadata_offset + len(metadata)
    header = b"PMTiles\x03" + struct.pack(
        "<11Q6B4iB2i", root_offset, len(root), metadata_offset, len(metadata),
        tile_offset, 0, tile_offset, len(tile), 1, 1, 1,
        1, 2 if compressed else 1, 1, 1, 0, 0, -10_000_000, -10_000_000, 10_000_000, 10_000_000,
        0, 0, 0,
    )
    return header + root + metadata + tile, tile, tile_offset


class OfflineArchiveTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("offline_map_archive_viewer", VIEWER)
        self.viewer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.viewer)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        work = Path(temporary.name)
        self.viewer.MAPS_DIR = work / "maps"
        self.viewer.MAPS_DIR.mkdir()
        self.archive, self.tile, self.tile_offset = pmtiles_fixture(
            '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>, Protomaps'
        )
        (self.viewer.MAPS_DIR / "region.pmtiles").write_bytes(self.archive)
        (self.viewer.MAPS_DIR / "truncated.pmtiles").write_bytes(self.archive[:-1])
        (work / "elsewhere.pmtiles").write_bytes(self.archive)
        (self.viewer.MAPS_DIR / "linked.pmtiles").symlink_to(work / "elsewhere.pmtiles")

        upstream = mock.patch.object(
            self.viewer.urllib.request, "urlopen", side_effect=AssertionError("expected an offline read")
        )
        upstream.start()
        self.addCleanup(upstream.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.viewer.Handler)
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, timeout=2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, **headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, response.headers, response.read()
        finally:
            connection.close()

    def test_lists_complete_archives_and_their_local_metadata(self):
        status, _, body = self.request("GET", "/api/maps")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), [{
            "name": "region.pmtiles", "bytes": len(self.archive),
            "bounds": [-1, -1, 1, 1], "min_zoom": 0, "max_zoom": 0,
            "attribution": "© OpenStreetMap contributors, Protomaps",
        }])

    def test_managed_pack_range_has_sha256_etag_and_disappears_when_removed(self):
        pack = self.viewer.MAPS_DIR / "packs" / "city"
        pack.mkdir(parents=True)
        archive = pack / "archive.pmtiles"
        archive.write_bytes(self.archive)
        status, headers, body = self.request("GET", "/packs/city", Range=f"bytes={self.tile_offset}-")
        self.assertEqual((status, body), (206, self.tile))
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(headers["ETag"], '"' + hashlib.sha256(self.archive).hexdigest() + '"')
        self.assertEqual(self.request("GET", "/packs/city", Range="bytes=999999-")[0], 416)
        archive.unlink()
        self.assertEqual(self.request("GET", "/packs/city")[0], 404)

    def test_reports_archive_attribution_only_when_available(self):
        fixtures = {
            "other.pmtiles": ('<a href="https://example.org">Other &amp; Different</a>', "Other & Different"),
            "uncredited.pmtiles": (None, None),
            "oversized.pmtiles": (" " * (self.viewer.MAX_METADATA_BYTES + 1), None),
        }
        for name, (attribution, _) in fixtures.items():
            archive, _, _ = pmtiles_fixture(attribution, compressed=True)
            (self.viewer.MAPS_DIR / name).write_bytes(archive)

        status, _, body = self.request("GET", "/api/maps")
        self.assertEqual(status, 200)
        by_name = {entry["name"]: entry["attribution"] for entry in json.loads(body)}
        self.assertEqual({name: by_name[name] for name in fixtures},
                         {name: expected for name, (_, expected) in fixtures.items()})

    def test_reads_tile_bytes_in_a_range_without_upstream(self):
        path = "/maps/region.pmtiles"
        end = len(self.archive) - 1
        status, headers, body = self.request("GET", path, Range=f"bytes={self.tile_offset}-{end}")
        self.assertEqual(status, 206)
        self.assertEqual(headers["Content-Type"], "application/vnd.pmtiles")
        self.assertEqual(headers["Content-Range"], f"bytes {self.tile_offset}-{end}/{len(self.archive)}")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertIsNone(headers["Access-Control-Allow-Origin"])
        self.assertEqual(body, self.tile)

        status, headers, body = self.request("HEAD", path)
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), len(self.archive))
        self.assertEqual(body, b"")

        for range_value in (f"bytes={len(self.archive)}-", "bytes=0-1,4-5", "bytes=" + "9" * 5000 + "-"):
            with self.subTest(range_value=range_value[:30]):
                status, headers, body = self.request("GET", path, Range=range_value)
                self.assertEqual(status, 416)
                self.assertEqual(headers["Content-Range"], f"bytes */{len(self.archive)}")
                self.assertEqual(body, b"")

    def test_refuses_symlinks_and_escaped_paths(self):
        for path in ("/maps/linked.pmtiles", "/maps/%2e%2e%2felsewhere.pmtiles"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path, Range="bytes=0-7")
                self.assertEqual(status, 404)


class MapToolsTests(unittest.TestCase):
    def test_geometry_and_distance(self):
        code = r"""
const assert = require('node:assert/strict');
require(process.argv[1]);
const {distance, overlay, draw} = globalThis.OneMindMapTools;
assert.equal(distance([0,0],[0,0]), 0);
assert.ok(Math.abs(distance([0,0],[1,0])-111195.08)<1);
assert.ok(distance([179.9,0],[-179.9,0])<23000);
assert.ok(Number.isFinite(distance([0,0],[180,0])));
for (const p of [[181,0],[0,91],['0',0],[NaN,0],null])
  assert.throws(()=>distance(p,[0,0]));
const feature = {type:'Feature',properties:{html:'<script>bad</script>'},
  geometry:{type:'Point',coordinates:[1,2]}};
assert.deepEqual(overlay(JSON.stringify(feature)).features[0].properties, {});
for (const g of [
  {type:'MultiPoint',coordinates:[[0,0],[1,1]]},
  {type:'LineString',coordinates:[[0,0],[1,1]]},
  {type:'MultiLineString',coordinates:[[[0,0],[1,1]]]},
  {type:'Polygon',coordinates:[[[0,0],[1,0],[1,1],[0,0]]]},
  {type:'MultiPolygon',coordinates:[[[[0,0],[1,0],[1,1],[0,0]]]]}
]) assert.equal(overlay(JSON.stringify(g)).features[0].geometry.type, g.type);
for (const bad of [null, 'https://example.com/map.json', {type:'constructor'},
  {type:'Point',coordinates:[0,Infinity]}, {type:'LineString',coordinates:[[0,0]]},
  {type:'Polygon',coordinates:[[[0,0],[1,0],[1,1],[0,1]]]},
  {type:'GeometryCollection',geometries:[]}, {type:'FeatureCollection',features:[]}
]) assert.throws(()=>overlay(JSON.stringify(bad)));
assert.throws(()=>overlay(' '.repeat(2*1024*1024+1)));
assert.throws(()=>overlay(JSON.stringify({type:'MultiPoint',coordinates:Array(50001).fill([0,0])})));
const data = overlay(JSON.stringify(feature));
const layers=[], sources={};
const map={getSource:id=>sources[id],addSource:(id,s)=>{sources[id]={...s,setData:d=>sources[id].data=d}},
  addLayer:l=>layers.push(l)};
draw(map,'test',data,'#123456');
assert.equal(layers.length,3);
assert.equal(sources.test.data.features.length,1);
draw(map,'test',{type:'FeatureCollection',features:[]},'#123456');
assert.equal(layers.length,3);
assert.equal(sources.test.data.features.length,0);
"""
        subprocess.run(["node", "-e", code, str(TOOLS)], check=True, capture_output=True, text=True)

    def test_viewer_serves_packaged_tools_without_assets_or_network(self):
        spec = importlib.util.spec_from_file_location("offline_map_viewer", VIEWER)
        viewer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(viewer)
        server = ThreadingHTTPServer(("127.0.0.1", 0), viewer.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(base + "/map_tools.js") as response:
                self.assertEqual(response.read(), TOOLS.read_bytes())
                self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
            with urllib.request.urlopen(base + "/") as response:
                page = response.read().decode()
                self.assertIn('src="map_tools.js"', page)
                self.assertIn('id="overlay"', page)
                script = page.split('<script>')[1].split('</script>')[0]
                result = subprocess.run(["node", "--check"], input=script, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
