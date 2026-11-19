# SPDX-License-Identifier: Apache-2.0
"""Exercise the shipped map tools in Node and the viewer HTTP route locally (#126)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[3]
VIEWER = ROOT / "apps/offline-maps/manifests/map_viewer.py"
TOOLS = VIEWER.with_name("map_tools.js")


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
