/* 目的地二级菜单：一级「国内 / 国外 + 国家」，二级「城市」。
   数据来自 #destData（services/destinations.menu() 的 JSON）。 */
(function () {
  var dataEl = document.getElementById('destData');
  var toggle = document.getElementById('destToggle');
  if (!dataEl || !toggle) return;

  var data = JSON.parse(dataEl.textContent);
  var input = document.getElementById('destInput');
  var label = document.getElementById('destLabel');
  var errorEl = document.getElementById('destError');
  var countryWrap = document.getElementById('destCountries');
  var cityWrap = document.getElementById('destCities');
  var cityTitle = document.getElementById('destCityTitle');
  var isEn = !!window.LANG_EN;

  var current = { scope: null, entry: null, city: null };

  function text(entry) {
    return isEn ? (entry.label_en || entry.label) : entry.label;
  }

  function el(tag, cls, html) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html !== undefined) node.innerHTML = html;
    return node;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function keyOf(scope, entry) {
    return scope + '|' + entry.country + '|' + (entry.region || '');
  }

  function scopeHeader(scope) {
    var row = el('div', 'dest-scope');
    row.innerHTML = scope === 'domestic'
      ? '<i class="bi bi-house-door-fill me-1"></i>' + (isEn ? 'Domestic' : '国内')
      : '<i class="bi bi-globe2 me-1"></i>' + (isEn ? 'Overseas' : '国外');
    return row;
  }

  function countryButton(scope, entry) {
    var btn = el('button', 'dest-country-btn');
    btn.type = 'button';
    btn.dataset.key = keyOf(scope, entry);
    btn.innerHTML = '<span class="name">' + esc(text(entry)) + '</span>' +
                    '<span class="count badge bg-light text-secondary border">' + entry.cities.length + '</span>';
    btn.addEventListener('click', function () {
      current.scope = scope;
      current.entry = entry;
      renderCities();
    });
    return btn;
  }

  function renderCountries() {
    countryWrap.innerHTML = '';

    countryWrap.appendChild(scopeHeader('domestic'));
    if (!data.domestic.length) {
      countryWrap.appendChild(el('div', 'dest-empty', isEn ? 'No domestic city yet' : '暂未收录国内城市'));
    }
    data.domestic.forEach(function (e) { countryWrap.appendChild(countryButton('domestic', e)); });

    countryWrap.appendChild(scopeHeader('foreign'));
    if (!data.foreign.length) {
      countryWrap.appendChild(el('div', 'dest-empty', isEn ? 'No overseas city yet' : '暂未收录国外城市'));
    }
    data.foreign.forEach(function (e) { countryWrap.appendChild(countryButton('foreign', e)); });

    var first = data.domestic[0];
    current.scope = first ? 'domestic' : 'foreign';
    current.entry = first || data.foreign[0];
    renderCities();
  }

  function renderCities() {
    var entry = current.entry;
    cityWrap.innerHTML = '';
    if (!entry) return;

    cityTitle.textContent = text(entry) + (isEn ? ' · Pick a city' : ' · 选择城市');
    var activeKey = keyOf(current.scope, entry);
    Array.prototype.forEach.call(countryWrap.querySelectorAll('.dest-country-btn'), function (b) {
      b.classList.toggle('active', b.dataset.key === activeKey);
    });

    entry.cities.forEach(function (city) {
      var btn = el('button', 'dest-city-btn' + (city === current.city ? ' active' : ''));
      btn.type = 'button';
      btn.innerHTML = '<i class="bi bi-geo-alt me-1"></i>' + esc(city);
      btn.title = text(entry) + ' · ' + city;
      btn.addEventListener('click', function () {
        current.city = city;
        input.value = city;
        label.textContent = city + ' · ' + text(entry);
        label.classList.add('fw-semibold');
        if (errorEl) errorEl.classList.add('d-none');
        Array.prototype.forEach.call(cityWrap.querySelectorAll('.dest-city-btn'), function (n) {
          n.classList.remove('active');
        });
        btn.classList.add('active');
        var inst = bootstrap.Dropdown.getInstance(toggle);
        if (inst) inst.hide();
      });
      cityWrap.appendChild(btn);
    });

    cityWrap.appendChild(el('div', 'dest-group-hint w-100',
      isEn ? entry.cities.length + ' cities available' : '共 ' + entry.cities.length + ' 个可选城市'));
  }

  // 表单校验：未选城市时给出提示并展开菜单，而不是静默提交失败
  var form = document.getElementById('travelForm');
  if (form) {
    form.addEventListener('submit', function (ev) {
      if (!input.value) {
        ev.preventDefault();
        if (errorEl) errorEl.classList.remove('d-none');
        toggle.focus();
        var inst = bootstrap.Dropdown.getInstance(toggle);
        if (inst) inst.show();
      }
    });
  }

  renderCountries();
})();
