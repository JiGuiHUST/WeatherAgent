/* 行程规划工具（trip_tool）页面：调用 /api/trip/plan_trip 并渲染时间线。 */
(function () {
  var form = document.getElementById('tripForm');
  if (!form) return;

  var i18nEl = document.getElementById('tripI18n');
  var i18n = i18nEl ? JSON.parse(i18nEl.textContent) : {};
  var resultEl = document.getElementById('tripResult');
  var errorEl = document.getElementById('tripError');
  var btn = document.getElementById('tripSubmit');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove('d-none');
  }

  function clearError() {
    errorEl.classList.add('d-none');
    errorEl.textContent = '';
  }

  function weatherLine(w) {
    if (!w) return '';
    var parts = [];
    if (w.rain_start !== null && w.rain_start !== undefined) {
      parts.push((i18n.rain || '降雨') + ' ' + (w.precip_total_mm || 0) + ' mm · ' +
        String(w.rain_start).padStart(2, '0') + '–' + String((w.rain_end || 0) + 1).padStart(2, '0') + 'h');
    } else {
      parts.push(i18n.no_rain || '全天无降水');
    }
    if (w.feels_max !== null && w.feels_max !== undefined) {
      parts.push((i18n.feels || '体感') + ' ' + Math.round(w.feels_max) + '℃');
    }
    return parts.join(' · ');
  }

  function stopHtml(s) {
    var leg = s.leg || {};
    var nav = leg.nav_url
      ? '<a class="ms-2" target="_blank" rel="noopener" href="' + esc(leg.nav_url) + '">' +
        '<i class="bi bi-geo-alt"></i> ' + esc(i18n.navigate || '导航') + '</a>'
      : '';
    return '' +
      '<div class="trip-stop">' +
      '  <div class="seq">' + s.seq + '</div>' +
      '  <div class="flex-grow-1">' +
      '    <div class="d-flex flex-wrap align-items-center gap-2">' +
      '      <span class="time">' + esc(s.arrive) + '–' + esc(s.leave) + '</span>' +
      '      <span class="fw-semibold">' + esc(s.name) + '</span>' +
      '      <span class="badge bg-success-subtle text-success-emphasis border border-success-subtle">' +
             esc(s.suitability) + '</span>' +
      '      <span class="badge bg-light text-secondary border">' + esc(s.exposure || '') + '</span>' +
      '    </div>' +
      '    <div class="small text-secondary mt-1">' + esc(s.reason) + '</div>' +
      '    <div class="leg mt-1">' +
      '      <i class="bi bi-signpost-split me-1"></i>' + esc(leg.transport || '') + ' ' +
             (leg.km != null ? esc(leg.km) + ' km' : '') + ' / ' +
             (leg.min != null ? esc(leg.min) + ' min' : '') + nav +
      '    </div>' +
      '  </div>' +
      '</div>';
  }

  function dayHtml(day) {
    var stops = (day.stops || []).map(stopHtml).join('');
    var dropped = (day.dropped || []).map(function (d) { return d.name; }).join('、');
    var droppedHtml = dropped
      ? '<div class="trip-totals px-3 py-2">' + esc(i18n.dropped || '未安排') + '：' + esc(dropped) + '</div>'
      : '';
    var totals = day.totals || {};
    var totalsHtml = '<div class="trip-totals px-3 py-2 border-top">' +
      (i18n.total || '合计') + ' ' + (totals.travel_min || 0) + ' min / ' +
      (totals.travel_km || 0) + ' km · ' + esc(totals.end_time || '') + '</div>';
    return '' +
      '<div class="card border-0 shadow-sm rounded-4 mb-3">' +
      '  <div class="trip-day-head">' +
      '    <span class="fw-bold"><i class="bi bi-calendar-event me-1 text-primary"></i>' +
           esc(day.date) + ' ' + esc(day.weekday) + '</span>' +
      '    <span class="text-muted small">' + esc(weatherLine(day.weather)) + '</span>' +
      '  </div>' +
      '  ' + stops + droppedHtml + totalsHtml +
      '</div>';
  }

  function render(data) {
    var days = (data.days || []).map(dayHtml).join('');
    var warnings = (data.warnings || []).map(function (w) {
      return '<li>' + esc(w) + '</li>';
    }).join('');
    var head = '<div class="d-flex flex-wrap gap-2 mb-3">' +
      '<span class="badge bg-light text-secondary border">' +
        esc(i18n.solver || '求解器') + ': ' + esc(data.solver || '—') + '</span>' +
      '<span class="badge bg-light text-secondary border">' +
        esc(i18n.stops || '景点') + ': ' + ((data.days && data.days[0] && data.days[0].stops) || []).length + '</span>' +
      '<span class="badge bg-light text-secondary border">' + (data.elapsed_ms || 0) + ' ms</span>' +
      '</div>';
    var warn = warnings
      ? '<div class="alert alert-warning rounded-4"><b>' + esc(i18n.warn || '提示') + '</b><ul class="mb-0 small mt-1">' + warnings + '</ul></div>'
      : '';
    resultEl.innerHTML = head + warn + days;
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    clearError();
    var date = document.getElementById('tripDate').value;
    if (!date) {
      showError(i18n.err_empty || '请选择日期');
      return;
    }
    btn.disabled = true;
    resultEl.innerHTML = '<div class="card border-0 shadow-sm rounded-4"><div class="card-body py-4">' +
      '<div class="d-flex align-items-center gap-3">' +
      '<div class="spinner-grow text-primary" role="status"></div>' +
      '<div><div class="fw-semibold text-primary">' + esc(i18n.planning || '正在规划…') + '</div>' +
      '<div class="small text-muted">取天气 → 评分 → 时间窗 → TSPTW 求解，通常 5–15 秒</div></div>' +
      '</div></div></div>';

    fetch('/api/trip/plan_trip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: date,
        max_spots: parseInt(document.getElementById('tripSpots').value, 10) || 4,
        transport: document.getElementById('tripTransport').value || 'mixed'
      })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.ok) {
          resultEl.innerHTML = '';
          showError((i18n.failed || '规划失败') + ': ' + ((data && data.error) || JSON.stringify(data && data.warnings)));
          return;
        }
        render(data);
      })
      .catch(function (e) {
        resultEl.innerHTML = '';
        showError((i18n.failed || '规划失败') + ': ' + e);
      })
      .finally(function () { btn.disabled = false; });
  });
})();
