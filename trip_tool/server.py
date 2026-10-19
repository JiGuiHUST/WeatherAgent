# -*- coding: utf-8 -*-
"""HTTP 接口 + 一个自包含演示页（不依赖现有 templates/，不改任何已有文件）。

挂载方式（不改 run.py）：
    from run import app
    from trip_tool.server import bp
    app.register_blueprint(bp)
仓库根目录的 app_trip.py 已经替你写好了这一句。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .contract import TOOLS, dispatch

bp = Blueprint("trip_tool", __name__, url_prefix="/api/trip")


@bp.get("/tools")
def tools():
    """工具清单（OpenAI function-calling 格式），可直接交给大模型。"""
    return jsonify({"tools": TOOLS})


@bp.post("/plan_trip")
def plan_trip_api():
    """唯一主入口：body 即工具参数，只有一个 date 也是合法调用。"""
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() or {}
    result = dispatch("plan_trip", payload)
    return jsonify(result), (200 if result.get("ok") else 422)


@bp.route("/list_spots", methods=["GET", "POST"])
def list_spots_api():
    args = request.get_json(silent=True) or request.args.to_dict()
    return jsonify(dispatch("list_spots", args))


@bp.get("/demo")
def demo():
    """零依赖演示页：输入日期 → 出时间线 + 地图。"""
    return _DEMO_HTML


_DEMO_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>按日期规划行程 · trip_tool</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 body{margin:0;font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f6f7fb}
 header{padding:12px 16px;background:#0f172a;color:#e2e8f0;font-size:14px}
 header b{color:#38bdf8}
 .bar{display:flex;gap:8px;align-items:center;padding:12px 16px;background:#fff;
      border-bottom:1px solid #e2e8f0;flex-wrap:wrap}
 input,select,button{padding:7px 10px;border:1px solid #cbd5e1;border-radius:8px;font-size:14px}
 button{background:#2563eb;color:#fff;border:0;cursor:pointer}
 button:disabled{background:#94a3b8}
 #map{height:46vh}
 #out{padding:14px 16px;font-size:14px;line-height:1.9;white-space:pre-wrap}
 .stop{border-left:4px solid #2563eb;background:#fff;margin:8px 0;padding:8px 12px;border-radius:8px}
 .warn{color:#b45309;font-size:12px}
</style></head><body>
<header><b>trip_tool</b> · 输入一个日期，按当天天气排出武汉游览顺序</header>
<div class="bar">
  <input id="date" type="date">
  <input id="spots" type="number" min="1" max="8" value="4" style="width:90px" title="最多景点数">
  <select id="transport"><option value="mixed">自动（步行/打车取快）</option>
    <option value="walk">只步行</option><option value="drive">只打车</option></select>
  <button id="go">生成行程</button>
  <span id="status" class="warn"></span>
</div>
<div id="map"></div>
<div id="out"></div>
<script>
const d = new Date(); d.setDate(d.getDate()+1);
document.getElementById('date').value = d.toISOString().slice(0,10);
const map = L.map('map').setView([30.5567,114.3110], 12);
L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
  {subdomains:'1234',maxZoom:18,attribution:'底图高德（原型）'}).addTo(map);
let layer = L.layerGroup().addTo(map);
const out = document.getElementById('out'), st = document.getElementById('status');
document.getElementById('go').onclick = async () => {
  st.textContent = '计算中…';
  const body = {date: document.getElementById('date').value,
                max_spots: +document.getElementById('spots').value,
                transport: document.getElementById('transport').value};
  try {
    const r = await fetch('/api/trip/plan_trip', {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const j = await r.json();
    if (!j.ok) { out.textContent = '失败：' + (j.error || JSON.stringify(j.warnings)); st.textContent=''; return; }
    render(j);
    st.textContent = '';
  } catch (e) { out.textContent = '请求失败：' + e; st.textContent=''; }
};
function render(j) {
  out.innerHTML = '';
  layer.clearLayers();
  const pts = [];
  j.days.forEach(day => {
    const h = document.createElement('div');
    h.innerHTML = '<b>' + day.date + ' ' + day.weekday + '</b>　' +
      (day.weather.rain_start !== null && day.weather.rain_start !== undefined
        ? '降水 ' + day.weather.precip_total_mm + ' mm，' +
          String(day.weather.rain_start).padStart(2,'0') + '–' +
          String((day.weather.rain_end||0)+1).padStart(2,'0') + ' 时有雨'
        : '全天无降水');
    out.appendChild(h);
    day.stops.forEach((s, i) => {
      const el = document.createElement('div');
      el.className = 'stop';
      el.innerHTML = '<b>' + s.seq + '. ' + s.arrive + ' ' + s.name + '</b>　' +
        '适宜度 ' + s.suitability + '　' + (s.exposure || '') + '<br>' +
        s.reason + '<br><small>' + s.leg.transport + ' ' + s.leg.km + ' km / ' +
        s.leg.min + ' 分钟　<a target="_blank" href="' + s.leg.nav_url + '">高德导航</a></small>';
      out.appendChild(el);
      pts.push([s.lat, s.lon]);
      L.marker([s.lat, s.lon]).addTo(layer)
        .bindPopup(s.seq + '. ' + s.name).bindTooltip(s.seq + '. ' + s.name);
    });
    out.insertAdjacentHTML('beforeend',
      '<div class="warn">' + j.days[0].totals.travel_min + ' 分钟交通 / ' +
      j.days[0].totals.travel_km + ' km　求解器 ' + j.solver + '</div>');
  });
  (j.warnings || []).forEach(w => out.insertAdjacentHTML('beforeend',
    '<div class="warn">⚠ ' + w + '</div>'));
  if (pts.length) { L.polyline(pts, {color:'#2563eb', dashArray:'6 6'}).addTo(layer);
                    map.fitBounds(pts, {padding:[40,40]}); }
}
</script></body></html>"""
