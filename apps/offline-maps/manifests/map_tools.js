// SPDX-License-Identifier: Apache-2.0
// OneMind map tools (#126). GeoJSON positions follow RFC 7946 (longitude, latitude).
(function (root) {
  'use strict';
  function position(p) {
    if (!Array.isArray(p) || p.length < 2 || p.length > 3 ||
        !p.every(Number.isFinite) || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90)
      throw new Error('Use finite longitude/latitude coordinates in degrees.');
    return p.slice();
  }
  function distance(a, b) {
    a = position(a); b = position(b);
    const rad = Math.PI / 180;
    const h = Math.sin((b[1] - a[1]) * rad / 2) ** 2 +
      Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin((b[0] - a[0]) * rad / 2) ** 2;
    return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
  }
  function overlay(text) {
    if (new TextEncoder().encode(text).length > 2 * 1024 * 1024)
      throw new Error('Choose a GeoJSON file smaller than 2 MiB.');
    const data = JSON.parse(text);
    let count = 0;
    const pos = (p) => {
      if (++count > 50000) throw new Error('An overlay can contain at most 50,000 positions.');
      return position(p);
    };
    const list = (value, min, parse) => {
      if (!Array.isArray(value) || value.length < min) throw new Error('Invalid GeoJSON coordinates.');
      return value.map(parse);
    };
    const line = (v) => list(v, 2, pos);
    const ring = (v) => {
      const result = list(v, 4, pos);
      if (JSON.stringify(result[0]) !== JSON.stringify(result[result.length - 1]))
        throw new Error('Polygon rings must be closed.');
      return result;
    };
    const polygon = (v) => list(v, 1, ring);
    const parsers = {Point: pos, MultiPoint: (v) => list(v, 1, pos), LineString: line,
      MultiLineString: (v) => list(v, 1, line), Polygon: polygon, MultiPolygon: (v) => list(v, 1, polygon)};
    function feature(f) {
      const g = f?.type === 'Feature' ? f.geometry : f;
      if (!g || !Object.hasOwn(parsers, g.type))
        throw new Error('Use GeoJSON points, lines or polygons. GeometryCollection is unsupported.');
      // Keep geometry only: properties, links, HTML and remote styles are never interpreted.
      return {type: 'Feature', properties: {}, geometry: {type: g.type, coordinates: parsers[g.type](g.coordinates)}};
    }
    const features = data?.type === 'FeatureCollection' ? list(data.features, 1, feature) : [feature(data)];
    return {type: 'FeatureCollection', features};
  }
  function draw(map, id, data, color) {
    const source = map.getSource(id);
    if (source) { source.setData(data); return; }
    map.addSource(id, {type: 'geojson', data});
    map.addLayer({id: id + '-fill', source: id, type: 'fill', filter: ['==', '$type', 'Polygon'],
      paint: {'fill-color': color, 'fill-opacity': 0.2}});
    map.addLayer({id: id + '-line', source: id, type: 'line', filter: ['!=', '$type', 'Point'],
      paint: {'line-color': color, 'line-width': 3}});
    map.addLayer({id: id + '-point', source: id, type: 'circle', filter: ['==', '$type', 'Point'],
      paint: {'circle-color': color, 'circle-radius': 6, 'circle-stroke-color': '#fff', 'circle-stroke-width': 2}});
  }
  root.OneMindMapTools = {distance, overlay, draw};
})(globalThis);
