// 前端交互：表单校验、入场动画、概率条动效、LLM 思考指示
document.addEventListener('DOMContentLoaded', function () {

  // 兜底读取语言标记（base.html 已注入 window.LANG_EN）
  if (typeof window.LANG_EN === 'undefined') {
    window.LANG_EN = document.getElementById('global-data') &&
                     document.getElementById('global-data').dataset.langEn === 'true';
  }

  // 顶层 HTML 转义工具：供各 section 复用（行程、景点等动态渲染）
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  window.__escapeHtml = escapeHtml;

  // ===== 1. 入场动画（.reveal -> .in）=====
  var reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && reveals.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en, i) {
        if (en.isIntersecting) {
          // 错峰入场，制造层叠智能感
          var el = en.target;
          var delay = (el.dataset.delay !== undefined) ? el.dataset.delay : (i % 6) * 70;
          setTimeout(function () { el.classList.add('in'); }, delay);
          io.unobserve(el);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    // 兜底：直接显示
    reveals.forEach(function (el) { el.classList.add('in'); });
  }

  // ===== 2. 概率进度条动画（首次可见时填充）=====
  var bars = document.querySelectorAll('.prob-bar');
  if (bars.length && 'IntersectionObserver' in window) {
    var bo = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          var bar = en.target;
          var w = bar.getAttribute('style') || '';
          var m = w.match(/width:\s*([\d.]+)%/);
          if (m) {
            bar.style.width = '0%';
            requestAnimationFrame(function () {
              setTimeout(function () { bar.style.width = m[1] + '%'; }, 80);
            });
          }
          bo.unobserve(bar);
        }
      });
    }, { threshold: 0.3 });
    bars.forEach(function (el) { bo.observe(el); });
  }

  // ===== 3. 首页表单校验 =====
  var form = document.getElementById('travelForm');
  if (form) {
    form.addEventListener('submit', function (e) {
      var dest = form.elements['destination'].value.trim();
      var pref = form.elements['preference'].value;
      if (!dest) { e.preventDefault(); flash('请输入目的地'); return; }
      if (!pref) { e.preventDefault(); flash('请选择旅行偏好'); return; }
      var t = (form.elements['time_input'].value || '').trim();
      if (t) {
        var ok = /[\u4e00-\u9fa5]/.test(t) || /^\d{8}$/.test(t) || /^\d{12}$/.test(t);
        if (!ok) {
          e.preventDefault();
          flash('时间格式应为：季节文字 / 8位日期 / 12位日期时间（任意年份都会映射到 2024 年数据）');
        }
      }
    });
  }

  function flash(msg) {
    var box = document.getElementById('flashBox');
    if (!box) {
      box = document.createElement('div');
      box.id = 'flashBox';
      box.className = 'alert alert-warning mt-3';
      form.appendChild(box);
    }
    box.textContent = msg;
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // ===== 4. LLM 思考指示（QA 表单提交时）=====
  var qaForms = document.querySelectorAll('form[action="/qa"]');
  qaForms.forEach(function (f) {
    f.addEventListener('submit', function () {
      var chatBody = document.querySelector('.chat-body');
      if (!chatBody) return;
      // 已存在思考气泡则跳过
      if (chatBody.querySelector('.thinking-bubble')) return;
      var wrap = document.createElement('div');
      wrap.className = 'chat-bot mb-3 thinking-bubble';
      wrap.innerHTML =
        '<div class="bubble-bot">' +
          '<span class="thinking-dots"><span></span><span></span><span></span></span>' +
          '<span class="ms-2 small text-muted">' + (window.LANG_EN ? 'AI thinking…' : 'AI 正在思考…') + '</span>' +
        '</div>';
      chatBody.appendChild(wrap);
      chatBody.scrollTop = chatBody.scrollHeight;
    });
  });

  // ===== 5. 平滑滚动到答案区（提交后）=====
  // 服务器返回页面后，自动滚动到最新一条回答
  var lastBubble = document.querySelector('.chat-body .chat-bot:last-of-type');
  if (lastBubble) {
    lastBubble.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // ===== 6. 景观概率数字递增动画 =====
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var target = parseInt(el.dataset.count, 10);
    if (isNaN(target)) return;
    var cur = 0;
    var step = Math.max(1, Math.ceil(target / 30));
    var timer = setInterval(function () {
      cur += step;
      if (cur >= target) { cur = target; clearInterval(timer); }
      el.textContent = cur;
    }, 24);
  });

  // ===== 7. 跨境行程：异步加载分人群智能行程规划（LLM 慢部分后加载） =====
  var tokenInput = document.getElementById('itin-token');
  if (tokenInput && tokenInput.value) {
    bootstrapAsyncItinerary(tokenInput.value);
  }

  // ===== 8. 景点选择对话框 + 景点级精确预报异步加载 =====
  initSpotPicker();
  if (document.getElementById('spots-container')) {
    bootstrapAsyncSpots();
  }

  function initSpotPicker() {
    var hiddenInput = document.getElementById('selectedSpotsInput');
    if (!hiddenInput) return;

    // i18n 兜底（路由页可能未注入 SPOTS_I18N）
    var isEn = !!window.LANG_EN;
    var i18n = window.SPOTS_I18N || {
      modalTitle: isEn ? 'Select spots' : '选择景点',
      loading: isEn ? 'Loading spots…' : '景点列表加载中…',
      empty: isEn ? 'No spots recorded for this city yet' : '该城市暂未收录景点',
      selected: isEn ? 'Selected' : '已选',
      selectAll: isEn ? 'Select all' : '全选',
      selectNone: isEn ? 'Clear' : '清空',
    };

    // 内存中维护的已选景点列表 [{city,name,lat,lon,category,desc,weather_tip}]
    var selected = [];
    try { selected = JSON.parse(hiddenInput.value || '[]'); }
    catch (e) { selected = []; }

    function persist() {
      hiddenInput.value = JSON.stringify(selected);
      // 更新每个城市 pill 上的徽标数
      document.querySelectorAll('.spot-count').forEach(function (badge) {
        var city = badge.getAttribute('data-city');
        var n = selected.filter(function (s) { return s.city === city; }).length;
        badge.textContent = String(n);
        badge.classList.toggle('bg-secondary', n === 0);
        badge.classList.toggle('bg-primary', n > 0);
      });
    }
    persist();

    var modalEl = document.getElementById('spotModal');
    if (!modalEl) return;
    var modal = null;
    try { modal = new bootstrap.Modal(modalEl); } catch (e) { modal = null; }

    var modalCityEl = document.getElementById('spotModalCity');
    var loadingEl = document.getElementById('spotModalLoading');
    var emptyEl = document.getElementById('spotModalEmpty');
    var listEl = document.getElementById('spotModalList');
    var cbWrap = document.getElementById('spotCheckboxes');
    var countEl = document.getElementById('spotModalCount');
    var confirmBtn = document.getElementById('confirmSpots');
    var selectAllBtn = document.getElementById('spotSelectAll');
    var selectNoneBtn = document.getElementById('spotSelectNone');

    var currentCity = '';
    var currentSpots = []; // 该城最新拉取的景点列表

    function showModalState(state) {
      // state: 'loading' | 'empty' | 'list'
      loadingEl.classList.toggle('d-none', state !== 'loading');
      emptyEl.classList.toggle('d-none', state !== 'empty');
      listEl.classList.toggle('d-none', state !== 'list');
    }

    function renderCheckboxes() {
      cbWrap.innerHTML = '';
      if (!currentSpots.length) {
        showModalState('empty');
        return;
      }
      showModalState('list');
      currentSpots.forEach(function (s, idx) {
        var already = selected.some(function (x) {
          return x.city === s.city && x.name === s.name;
        });
        var col = document.createElement('div');
        col.className = 'col-md-6';
        col.innerHTML =
          '<div class="card border-0 shadow-sm rounded-3 h-100 spot-card' + (already ? ' border-primary' : '') + '">' +
            '<div class="card-body p-3">' +
              '<div class="form-check">' +
                '<input class="form-check-input spot-cb" type="checkbox" id="spot_' + idx + '" ' + (already ? 'checked' : '') + '>' +
                '<label class="form-check-label fw-semibold ms-1" for="spot_' + idx + '">' + escapeHtml(s.name) + '</label>' +
                '<span class="badge bg-light text-secondary ms-2 small">' + escapeHtml(s.category || '') + '</span>' +
              '</div>' +
              (s.desc ? '<div class="small text-muted mt-1">' + escapeHtml(s.desc) + '</div>' : '') +
              (s.weather_tip ? '<div class="small text-primary mt-1"><i class="bi bi-umbrella me-1"></i>' + escapeHtml(s.weather_tip) + '</div>' : '') +
              '<div class="small text-muted mt-1"><i class="bi bi-geo-alt me-1"></i>(' +
                (s.lat != null ? Number(s.lat).toFixed(3) : '?') + ', ' +
                (s.lon != null ? Number(s.lon).toFixed(3) : '?') + ')</div>' +
            '</div>' +
          '</div>';
        col.querySelector('.spot-cb').addEventListener('change', function () {
          updateCountFromCheckboxes();
        });
        cbWrap.appendChild(col);
      });
      updateCountFromCheckboxes();
    }

    function updateCountFromCheckboxes() {
      var n = cbWrap.querySelectorAll('.spot-cb:checked').length;
      countEl.textContent = String(n);
    }

    function getCurrentPicks() {
      var picks = [];
      cbWrap.querySelectorAll('.spot-cb').forEach(function (cb, idx) {
        if (cb.checked) {
          var s = currentSpots[idx];
          if (s) picks.push({
            city: s.city, name: s.name, lat: s.lat, lon: s.lon,
            category: s.category, desc: s.desc, weather_tip: s.weather_tip
          });
        }
      });
      return picks;
    }

    // 绑定『选景点』按钮点击事件
    document.querySelectorAll('.select-spots-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var city = btn.getAttribute('data-city');
        if (!city) return;
        currentCity = city;
        modalCityEl.textContent = i18n.modalTitle + ' · ' + city;
        showModalState('loading');
        countEl.textContent = '0';
        if (modal) modal.show();
        fetch('/spots/' + encodeURIComponent(city), { credentials: 'same-origin' })
          .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
          })
          .then(function (data) {
            if (!data || !data.ok) throw new Error('bad_response');
            currentSpots = data.spots || [];
            renderCheckboxes();
          })
          .catch(function (e) {
            console.warn('[spots] fetch failed:', e);
            currentSpots = [];
            showModalState('empty');
          });
      });
    });

    // 全选 / 清空
    if (selectAllBtn) {
      selectAllBtn.addEventListener('click', function () {
        cbWrap.querySelectorAll('.spot-cb').forEach(function (cb) { cb.checked = true; });
        updateCountFromCheckboxes();
      });
    }
    if (selectNoneBtn) {
      selectNoneBtn.addEventListener('click', function () {
        cbWrap.querySelectorAll('.spot-cb').forEach(function (cb) { cb.checked = false; });
        updateCountFromCheckboxes();
      });
    }

    // 确认按钮：合并选择
    if (confirmBtn) {
      confirmBtn.addEventListener('click', function () {
        // 移除该城市旧选择
        selected = selected.filter(function (s) { return s.city !== currentCity; });
        // 加入新选择
        var picks = getCurrentPicks();
        selected = selected.concat(picks);
        persist();
        if (modal) modal.hide();
      });
    }

    // 城市复选框变化时，未勾选的城市自动剔除其已选景点
    document.querySelectorAll('input[name="cities"]').forEach(function (cb) {
      cb.addEventListener('change', function () {
        if (!cb.checked) {
          var city = cb.value;
          selected = selected.filter(function (s) { return s.city !== city; });
          persist();
        }
      });
    });
  }

  function bootstrapAsyncSpots() {
    var isEn = !!window.LANG_EN;
    var i18n = window.SPOTS_I18N || {
      loading: isEn ? 'Fetching point-level daily forecasts by spot lat/lon (one grid call per spot, may take 5-15s)…'
                    : '正在按景点经纬度逐日获取精确预报（每个景点 1 次格点调用，可能 5-15 秒）…',
      loadingTip: isEn ? 'Falls back to city climate averages when API unreachable'
                       : 'API 不可达时自动降级为城市气候均值',
      error: isEn ? 'Spot forecast failed to load' : '景点预报加载失败',
      errorSession: isEn ? 'Session expired, please re-submit the route form'
                         : '会话已过期，请重新提交行程表单',
      retry: isEn ? 'Click to retry' : '点击重试',
      bestHours: isEn ? 'Best hours' : '最佳时段',
      weatherTip: isEn ? 'Spot weather tip' : '景点天气建议',
    };

    var tokenInput = document.getElementById('itin-token');
    var token = tokenInput && tokenInput.value ? tokenInput.value : '';
    if (!token) return;

    var container = document.getElementById('spots-container');
    var skeleton = document.getElementById('spots-skeleton');
    var errorEl = document.getElementById('spots-error-msg');
    var retryBtn = document.getElementById('spots-retry-btn');

    function showError(msg, allowRetry) {
      if (errorEl) {
        errorEl.textContent = msg;
        errorEl.classList.remove('d-none');
      }
      if (retryBtn) {
        retryBtn.classList.toggle('d-none', !allowRetry);
      }
    }

    function hideSkeleton() {
      if (skeleton) skeleton.remove();
      var loadCard = container && container.querySelector('.card[style*="dashed"]');
      if (loadCard) loadCard.remove();
    }

    function renderSpots(spots) {
      if (!spots || !spots.length) {
        if (container) {
          container.innerHTML = '<div class="alert alert-light border">' +
            (isEn ? 'No spot forecasts to show.' : '暂无景点预报数据。') + '</div>';
        }
        return;
      }
      // 清空容器并重新构建
      while (container.firstChild) container.removeChild(container.firstChild);
      var row = document.createElement('div');
      row.className = 'row g-3';

      // 数据来源 badge：实况=蓝、预报=绿、气候值=橙，与城市卡片同风格但更醒目
      function sourceBadgeHtml(d) {
        var src = (d.source || '').toString();
        var label, cls, icon;
        if (d.used_climate || src === '气候默认值' || src === 'Climate avg') {
          label = isEn ? 'Climate avg' : '气候值';
          cls = 'bg-warning text-dark';
          icon = 'bi-cloud-slash';
        } else if (src === '预报' || src === 'Forecast') {
          label = isEn ? 'Forecast' : '预报';
          cls = 'bg-success';
          icon = 'bi-graph-up-arrow';
        } else if (src === '实况' || src === 'Observation') {
          label = isEn ? 'Observation' : '实况';
          cls = 'bg-info text-dark';
          icon = 'bi-thermometer-half';
        } else {
          return '<b class="small text-muted ms-1">' + escapeHtml(src || '—') + '</b>';
        }
        return '<span class="badge rounded-pill ' + cls + ' ms-1" title="' +
               (isEn ? 'Data source' : '数据来源') + '">' +
               '<i class="bi ' + icon + ' me-1"></i>' + label + '</span>';
      }

      spots.forEach(function (sp) {
        var col = document.createElement('div');
        col.className = 'col-lg-6 reveal';
        var daysHtml = '';
        (sp.days || []).forEach(function (d) {
          var oorBadge = d.out_of_range
            ? '<span class="badge rounded-pill bg-danger text-white ms-1" title="' +
              (isEn ? 'Exceeds GOWFS 168h forecast range' : '已超出 GOWFS 168h 预报时效') + '">+' +
              escapeHtml(String(d.days_over || 0)) + 'd</span>'
            : '';
          daysHtml +=
            '<tr>' +
              '<td>' + escapeHtml(d.date || '') +
                '<div class="small text-muted">' + escapeHtml(d.weekday || '') + '</div>' +
                '<div class="mt-1">' + sourceBadgeHtml(d) + oorBadge + '</div>' +
              '</td>' +
              '<td class="text-center">' + (d.avg_tmp != null ? escapeHtml(String(d.avg_tmp)) + '℃' : '—') + '</td>' +
              '<td class="text-center">' + escapeHtml(String(d.total_pre != null ? d.total_pre : '—')) + 'mm</td>' +
              '<td class="text-center">' + (d.wind != null ? escapeHtml(String(d.wind)) : '—') + '</td>' +
              '<td class="text-center">' + (d.vis != null ? escapeHtml(String(d.vis)) : '—') + 'km</td>' +
              '<td class="text-center"><span class="comfort-badge comfort-' + escapeHtml(d.comfort || '') + '">' + escapeHtml(d.comfort || '—') + '</span></td>' +
              '<td>' + (d.best_hours ? '<span class="badge bg-success-subtle text-success-emphasis">' + escapeHtml(d.best_hours) + '</span>' : '—') + '</td>' +
            '</tr>';
        });
        col.innerHTML =
          '<div class="card border-0 shadow-sm rounded-4 h-100">' +
            '<div class="card-header bg-white border-0 py-3">' +
              '<span class="fw-bold"><i class="bi bi-pin-map-fill text-info me-1"></i>' + escapeHtml(sp.name || '') + '</span>' +
              '<span class="text-muted small ms-2">' + escapeHtml(sp.city || '') + (sp.category ? ' · ' + escapeHtml(sp.category) : '') + '</span>' +
              '<span class="badge bg-light text-dark float-end small">' +
                (sp.lat != null ? Number(sp.lat).toFixed(3) : '?') + ', ' +
                (sp.lon != null ? Number(sp.lon).toFixed(3) : '?') +
              '</span>' +
            '</div>' +
            '<div class="card-body">' +
              (sp.desc ? '<div class="small text-muted mb-2">' + escapeHtml(sp.desc) + '</div>' : '') +
              (sp.weather_tip ? '<div class="alert alert-info py-2 px-3 small mb-2"><i class="bi bi-umbrella me-1"></i><b>' + escapeHtml(i18n.weatherTip) + ':</b> ' + escapeHtml(sp.weather_tip) + '</div>' : '') +
              '<div class="table-responsive">' +
                '<table class="table table-sm table-bordered align-middle mb-0 forecast-table">' +
                  '<thead class="table-light"><tr>' +
                    '<th>' + (isEn ? 'Date' : '日期') + '</th>' +
                    '<th class="text-center">' + (isEn ? 'Temp℃' : '温度℃') + '</th>' +
                    '<th class="text-center">' + (isEn ? 'Precip' : '降水mm') + '</th>' +
                    '<th class="text-center">' + (isEn ? 'Wind' : '风力') + '</th>' +
                    '<th class="text-center">' + (isEn ? 'Vis' : '能见度') + '</th>' +
                    '<th class="text-center">' + (isEn ? 'Comfort' : '体感') + '</th>' +
                    '<th>' + escapeHtml(i18n.bestHours) + '</th>' +
                  '</tr></thead>' +
                  '<tbody>' + daysHtml + '</tbody>' +
                '</table>' +
              '</div>' +
            '</div>' +
          '</div>';
        row.appendChild(col);
      });
      container.appendChild(row);
      // 触发 reveal 动画
      var reveals = container.querySelectorAll('.reveal');
      if ('IntersectionObserver' in window && reveals.length) {
        var io = new IntersectionObserver(function (entries) {
          entries.forEach(function (en, i) {
            if (en.isIntersecting) {
              var delay = (i % 6) * 70;
              setTimeout(function () { en.target.classList.add('in'); }, delay);
              io.unobserve(en.target);
            }
          });
        }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
        reveals.forEach(function (el) { io.observe(el); });
      } else {
        reveals.forEach(function (el) { el.classList.add('in'); });
      }
    }

    function fetchAndRender(isRetry) {
      if (errorEl) errorEl.classList.add('d-none');
      if (retryBtn) retryBtn.classList.add('d-none');
      fetch('/route_spots_async?token=' + encodeURIComponent(token) +
            (isRetry ? '&_=' + Date.now() : ''),
            { credentials: 'same-origin' })
        .then(function (resp) {
          if (resp.status === 400) {
            showError(i18n.errorSession, false);
            hideSkeleton();
            return { ok: false };
          }
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          return resp.json();
        })
        .then(function (data) {
          if (!data || !data.ok) return;
          hideSkeleton();
          renderSpots(data.spots || []);
        })
        .catch(function (e) {
          console.warn('[spots async] error:', e);
          showError(i18n.error, true);
        });
    }

    fetchAndRender(false);
    if (retryBtn) {
      retryBtn.addEventListener('click', function () { fetchAndRender(true); });
    }
  }


  function bootstrapAsyncItinerary(token) {
    var i18n = window.ITIN_I18N || {
      loading: 'AI 正在规划详细时间线…',
      loadingFallback: '正在准备规则版精简建议兜底…',
      error: 'AI 规划失败，已切换为规则版精简建议',
      errorSession: '会话已过期，请重新提交行程表单',
      retry: '点击重试',
      refresh: '重新生成',
      srcLLM: 'AI 生成',
      srcRule: '规则建议',
      srcMixed: 'AI+规则',
      tipLLM: '建议由 AI 依据当日气象动态生成，时间点+景点+取舍更详尽',
      tipRule: 'AI 接口不可用，已使用规则建议（较为精简）',
      tipMixed: '部分城市 AI 生成，部分城市规则回退',
      roadRisk: '边境道路 / 铁路雨雾风险',
      roadRiskEn: 'Road/rail risk',
      notes: '提示',
    };

    var skeleton = document.getElementById('itin-skeleton');
    var errorEl = document.getElementById('itin-error-msg');
    var retryBtn = document.getElementById('itin-retry-btn');
    var refreshBtn = document.getElementById('itin-refresh-btn');
    var roadEl = document.getElementById('itin-road-risk');
    var crowdBadge = document.getElementById('itin-crowd-badge');
    var srcBadge = document.getElementById('itin-source-badge');
    var isEn = !!window.LANG_EN;

    function showError(msg, allowRetry) {
      if (errorEl) {
        errorEl.textContent = msg;
        errorEl.classList.remove('d-none');
      }
      if (retryBtn) {
        retryBtn.classList.toggle('d-none', !allowRetry);
        if (allowRetry) retryBtn.style.display = ''; else retryBtn.style.display = 'none';
      }
    }

    function hideSkeleton() {
      if (skeleton) skeleton.remove();
      // 移除顶部加载卡片
      var loadCard = document.querySelector('#itin-container > .card');
      if (loadCard) loadCard.remove();
    }

    function renderSource(source) {
      if (!srcBadge) return;
      var cls = '', tip = '', text = '', icon = '';
      if (source === 'llm') {
        cls = 'bg-success'; tip = i18n.tipLLM; text = i18n.srcLLM; icon = 'bi-stars';
      } else if (source === 'mixed') {
        cls = 'bg-warning text-dark'; tip = i18n.tipMixed; text = i18n.srcMixed; icon = 'bi-shuffle';
      } else {
        cls = 'bg-secondary'; tip = i18n.tipRule; text = i18n.srcRule; icon = 'bi-gear';
      }
      srcBadge.className = 'badge ' + cls;
      srcBadge.title = tip;
      srcBadge.innerHTML = '<i class="bi ' + icon + ' me-1"></i>' + text;
      srcBadge.classList.remove('d-none');
      srcBadge.style.display = '';
    }

    function renderRoadRisk(risks) {
      if (!roadEl) return;
      if (!risks || !risks.length) {
        roadEl.classList.add('d-none');
        roadEl.innerHTML = '';
        return;
      }
      roadEl.classList.remove('d-none');
      var label = isEn ? i18n.roadRiskEn : i18n.roadRisk;
      var html = '<b><i class="bi bi-exclamation-triangle me-1"></i>' + label + ':</b><ul class="mb-0 mt-1">';
      risks.forEach(function (r) {
        html += '<li><b>' + escapeHtml(r.city) + ':</b> ' + escapeHtml(r.text) + '</li>';
      });
      html += '</ul>';
      roadEl.innerHTML = html;
    }

    function renderCards(days) {
      if (!days || !days.length) return;
      var row = document.createElement('div');
      row.className = 'row g-3';
      days.forEach(function (d) {
        var col = document.createElement('div');
        col.className = 'col-lg-6 reveal';
        var slotsHtml = '';
        (d.schedule || []).forEach(function (s) {
          slotsHtml +=
            '<li class="it-slot d-flex">' +
              '<div class="it-time flex-shrink-0">' +
                '<span class="badge rounded-pill bg-primary-subtle text-primary-emphasis fw-semibold small">' +
                  escapeHtml(s.time || '') + '</span></div>' +
              '<div class="it-content flex-grow-1 ms-3">' +
                '<div class="fw-semibold">' + escapeHtml(s.title || '') + '</div>' +
                (s.detail ? '<div class="small text-muted mt-1">' + escapeHtml(s.detail) + '</div>' : '') +
              '</div></li>';
        });
        var notesHtml = d.notes
          ? ('<div class="small text-muted border-top pt-2 mt-1"><i class="bi bi-info-circle me-1"></i>' +
             escapeHtml(d.notes) + '</div>')
          : '';
        col.innerHTML =
          '<div class="card border-0 shadow-sm rounded-4 h-100">' +
            '<div class="card-header bg-white border-0 py-3">' +
              '<span class="fw-bold">' + escapeHtml(d.city) + '</span>' +
              '<span class="text-muted small ms-2">' + escapeHtml(d.date) + ' · ' + escapeHtml(d.weekday) + '</span>' +
              '<span class="badge bg-light text-dark float-end">' + escapeHtml(d.tag || '') + '</span>' +
            '</div>' +
            '<div class="card-body">' +
              '<ul class="list-unstyled itinerary-schedule mb-2">' + slotsHtml + '</ul>' + notesHtml +
            '</div></div>';
        row.appendChild(col);
      });
      var container = document.getElementById('itin-container');
      if (container) container.appendChild(row);
      // 让新加入的 .reveal 生效（重新观察）
      triggerReveals();
    }

    function triggerReveals() {
      var reveals = document.querySelectorAll('#itin-container .reveal');
      if ('IntersectionObserver' in window && reveals.length) {
        var io = new IntersectionObserver(function (entries) {
          entries.forEach(function (en, i) {
            if (en.isIntersecting) {
              var el = en.target;
              var delay = (i % 6) * 70;
              setTimeout(function () { el.classList.add('in'); }, delay);
              io.unobserve(el);
            }
          });
        }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
        reveals.forEach(function (el) { io.observe(el); });
      } else {
        reveals.forEach(function (el) { el.classList.add('in'); });
      }
    }

    function escapeHtml(s) {
      return String(s || '').replace(/[&<>"']/g, function (c) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
      });
    }

    function fetchAndRender(isRetry) {
      if (errorEl) errorEl.classList.add('d-none');
      if (retryBtn) retryBtn.classList.add('d-none');
      fetch('/route_itinerary_async?token=' + encodeURIComponent(token) + (isRetry ? '&_=' + Date.now() : ''),
            { credentials: 'same-origin' })
        .then(function (resp) {
          if (resp.status === 400) {
            showError(i18n.errorSession, false);
            hideSkeleton();
            return { ok: false };
          }
          if (!resp.ok) throw new Error('HTTP ' + resp.status);
          return resp.json();
        })
        .then(function (data) {
          if (!data || !data.ok) return;
          if (crowdBadge && data.crowd) crowdBadge.textContent = data.crowd;
          renderSource(data.source || 'rule');
          renderRoadRisk(data.road_risk || []);
          hideSkeleton();
          renderCards(data.days || []);
          if (refreshBtn) {
            refreshBtn.classList.remove('d-none');
            refreshBtn.style.display = '';
          }
        })
        .catch(function (e) {
          console.warn('[itin async] error:', e);
          showError(i18n.error, true);
        });
    }

    // 初始请求
    fetchAndRender(false);

    // 重试按钮
    if (retryBtn) {
      retryBtn.addEventListener('click', function () { fetchAndRender(true); });
    }
    // 重新生成按钮（结果已到后点击，强制服务端 itin_ready=false 用带 _=t 触发新请求并清缓存）——
    // 这里前端带 force=1，后端端点收到即清缓存重算
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        // 移除已渲染的卡片，恢复骨架 + 重拉
        var container = document.getElementById('itin-container');
        if (container) {
          // 清理已渲染的卡片（保留最外层容器 + 保留我们插入的骨架？简单起见：清空并重写骨架 + 加载条）
          while (container.firstChild) container.removeChild(container.firstChild);
        }
        rebuildLoadingUI(container, i18n);
        // 让 retry 按钮在新 UI 上重新绑定：因为我们刚重建了 loading UI，重新引用新的元素
        skeleton = document.getElementById('itin-skeleton');
        errorEl = document.getElementById('itin-error-msg');
        retryBtn = document.getElementById('itin-retry-btn');
        if (retryBtn) {
          retryBtn.addEventListener('click', function () { fetchAndRender(true); });
        }
        fetchAndRender(true);
      });
    }

    function rebuildLoadingUI(container, i) {
      if (!container) return;
      var dashCard = document.createElement('div');
      dashCard.className = 'card border-0 shadow-sm rounded-4 mb-3';
      dashCard.style.cssText = 'border:1px dashed #cfe2ff;';
      dashCard.innerHTML =
        '<div class="card-body py-4">' +
          '<div class="d-flex align-items-start gap-3">' +
            '<div class="spinner-grow text-primary flex-shrink-0" role="status"><span class="visually-hidden">Loading</span></div>' +
            '<div class="flex-grow-1">' +
              '<div class="fw-semibold text-primary">' + i.loading + '</div>' +
              '<div class="small text-muted mt-1">' +
                '<span class="thinking-dots-inline"><span></span><span></span><span></span></span>' +
                i.loadingFallback +
              '</div>' +
            '</div>' +
            '<button id="itin-retry-btn" type="button" class="btn btn-sm btn-outline-secondary d-none">' +
              '<i class="bi bi-arrow-repeat me-1"></i>' + i.retry +
            '</button>' +
          '</div>' +
          '<div id="itin-error-msg" class="alert alert-warning d-none mt-3 small mb-0"></div>' +
        '</div>';
      container.appendChild(dashCard);

      var sk = document.createElement('div');
      sk.id = 'itin-skeleton';
      sk.className = 'row g-3';
      var html = '';
      for (var k = 0; k < 4; k++) {
        html +=
          '<div class="col-lg-6">' +
            '<div class="card border-0 shadow-sm rounded-4 h-100">' +
              '<div class="card-header bg-white border-0 py-3 placeholder-glow">' +
                '<span class="placeholder col-3 fw-bold"></span>' +
                '<span class="placeholder col-4 small ms-2"></span>' +
                '<span class="placeholder col-2 float-end rounded-pill"></span>' +
              '</div><div class="card-body">';
        for (var j = 0; j < 4; j++) {
          html +=
            '<div class="mb-2 placeholder-glow">' +
              '<div class="d-flex gap-2 mb-1">' +
                '<span class="placeholder col-2 small rounded"></span>' +
                '<span class="placeholder col-6 fw-semibold rounded"></span>' +
              '</div>' +
              '<div class="placeholder col-12 small rounded"></div>' +
              '<div class="placeholder col-11 small rounded ms-1"></div>' +
            '</div>';
        }
        html +=
              '<div class="placeholder col-10 small rounded mt-2"></div>' +
            '</div></div></div>';
      }
      sk.innerHTML = html;
      container.appendChild(sk);
    }
  }
});
