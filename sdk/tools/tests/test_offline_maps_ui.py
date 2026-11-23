# SPDX-License-Identifier: Apache-2.0
"""Run the shipped viewer script with controlled DOM, map and file promises (#126)."""
import ast
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
VIEWER = ROOT / "apps/offline-maps/manifests/map_viewer.py"

HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
function deferred() {
  let resolve; const promise = new Promise(r => resolve = r);
  return {promise, resolve};
}
const elements = {};
for (const id of ['msg','pick','tools','measure','distance','overlay-status','reset','overlay','clear-overlay'])
  elements[id] = {disabled:id === 'tools', checked:false, textContent:'', value:'', files:[], append(){}};
const headers = {}, maps = [];
class FakeMap {
  constructor(options) { this.options=options; this.sources={}; this.handlers={}; maps.push(this); }
  on(type, fn) { this.handlers[type]=fn; }
  emit(type, event) { this.handlers[type]?.(event); }
  addControl() {}
  remove() { this.removed=true; }
  getSource(id) { return this.sources[id]; }
  addSource(id, source) { this.sources[id]={...source,setData:data=>this.sources[id].data=data}; }
  addLayer() {}
}
const context = vm.createContext({URL, TextEncoder,
  document:{getElementById:id=>elements[id],createElement:()=>({})},
  location:{href:'http://localhost/'},
  fetch:async()=>({json:async()=>[]}),
  pmtiles:{PMTiles:class {
    constructor(url) { this.name=new URL(url).pathname.split('/').pop(); }
    getHeader() { const d=deferred(); headers[this.name]=d; return d.promise; }
  },Protocol:class { tile(){} }},
  maplibregl:{Map:FakeMap,NavigationControl:class {},ScaleControl:class {},addProtocol(){}},
  basemaps:{layers:()=>[],namedFlavor:()=>({})}
});
vm.runInContext(input.tools, context);
vm.runInContext(input.script, context);
const header={minLon:0,minLat:0,maxLon:1,maxLat:1,minZoom:0,maxZoom:5};
async function loaded(name='map.pmtiles') {
  const pending=context.show(name); headers[name].resolve(header); await pending;
  const map=maps.at(-1); map.emit('load'); return map;
}
function file(name, pending) {
  elements.overlay.files=[{name,size:100,text:()=>pending.promise}];
  return elements.overlay.onchange({target:elements.overlay});
}
const point=n=>JSON.stringify({type:'Point',coordinates:[n,n]});
const click=(map,lng,lat)=>map.emit('click',{lngLat:{wrap:()=>({lng}),lat}});
(async()=>{
  // Let the viewer's startup (empty archive list) finish before exercising controls.
  for(let i=0;i<4;i++) await Promise.resolve();
  if(input.case==='archive_race') {
    const old=context.show('old.pmtiles'), recent=context.show('recent.pmtiles');
    headers['recent.pmtiles'].resolve(header); await recent;
    const selected=maps.at(-1); selected.emit('load');
    headers['old.pmtiles'].resolve(header); await old;
    assert.equal(maps.length,1,'late header must not construct an obsolete map');
    assert.match(elements.msg.textContent,/recent.pmtiles/);
    const next=context.show('next.pmtiles'); headers['next.pmtiles'].resolve(header); await next;
    selected.emit('load');
    assert.equal(elements.tools.disabled,true,'obsolete load cannot enable current controls');
    maps.at(-1).emit('load');
    assert.equal(elements.tools.disabled,false);
    elements.measure.checked=true; click(selected,1,1);
    assert.equal(maps.at(-1).sources.measurement.data.features.length,0);
  } else if(input.case==='clear_pending_overlay') {
    const map=await loaded(), pending=deferred();
    const reading=file('pending.geojson',pending);
    elements['clear-overlay'].onclick();
    pending.resolve(point(1)); await reading;
    assert.equal(map.sources.overlay.data.features.length,0,'clear invalidates pending file read');
    assert.equal(elements['overlay-status'].textContent,'Overlay cleared.');
  } else if(input.case==='overlay_race') {
    const map=await loaded(), old=deferred(), recent=deferred();
    const oldRead=file('old.geojson',old), recentRead=file('recent.geojson',recent);
    recent.resolve(point(2)); await recentRead;
    old.resolve(point(1)); await oldRead;
    assert.equal(map.sources.overlay.data.features[0].geometry.coordinates[0],2);
    assert.match(elements['overlay-status'].textContent,/recent.geojson/);
  } else if(input.case==='measure_reset_dateline') {
    const map=await loaded();
    click(map,0,0); assert.equal(map.sources.measurement.data.features.length,0);
    elements.measure.checked=true;
    click(map,179,0); assert.match(elements.distance.textContent,/second point/);
    click(map,-179,0);
    const features=map.sources.measurement.data.features;
    assert.equal(features.length,3);
    const line=features.find(f=>f.geometry.type==='LineString').geometry.coordinates;
    assert.equal(Math.abs(line[1][0]-line[0][0]),2,'render the short dateline segment');
    assert.match(elements.distance.textContent,/222\.39 km/);
    click(map,1,1); assert.equal(map.sources.measurement.data.features.length,1);
    elements.reset.onclick();
    assert.equal(map.sources.measurement.data.features.length,0);
    assert.match(elements.distance.textContent,/Enable measurement/);
  } else throw new Error('unknown test case');
})().catch(error=>{console.error(error);process.exitCode=1});
"""


class MapViewerUiTests(unittest.TestCase):
    def run_case(self, case):
        tree = ast.parse(VIEWER.read_text())
        page = next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "PAGE" for t in node.targets))
        script = page.split("<script>")[1].split("</script>")[0]
        script = script.replace("__CONF__", json.dumps({"assets": "ready", "flavor": "light", "lang": "en"}))
        payload = {"case": case, "script": script, "tools": VIEWER.with_name("map_tools.js").read_text()}
        result = subprocess.run(["node", "-e", HARNESS], input=json.dumps(payload),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_latest_archive_wins_when_headers_resolve_in_reverse(self):
        self.run_case("archive_race")

    def test_clear_invalidates_pending_overlay_read(self):
        self.run_case("clear_pending_overlay")

    def test_latest_overlay_wins_when_files_resolve_in_reverse(self):
        self.run_case("overlay_race")

    def test_measurement_toggle_reset_and_short_dateline_segment(self):
        self.run_case("measure_reset_dateline")


if __name__ == "__main__":
    unittest.main()
