# streamlit run app.py
# ngrok config add-authtoken [your authtoken]
# ngrok http 8501

import base64
import json
import os
import random
import re
from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup, NavigableString

# ==========================================
# 페이지 설정
# ==========================================
st.set_page_config(
    page_title="FCO4 CDS",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
    <style>
    div[data-testid="stToolbarActions"] { display: none !important; }
    button[data-testid="manage-app-button"] { display: none !important; }
    div[data-testid="stMainMenu"] { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 상수
# ==========================================
_PROFILE_URL   = st.secrets["PROFILE_URL"]
_SQUAD_API_URL = st.secrets["SQUAD_API_URL"]
_THUMB_BASE    = st.secrets["THUMB_BASE_URL"]

# 프로필 페이지에서 nexon_sn, char_id를 추출하는 정규식
_PROFILE_PATTERN = re.compile(
    r"SquadProfile\.SetSquadInfo\([^,]+,\s*[^,]+,\s*['\"](\d+)['\"],\s*['\"]([a-f0-9]+)['\"]\)"
)

# 대분류 → 포지션 목록. 매핑 없는 포지션은 FW로 처리
_POS_CATEGORY = {
    "GK": ["GK"],
    "DF": ["SW", "LB", "LCB", "CB", "RCB", "RB", "LWB", "RWB"],
    "MF": ["LDM", "CDM", "RDM", "LM", "LCM", "CM", "RCM", "RM", "LAM", "CAM", "RAM"],
    "FW": ["LW", "LF", "CF", "RF", "RW", "LS", "ST", "RS"],
}
# 역매핑: 포지션 → 대분류
_POS_CAT = {pos: cat for cat, positions in _POS_CATEGORY.items() for pos in positions}

# 포지션 → 필드 위치 (x: 좌우 0~100%, y: 아래부터 0~115)
_POS_XY = {
    "GK":  (50, 15),
    "SW":  (50, 25),
    "RCB": (62, 30), "CB":  (50, 30), "LCB": (38, 30),
    "RB":  (80, 35), "LB":  (20, 35),
    "RWB": (80, 40), "LWB": (20, 40),
    "RDM": (65, 50), "CDM": (50, 50), "LDM": (35, 50),
    "RCM": (65, 65), "CM":  (50, 65), "LCM": (35, 65),
    "RM":  (80, 70),  "LM":  (20, 70),
    "RAM": (70, 80), "CAM": (50, 80), "LAM": (30, 80),
    "RW":  (75, 90), "LW": (25, 90),
    "RF":  (65, 95), "CF":  (50, 95), "LF":  (35, 95),
    "RS": (65, 105), "ST":  (50, 105), "LS":  (35, 105),
}

# 스크래핑용 공통 요청 헤더
_HEADERS = {
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept-Language":  "ko-KR,ko;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

# 데이터센터 POST 스크래핑용 헤더
_SCRAPER_HEADERS = {
    "User-Agent":       "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer":          "https://fconline.nexon.com/datacenter",
}

# 능력치 키 목록 (필드 플레이어 / GK)
_FIELD_KEYS = ["스피드", "슛", "패스", "드리블", "수비", "피지컬"]
_GK_KEYS    = ["다이빙", "핸들링", "킥", "반응속도", "스피드", "위치선정"]

# ==========================================
# 스타일 (CSS)
# ==========================================
_CHART_CSS = """
.chart-player-name{font-size:13px;font-weight:700;color:#e0e0e0;padding:6px 0 10px;min-height:22px}
.chart-hint{color:#555;font-size:12px;text-align:center;padding:16px 20px;line-height:2}
.chart-loading{color:#888;font-size:12px;text-align:center;padding:60px 0;animation:blink 1.5s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
.chart-error{color:#ff6b6b;font-size:12px;text-align:center;padding:20px 0}
#chart-wrap{position:relative;height:280px;overflow:hidden}
#chart-meta{display:none;flex-direction:column;gap:6px;margin-bottom:10px}
#meta-period-block{display:flex;flex-direction:column;align-items:center;text-align:center;padding:8px 6px;background:#16161f;border-radius:6px}
#meta-prices{display:flex;gap:6px}
.meta-col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;text-align:center;padding:8px 6px;background:#16161f;border-radius:6px}
.meta-label{color:#555;font-size:9px;letter-spacing:0.5px;margin-bottom:6px;width:100%}
#meta-range{white-space:nowrap;color:#aaa}
.meta-price{font-size:15px;font-weight:700;line-height:1.3;color:#e0e0e0}
.meta-date{color:#555;font-size:9px;margin-top:2px}
.meta-high{color:#ff6b6b}
.meta-low{color:#5b9bd5}
.ability-hint{color:#555;font-size:12px;text-align:center;padding:16px 20px;line-height:2}
#ability-loading{padding:16px 0}
.ab-header{display:flex;gap:8px;padding:0 0 8px}
.ab-img-wrap{position:relative;aspect-ratio:1;align-self:stretch;flex-shrink:0;max-height:90px}
.ab-player-img{width:100%;height:100%;object-fit:contain;object-position:bottom}
.ab-enhance{position:absolute;bottom:0;right:0;width:18px;height:11px;font-size:7px;font-weight:700;line-height:11px;text-align:center;border-radius:0;z-index:5}
.ab-info-wrap{flex:1;display:flex;flex-direction:column;gap:4px;min-width:0;justify-content:center}
.ab-row{display:flex;align-items:center;flex-wrap:wrap;gap:3px}
.ab-season-icon{width:18px;height:14px;object-fit:contain;flex-shrink:0}
.ab-name{font-size:12px;font-weight:700;color:#e0e0e0}
.ab-pos-chip{display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:#1e1e2a;border-radius:3px}
.ab-pos{font-size:8px;color:#888;font-weight:700;width:16px;text-align:left;flex-shrink:0}
.ab-ovr{font-size:10px;color:#e0e0e0;font-weight:700}
.ab-row3{font-size:11px;color:#666;line-height:1.8;white-space:nowrap;overflow:hidden}
.ab-tc-wrap{display:flex;flex-direction:row;flex-wrap:wrap;gap:12px;align-items:center;justify-content:center;flex-shrink:0;padding:0 2px}
.ab-tc-item{position:relative;cursor:default}
.ab-tc-item img{width:28px;height:28px;object-fit:contain;display:block}
.ab-tc-tooltip{display:none;position:absolute;top:calc(100% + 5px);right:0;background:#0d0d14;color:#ccc;font-size:9px;white-space:nowrap;padding:4px 8px;border-radius:3px;border:1px solid #2a2a35;z-index:99;pointer-events:none;line-height:1.8}
.ab-tc-tooltip b{color:#e0e0e0;display:block;margin-bottom:2px}
.ab-tc-item:hover .ab-tc-tooltip{display:block}
.ab-rows-top{display:flex;align-items:center;gap:6px}
.ab-rows-left{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.ab-tc-inline{display:none}
.ab-tc-column{display:flex;align-self:center}
@media(max-width:600px){
  .ab-tc-item img{width:18px;height:18px}
  .ab-tc-inline{display:flex}
  .ab-tc-column{display:none}
  .ab-row3{white-space:nowrap;font-size:clamp(7px,2.8vw,9px);overflow:hidden}
}
.ab-traits{display:flex;flex-wrap:wrap;gap:4px;padding:2px 0;align-items:center}
.ab-trait-item{position:relative;cursor:default}
.ab-trait-item img{width:26px;height:26px;object-fit:contain;border-radius:3px;display:block}
.ab-trait-tooltip{display:none;position:absolute;bottom:calc(100% + 5px);left:50%;transform:translateX(-50%);background:#0d0d14;color:#ccc;font-size:9px;white-space:nowrap;padding:3px 7px;border-radius:3px;border:1px solid #2a2a35;z-index:99;pointer-events:none}
.ab-trait-item:hover .ab-trait-tooltip{display:block}
.ability-grid{display:flex;flex-direction:column;gap:5px;padding:4px 0 8px}
.ability-row{display:flex;align-items:center;gap:6px}
.ab-label{font-size:9px;color:#777;width:36px;flex-shrink:0;text-align:right}
.ab-bar-wrap{flex:1;height:5px;background:#1e1e2a;border-radius:3px;overflow:hidden}
.ab-bar{height:100%;border-radius:3px;transition:width 0.4s ease}
.ab-val{font-size:11px;font-weight:700;color:#e0e0e0;width:22px;text-align:right}
.ti-row{display:flex;gap:6px;align-items:stretch}
.ti-stat-block{flex:1;background:#16161f;border-radius:6px;padding:8px 10px;display:flex;flex-direction:column;align-items:center;text-align:center}
.ti-stat-label{color:#555;font-size:9px;letter-spacing:0.5px;margin-bottom:6px;width:100%}
.ti-stat-value{font-size:14px;font-weight:700;color:#e0e0e0}
.ti-stat-sub{font-size:11px;color:#666;margin-top:2px}
.ti-chart-block{flex:2;align-items:stretch;min-width:0}
#ti-abilities{width:100%;margin-top:2px}
#ti-abilities .ability-row{gap:4px}
#ti-abilities .ab-label{width:28px;font-size:8px;font-weight:700}
#ti-abilities .ab-val{font-size:9px;width:16px}
@media(max-width:600px){
  .ti-row{flex-wrap:wrap}
  .ti-chart-block{flex:0 0 100%}
}
.pa-row{display:flex;align-items:stretch;gap:12px;padding:4px 0}
.ti-squad-total{flex:1;display:flex;flex-direction:column;background:#16161f;border-radius:6px;padding:8px 10px}
.pa-stat-block{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;width:100%}
.pa-stat-block+.pa-stat-block{border-top:1px solid #2a2a35}
.ti-squad-label{font-size:9px;color:#555;letter-spacing:0.5px}
.ti-squad-num{font-size:16px;font-weight:700;color:#e0e0e0}
.ti-donut-block{padding:6px 4px 8px}
.ti-donut-wrap{position:relative;width:150px;height:150px;margin:0 auto}
.ti-donut-center{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;pointer-events:none;width:65%}
.ti-donut-value{font-size:11px;font-weight:700;color:#e0e0e0;line-height:1.4;white-space:nowrap}
.ti-donut-cat{font-size:10px;font-weight:700;line-height:1.4;white-space:nowrap;min-height:14px}
"""

# ==========================================
# 클라이언트 스크립트 (JS)
# ==========================================
_CHART_JS = r"""
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
let _ch = null;

function enClass(b) {
  b = +b;
  if (b === 1)  return 'en1';
  if (b <= 4)   return 'en2';
  if (b <= 7)   return 'en5';
  if (b <= 10)  return 'en8';
  if (b <= 13)  return 'en11';
  return '';
}

const _POS_CAT_COLOR = (pos => {
  const GK = ['GK'];
  const DF = ['SW','LB','LCB','CB','RCB','RB','LWB','RWB'];
  const MF = ['LDM','CDM','RDM','LM','LCM','CM','RCM','RM','LAM','CAM','RAM'];
  if (GK.includes(pos)) return '#f2be57';
  if (DF.includes(pos)) return '#2b7def';
  if (MF.includes(pos)) return '#00d28b';
  return '#f6425f'; // FW default
});

function resizeIframe() {
  if (!_resizeEnabled) return;
  const h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
}
window.addEventListener('load', resizeIframe);
if (typeof ResizeObserver !== 'undefined') {
  new ResizeObserver(resizeIframe).observe(document.querySelector('.layout') || document.body);
}

function clearSelection() {
  document.querySelectorAll('.pcard,.scard').forEach(c => c.classList.remove('selected'));
  const hint = document.getElementById('ability-hint');
  const body = document.getElementById('ability-body');
  if (hint) hint.style.display = ABILITY_LOADED ? '' : 'none';
  if (body) body.style.display = 'none';
  toggle(PRICE_LOADED, false, false);
  if (typeof window._donutReset === 'function') window._donutReset();
}

document.querySelectorAll('.pcard,.scard').forEach(el => {
  el.addEventListener('click', e => {
    e.stopPropagation();
    const {spid, buildup, name, price} = el.dataset;
    const wasSelected = el.classList.contains('selected');
    document.querySelectorAll('.pcard,.scard').forEach(c => c.classList.remove('selected'));
    if (wasSelected) {
      clearSelection();
    } else {
      el.classList.add('selected');
      if (ABILITY_LOADED) showAbility(spid, buildup);
      if (PRICE_LOADED) showChart(spid, buildup, name, price);
      const cat = el.dataset.cat || null;
      if (cat && typeof window._donutHighlight === 'function') window._donutHighlight(cat);
    }
  });
});


function showAbility(spid, buildup) {
  const key  = spid + '_' + buildup;
  const ab   = (typeof ABILITY_DATA !== 'undefined' && ABILITY_DATA[key]) || {};
  const stats = ab.stats || {};
  const hint  = document.getElementById('ability-hint');
  const body  = document.getElementById('ability-body');
  if (!Object.keys(stats).length) {
    if (hint) hint.style.display = '';
    if (body) body.style.display = 'none';
    return;
  }

  const info          = ab.info           || {};
  const traits        = ab.traits         || [];
  const prefPositions = ab.pref_positions || [];

  // 카드에서 시즌 아이콘 가져오기
  const card = document.querySelector(
    '.pcard[data-spid="' + spid + '"][data-buildup="' + buildup + '"],' +
    '.scard[data-spid="' + spid + '"][data-buildup="' + buildup + '"]'
  );
  const seasonIcon = card ? card.dataset.seasonIcon : '';
  const playerName = card ? card.dataset.name       : '';

  // Row 3 항목 조합
  const skillHtml = info.skill
    ? '<span style="letter-spacing:0px">' + info.skill.replace(/★/g, '<span style="color:#fc0">★</span>') + '</span>'
    : '';
  const row3 = [info.birth, info.height, info.weight, info.physical, skillHtml, info.foot]
    .filter(v => v && v.trim()).join('&nbsp; | &nbsp;');

  const enCls = +buildup > 0 ? enClass(buildup) : '';
  const tcList = (typeof TC_DATA !== 'undefined' && TC_DATA[key]) || [];
  const tcHtml = tcList.map(t => {
    const skillLines = t.skill ? t.skill.split('|').filter(s => s.trim()) : [];
    const tip = '<b>' + t.name + '</b>' + (skillLines.length ? skillLines.join('<br>') : '');
    return '<span class="ab-tc-item"><img src="' + t.img + '" alt="' + t.name + '">'
      + '<span class="ab-tc-tooltip">' + tip + '</span></span>';
  }).join('');
  let h = '<div class="ab-header">';
  h += '<div class="ab-img-wrap">';
  const thumbUrl = (typeof THUMB_DATA !== 'undefined' && THUMB_DATA[key]) || ab.img || '';
  h += '<img class="ab-player-img" src="' + thumbUrl + '" onerror="this.style.display=\'none\'">';
  if (enCls) h += '<div class="ab-enhance ' + enCls + '">' + buildup + '</div>';
  h += '</div>';
  h += '<div class="ab-info-wrap">';

  // 1·2행 wrapper (모바일에서 tc 이미지를 우측에 중앙 정렬)
  h += '<div class="ab-rows-top">';
  h += '<div class="ab-rows-left">';

  // 1행: 시즌 아이콘 + 선수명
  h += '<div class="ab-row">';
  if (seasonIcon) h += '<img class="ab-season-icon" src="' + seasonIcon + '" onerror="this.style.display=\'none\'">';
  h += '<span class="ab-name">' + playerName + '</span>';
  h += '</div>';

  // 2행: 선호 포지션 + OVR (복수 가능)
  if (prefPositions.length) {
    h += '<div class="ab-row">';
    h += prefPositions.map(p => {
      const col = _POS_CAT_COLOR(p.pos);
      return '<span class="ab-pos-chip" style="background:' + col + '22;border:1px solid ' + col + '55">'
        + '<span class="ab-pos" style="color:' + col + '">' + p.pos + '</span>'
        + '<span class="ab-ovr">' + p.ovr + '</span></span>';
    }).join('');
    h += '</div>';
  }

  h += '</div>'; // ab-rows-left
  if (tcList.length) h += '<div class="ab-tc-wrap ab-tc-inline">' + tcHtml + '</div>';
  h += '</div>'; // ab-rows-top

  // 3행: 생년월일 | 키 | 몸무게 | 체형 | 개인기 | 주발
  if (row3) h += '<div class="ab-row ab-row3">' + row3 + '</div>';

  // 4행: 특성
  if (traits.length) {
    h += '<div class="ab-traits">';
    h += traits.map(t =>
      '<span class="ab-trait-item">'
      + '<img src="' + t.img + '" alt="' + t.desc + '">'
      + '<span class="ab-trait-tooltip">' + t.desc + '</span>'
      + '</span>'
    ).join('');
    h += '</div>';
  }

  h += '</div>'; // ab-info-wrap

  // 우측 열: 팀컬러 이미지 (데스크탑 전용)
  if (tcList.length) {
    h += '<div class="ab-tc-wrap ab-tc-column">' + tcHtml + '</div>';
  }

  h += '</div>'; // ab-header

  // 주요 능력치 막대
  h += '<div class="ability-grid">';
  h += Object.entries(stats).map(([k, v]) => {
    const pct = (Math.min(v, 170) / 170 * 100).toFixed(1);
    const col = v >= 160 ? '#11cdc6' : v >= 150 ? '#ffa800' : v >= 140 ? '#c99b00' : v >= 130 ? '#e12900' : v >= 120 ? '#cf39d0' : v >= 110 ? '#b33bfe' : v >= 100 ? '#6e3bfe' : v >= 90 ? '#175dde' : v >= 80 ? '#2194d6' : v >= 70 ? '#1f2d37' : '#8f96a0';
    return '<div class="ability-row">'
      + '<span class="ab-label">' + k + '</span>'
      + '<div class="ab-bar-wrap"><div class="ab-bar" style="width:' + pct + '%;background:' + col + '"></div></div>'
      + '<span class="ab-val" style="color:' + col + '">' + v + '</span></div>';
  }).join('');
  h += '</div>';

  body.innerHTML = h;
  if (hint) hint.style.display = 'none';
  body.style.display = '';
  setTimeout(resizeIframe, 50);
  setTimeout(resizeIframe, 400);
}

function toggle(hint, err, chart) {
  document.getElementById('chart-hint').style.display  = hint  ? '' : 'none';
  document.getElementById('chart-error').style.display = err   ? '' : 'none';
  document.getElementById('chart-meta').style.display  = chart ? 'flex' : 'none';
  if (chart) {
    // chart-wrap을 보이기 전에 충분한 높이를 먼저 확보
    _resizeEnabled = false;
    window.parent.postMessage({type: 'streamlit:setFrameHeight', height: _SAFE_H}, '*');
    setTimeout(() => {
      document.getElementById('chart-wrap').style.display = '';
      setTimeout(() => { _resizeEnabled = true; resizeIframe(); }, 350);
    }, 100);
  } else {
    document.getElementById('chart-wrap').style.display = 'none';
    _resizeEnabled = true;
    setTimeout(resizeIframe, 50);
    setTimeout(resizeIframe, 400);
  }
}

function updateMeta(records, squadPrice) {
  let maxI = 0, minI = 0;
  records.forEach((r, i) => {
    if (r.value > records[maxI].value) maxI = i;
    if (r.value < records[minI].value) minI = i;
  });
  const startDate = records[0].date, endDate = records[records.length - 1].date;
  document.getElementById('meta-range').textContent = startDate + '\n~ ' + endDate;
  const days = Math.round((new Date(endDate) - new Date(startDate)) / 86400000) + 1;
  document.getElementById('meta-period-days').textContent = '(' + days + '일)';
  document.getElementById('meta-current-price').textContent = bp(squadPrice);
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('meta-current-date').textContent  = '(' + today + ')';
  document.getElementById('meta-high-price').textContent = bp(records[maxI].value);
  document.getElementById('meta-high-date').textContent  = '(' + records[maxI].date + ')';
  document.getElementById('meta-low-price').textContent  = bp(records[minI].value);
  document.getElementById('meta-low-date').textContent   = '(' + records[minI].date + ')';
}

function showChart(spid, buildup, name, price) {
  const key     = spid + '_' + buildup;
  const records = (typeof PRICE_DATA !== 'undefined' && PRICE_DATA[key]) || [];
  if (!records.length) {
    document.getElementById('chart-error').textContent = '❌ 시세 데이터가 없습니다.';
    toggle(false, true, false);
    return;
  }
  updateMeta(records, +price);
  draw(records.map(r => r.date), records.map(r => r.value), name, +buildup);
  toggle(false, false, true);
}

function bp(v) {
  const gyeong = Math.floor(v / 1e16);
  const jo  = Math.floor((v % 1e16) / 1e12);
  const eok = Math.floor((v % 1e12) / 1e8);
  const man = Math.floor((v % 1e8)  / 1e4);
  const p = [];
  if (gyeong) p.push(gyeong + '경');
  if (jo)     p.push(jo     + '조');
  if (eok)    p.push(eok    + '억');
  if (man)    p.push(man    + '만');
  return p.slice(0, 2).join(' ') || '0';
}

function draw(labels, data, name, buildup) {
  const ctx = document.getElementById('priceChart').getContext('2d');
  if (_ch) _ch.destroy();
  _ch = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: name + (buildup ? '  ' + buildup + '강' : ''),
        data,
        borderColor: '#07f468',
        backgroundColor: 'rgba(7,244,104,0.07)',
        borderWidth: 1.5, pointRadius: 2, pointHoverRadius: 4, tension: 0.3, fill: true
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: {duration: 300, onComplete: resizeIframe},
      scales: {
        x: {ticks: {color: '#777', maxRotation: 40, font: {size: 9}, autoSkip: false,
              callback: function(val, idx, ticks) {
                const ym = this.getLabelForValue(val).slice(0, 7);
                if (idx === 0) return ym;
                const prevYm = this.getLabelForValue(ticks[idx-1].value).slice(0, 7);
                return ym !== prevYm ? ym : '';
              }}, grid: {display: false}},
        y: {ticks: {color: '#777', callback: v => bp(v), font: {size: 9}}, grid: {display: false}}
      },
      plugins: {
        legend: {display: false},
        tooltip: {callbacks: {label: c => ' ' + bp(c.parsed.y)}}
      }
    }
  });
}

// 구단 가치 도넛 차트
(function() {
  const canv = document.getElementById('ti-donut');
  if (!canv || typeof TI_VALUE_DATA === 'undefined') return;
  const catColors  = {GK: '#f2be57', FW: '#f6425f', MF: '#00d28b', DF: '#2b7def'};
  const labels     = ['GK', 'FW', 'MF', 'DF'].filter(c => TI_VALUE_DATA[c] > 0);
  const values     = labels.map(c => TI_VALUE_DATA[c]);
  const bgColors   = labels.map(c => catColors[c]);
  const dimColors  = bgColors.map(c => c + '40');
  const total      = values.reduce((s, v) => s + v, 0);
  function bpK(v) {
    const gyeong = Math.floor(v / 1e16);
    const jo  = Math.floor((v % 1e16) / 1e12);
    const eok = Math.floor((v % 1e12) / 1e8);
    const man = Math.floor((v % 1e8)  / 1e4);
    const p = [];
    if (gyeong) p.push(gyeong + '경');
    if (jo)     p.push(jo     + '조');
    if (eok)    p.push(eok    + '억');
    if (man)    p.push(man    + '만');
    return p.slice(0, 2).join(' ') || '0';
  }
  const exclValues = labels.map(c => (typeof TI_VALUE_DATA_EXCL !== 'undefined' ? TI_VALUE_DATA_EXCL[c] : 0) || 0);
  const wrap       = canv.closest('.ti-donut-wrap');
  const valueEl    = wrap ? wrap.querySelector('.ti-donut-value') : null;
  const catEl      = document.getElementById('ti-donut-cat');
  const posHintEl  = document.getElementById('pa-hint');
  const posLabelEl = document.getElementById('pa-pos-label');
  const posValueEl = document.getElementById('pa-pos-value');
  const posSubEl   = document.getElementById('pa-pos-sub');
  const defText    = valueEl ? valueEl.textContent : '';
  let _selectedCat = null;

  function _applyState(cat) {
    const ds = tiDonut.data.datasets[0];
    const i  = cat ? labels.indexOf(cat) : -1;
    if (i !== -1) {
      if (posHintEl)  posHintEl.style.display = 'none';
      if (valueEl)    valueEl.textContent = (values[i] / total * 100).toFixed(2) + '%';
      if (catEl)      { catEl.style.color = bgColors[i]; catEl.textContent = labels[i]; }
      ds.backgroundColor = bgColors.map((c, j) => j === i ? c : dimColors[j]);
      if (posLabelEl) { posLabelEl.style.display = ''; posLabelEl.textContent = labels[i]; posLabelEl.style.color = bgColors[i]; }
      if (posValueEl) { posValueEl.style.display = ''; posValueEl.textContent = bpK(values[i]); }
      if (posSubEl)   { posSubEl.style.display   = ''; posSubEl.textContent   = '(' + bpK(exclValues[i]) + ')'; }
    } else {
      if (posHintEl)  posHintEl.style.display = '';
      if (valueEl)    valueEl.textContent = defText;
      if (catEl)      { catEl.textContent = ''; }
      ds.backgroundColor = bgColors;
      if (posLabelEl) posLabelEl.style.display = 'none';
      if (posValueEl) posValueEl.style.display = 'none';
      if (posSubEl)   posSubEl.style.display   = 'none';
    }
    tiDonut.update('none');
  }

  const tiDonut = new Chart(canv, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: bgColors,
        hoverBackgroundColor: bgColors,
        borderWidth: 2,
        borderColor: '#111318',
        hoverBorderColor: '#111318',
        hoverOffset: 10,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      layout: {padding: 10},
      plugins: {
        legend: {display: false},
        tooltip: {enabled: false}
      },
      onHover: (evt, els) => {
        if (!valueEl || !catEl) return;
        if (els.length) {
          const i  = els[0].index;
          const ds = tiDonut.data.datasets[0];
          if (valueEl)    valueEl.textContent = (values[i] / total * 100).toFixed(2) + '%';
          if (catEl)      { catEl.style.color = bgColors[i]; catEl.textContent = labels[i]; }
          ds.backgroundColor = bgColors.map((c, j) => j === i ? c : dimColors[j]);
          if (posHintEl)  posHintEl.style.display = 'none';
          if (posLabelEl) { posLabelEl.style.display = ''; posLabelEl.textContent = labels[i]; posLabelEl.style.color = bgColors[i]; }
          if (posValueEl) { posValueEl.style.display = ''; posValueEl.textContent = bpK(values[i]); }
          if (posSubEl)   { posSubEl.style.display   = ''; posSubEl.textContent   = '(' + bpK(exclValues[i]) + ')'; }
          tiDonut.update('none');
        } else {
          _applyState(_selectedCat);
        }
      },
      animation: {duration: 500}
    }
  });

  canv.addEventListener('mouseleave', () => _applyState(_selectedCat));

  window._donutHighlight = function(cat) {
    _selectedCat = labels.includes(cat) ? cat : null;
    _applyState(_selectedCat);
  };
  window._donutReset = function() {
    _selectedCat = null;
    _applyState(null);
  };
})();

function updateTeamInfo() {
  const container = document.getElementById('ti-abilities');
  if (!container) return;
  const groups = {FW: [], MF: [], DF: []};
  document.querySelectorAll('.pcard').forEach(card => {
    const ovr = +card.dataset.ovr;
    if (!ovr) return;
    let cat = null;
    if (card.classList.contains('cat-fw'))      cat = 'FW';
    else if (card.classList.contains('cat-mf')) cat = 'MF';
    else if (card.classList.contains('cat-df')) cat = 'DF';
    if (cat) groups[cat].push(ovr);
  });
  const catColors = {FW: '#f6425f', MF: '#00d28b', DF: '#2b7def'};
  let h = '';
  for (const cat of ['FW', 'MF', 'DF']) {
    const list = groups[cat];
    if (!list.length) continue;
    const avg = Math.round(list.reduce((s, v) => s + v, 0) / list.length);
    const col = catColors[cat];
    const pct = (Math.min(avg, 170) / 170 * 100).toFixed(1);
    h += '<div class="ability-row">'
      + '<span class="ab-label" style="color:' + col + '">' + cat + '</span>'
      + '<div class="ab-bar-wrap"><div class="ab-bar" style="width:' + pct + '%;background:' + col + '"></div></div>'
      + '<span class="ab-val" style="color:' + col + '">' + avg + '</span></div>';
  }
  container.innerHTML = h;
}
updateTeamInfo();
</script>
"""


# ==========================================
# 애셋
# ==========================================
def _b64(path: str, mime: str) -> str:
    """파일을 읽어 base64 data URI로 반환 (iframe 내 로컬 파일 참조 불가 우회)."""
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


# 이미지·폰트 base64 임베딩
_BG_SVG_URL      = _b64("img/bg_squad.svg",               "image/svg+xml")
_BG_PLT_URL      = _b64("img/bg_plt.png",                 "image/png")
_FONT_BOLD_WOFF2 = _b64("font/FCOAllSans-Bold.woff2",     "font/woff2")
_FONT_BOLD_WOFF  = _b64("font/FCOAllSans-Bold.woff",      "font/woff")
_FONT_MED_WOFF2  = _b64("font/FCOAllSans-Medium.woff2",   "font/woff2")
_FONT_MED_WOFF   = _b64("font/FCOAllSans-Medium.woff",    "font/woff")
_FONT_NEXON_B    = _b64("font/NEXONFOOTBALLGOTHICB.TTF",  "font/ttf")


# ==========================================
# 데이터 수집
# ==========================================
@st.cache_data(show_spinner=False)
def load_spposition() -> dict[str, int]:
    """포지션 정렬 순서 로드 (data/meta_spposition.csv)."""
    df = pd.read_csv("data/meta_spposition.csv")
    return dict(zip(df["role"], df["ID"]))


@st.cache_data(show_spinner=False)
def load_season_meta() -> dict[int, str]:
    """시즌 ID → 시즌 아이콘 URL 매핑 로드 (data/meta_seasonid.csv)."""
    df = pd.read_csv("data/meta_seasonid.csv")
    return dict(zip(df["ID"].astype(int), df["season_IMG"]))


@st.cache_data(ttl=300, show_spinner=False)
def get_squad_data(nickname: str) -> tuple[pd.DataFrame | None, pd.DataFrame | None, str | None]:
    """
    구단주명으로 현재 대표 스쿼드를 조회한다.

    Returns:
        df_st      : 선발 선수 DataFrame
        df_sub     : 후보 선수 DataFrame
        squad_name : 스쿼드명 문자열
        실패 시 (None, None, None)
    """
    session = requests.Session()

    # 1) 프로필 페이지 스크래핑 → nexon_sn, char_id 획득
    resp = session.get(_PROFILE_URL, params={"strCharacterName": nickname}, headers=_HEADERS)
    m = _PROFILE_PATTERN.search(resp.text)
    if not m:
        return None, None, None
    nexon_sn, char_id = m.group(1), m.group(2)

    # 2) 스쿼드 API 호출
    resp = session.get(
        _SQUAD_API_URL,
        params={"strTeamType": 1, "n1Type": 1, "n8NexonSN": nexon_sn, "strCharacterID": char_id},
        headers=_HEADERS,
    )
    data = resp.json()
    if not data.get("players"):
        return None, None, None

    season_meta = load_season_meta()

    # 3) 선수 데이터 파싱 (state==0: 선발, 그 외: 후보)
    starters, subs = [], []
    for p in data["players"]:
        role      = p.get("role", "").upper()
        price     = int(str(p.get("price", "0")).replace(",", ""))
        spid      = p.get("spid", 0)
        season_id = int(str(spid)[:3]) if spid else 0  # spid 앞 3자리 = 시즌 ID

        tc  = p.get("teamColor") or {}
        tc1 = tc.get("teamColor1") or {}
        tc2 = tc.get("teamColor2") or {}
        tc3 = tc.get("teamColor3") or {}
        record = {
            "포지션":     role,
            "대분류":     _POS_CAT.get(role, "FW"),
            "이름":       p.get("name"),
            "OVR":        p.get("ovr"),
            "강화":       p.get("buildUp"),
            "급여":       p.get("pay"),
            "가격(BP)":   price,
            "spid":       spid,
            "이미지":     _thumb_url(p.get("thumb_custom", "")),
            "thumb_url":  _thumb_url(p.get("thumb", "")),
            "시즌아이콘": season_meta.get(season_id, ""),
            "tc_id":    int(tc1.get("id") or 0),
            "tc_lv":    int(tc1.get("lv") or 0),
            "tc_en_id": int(tc3.get("id") or 0),
            "tc_en_lv": int(tc3.get("lv") or 0),
            "tc_ft_id": int(tc2.get("id") or 0),
            "tc1_name": tc1.get("name", ""), "tc1_skill": tc1.get("skill", ""), "tc1_img": tc1.get("image", ""),
            "tc2_name": tc2.get("name", ""), "tc2_skill": tc2.get("skill", ""), "tc2_img": tc2.get("image", ""),
            "tc3_name": tc3.get("name", ""), "tc3_skill": tc3.get("skill", ""), "tc3_img": tc3.get("image", ""),
        }
        (starters if p.get("state") == 0 else subs).append(record)

    # 4) 포지션 순서로 정렬
    pos_order = load_spposition()
    starters.sort(key=lambda r: pos_order.get(r["포지션"], -1), reverse=True)
    subs.sort(key=lambda r: pos_order.get(r["포지션"], -1), reverse=True)

    return pd.DataFrame(starters), pd.DataFrame(subs), data.get("squadName")


def _resolve_dates(times: list[str]) -> list[str]:
    """'MM.DD' 문자열 목록을 'YYYY-MM-DD'로 변환. 월이 역순으로 증가하면 연도를 내린다."""
    parsed = [tuple(map(int, t.split("."))) for t in times]
    yr     = datetime.now().year
    prev   = parsed[-1][0] if parsed else 1
    dates  = [""] * len(parsed)
    for i in range(len(parsed) - 1, -1, -1):
        m, d = parsed[i]
        if m > prev:
            yr -= 1
        dates[i] = f"{yr}-{m:02d}-{d:02d}"
        prev = m
    return dates


def _fetch_price_one(spid: int, buildup: int) -> list[dict]:
    """단일 선수 시세 데이터를 Python requests로 서버사이드 수집."""
    try:
        resp = requests.post(
            "https://fconline.nexon.com/datacenter/PlayerPriceGraph",
            data={"spid": spid, "n1strong": buildup, "rd": random.random()},
            headers=_SCRAPER_HEADERS,
            timeout=10,
        )
        text = resp.text
        tM = re.search(r'"time"\s*:\s*\[(.*?)\]',  text, re.DOTALL)
        vM = re.search(r'"value"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if not tM or not vM:
            return []
        times  = re.findall(r'"([^"]+)"', tM.group(1))
        values = re.findall(r'"([^"]+)"', vM.group(1))
        if len(times) != len(values):
            return []
        dates = _resolve_dates(times)
        return [{"date": dt, "value": int(v)} for dt, v in zip(dates, values)]
    except Exception:
        return []


def _fetch_ability_one(spid: int, buildup: int,
                       tc_id: int = 0, tc_lv: int = 0,
                       tc_en_id: int = 0, tc_en_lv: int = 0,
                       tc_ft_id: int = 0) -> dict:
    """단일 선수 세부 능력치를 팀컬러 적용하여 서버사이드 수집."""
    try:
        resp = requests.post(
            "https://fconline.nexon.com/datacenter/PlayerAbility",
            data={
                "spid": spid, "n1Strong": buildup, "n1Grow": 4,  # 적응도 4 고정
                "n4TeamColorId": tc_id, "n4TeamColorLv": tc_lv,
                "n4TeamColorId_Enhance": tc_en_id, "n4TeamColorLv_Enhance": tc_en_lv,
                "n4TeamColorId_Feature": tc_ft_id,
                "n1Change": 1,
                "strPlayerImg": f"{_THUMB_BASE}/playersAction/p{spid % 1000000}_25.png",
                "rd": random.random(),
            },
            headers=_SCRAPER_HEADERS,
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        raw: dict[str, int] = {}
        is_gk = False

        # 주요 능력치 6개가 정확히 담긴 <ul>만 파싱 (세부 능력치 ul 제외)
        for ul in soup.select("ul"):
            items = ul.select("li.ab")
            names = {li.select_one(".txt").text.strip()
                     for li in items if li.select_one(".txt")}
            if names == set(_FIELD_KEYS):
                is_gk = False
            elif names == set(_GK_KEYS):
                is_gk = True
            else:
                continue
            for li in items:
                txt = li.select_one(".txt")
                val = li.select_one(".value")
                if txt and val:
                    try:
                        raw[txt.text.strip()] = int(val.contents[0].strip())
                    except (ValueError, IndexError):
                        pass
            break

        target_keys = _GK_KEYS if is_gk else _FIELD_KEYS
        stats = {k: raw.get(k, 0) for k in target_keys}

        if not raw:
            return {}

        # ── 선호 포지션 (.info_line.info_ab 내 span.position 순회) ──
        pref_positions: list[dict] = []
        ab_section = soup.select_one(".info_line.info_ab")
        if ab_section:
            for pos_span in ab_section.find_all("span", class_="position"):
                txt_el = pos_span.find(class_="txt")
                val_el = pos_span.find(class_="value")
                if not txt_el:
                    continue
                pos_txt = txt_el.get_text(strip=True)
                if not pos_txt:
                    continue
                ovr_val = 0
                if val_el:
                    # 첫 번째 텍스트 노드만 추출 (<span class="diff"> 제외)
                    raw_txt = next((c for c in val_el.children
                                    if isinstance(c, NavigableString)), "")
                    try:
                        ovr_val = int(raw_txt.strip())
                    except ValueError:
                        pass
                pref_positions.append({"pos": pos_txt, "ovr": ovr_val})

        # ── 기본 정보 ──
        def _etxt(sel: str) -> str:
            el = soup.select_one(sel)
            return el.text.strip().replace("\n", "").replace(" ", "") if el else ""

        info = {
            "birth":    _etxt(".etc.birth"),
            "height":   _etxt(".etc.height"),
            "weight":   _etxt(".etc.weight"),
            "physical": _etxt(".etc.physical"),
            "foot":     _etxt(".etc.foot"),
            "skill":    _etxt(".etc.skill"),
        }

        # ── 특성 (.skill_wrap > span > img + span.desc) ──
        traits = []
        skill_wrap = soup.select_one(".skill_wrap")
        if skill_wrap:
            for span in skill_wrap.find_all("span", recursive=False):
                img_el = span.find("img")
                if not img_el:
                    continue
                desc_el = span.find("span", class_="desc")
                desc = (desc_el.text.strip() if desc_el else "") or img_el.get("alt", "")
                traits.append({"img": img_el.get("src", ""), "desc": desc})

        # ── 선수 액션 이미지 ──
        img_url = f"{_THUMB_BASE}/playersAction/p{spid % 1000000}_25.png"

        return {"stats": stats, "is_gk": is_gk,
                "pref_positions": pref_positions,
                "info": info, "traits": traits, "img": img_url}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_squad_ability_data(ability_keys: tuple) -> dict:
    """선수 능력치 데이터 일괄 수집 (5분 캐시)."""
    return {
        f"{spid}_{buildup}": _fetch_ability_one(spid, buildup, tc_id, tc_lv, tc_en_id, tc_en_lv, tc_ft_id)
        for spid, buildup, tc_id, tc_lv, tc_en_id, tc_en_lv, tc_ft_id in ability_keys
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_squad_price_data(player_keys: tuple) -> dict:
    """선수 목록의 시세 데이터를 일괄 수집 (5분 캐시)."""
    return {f"{spid}_{buildup}": _fetch_price_one(spid, buildup)
            for spid, buildup in player_keys}


# ==========================================
# 유틸
# ==========================================

def _thumb_url(path: str) -> str:
    """썸네일 경로에서 쿼리 파라미터를 제거하고 베이스 URL을 붙여 반환."""
    return f"{_THUMB_BASE}{path.split('?')[0]}"


def _enhance_class(grade) -> str:
    """강화 등급(1~13) → CSS 클래스명."""
    g = int(grade or 0)
    if g == 1:   return "en1"
    if g <= 4:   return "en2"
    if g <= 7:   return "en5"
    if g <= 10:  return "en8"
    return "en11"


def _bp_korean(bp: int) -> str:
    """BP를 한국식 단위로 변환. 상위 2개 단위만 표시.
    예) 8_100_000_000_000 → '8조 1000억'
    """
    gyeong = bp // 10**16
    jo     = (bp % 10**16) // 10**12
    eok    = (bp % 10**12) // 10**8
    man    = (bp % 10**8)  // 10**4
    labels = [f"{v}{u}" for v, u in [(gyeong, "경"), (jo, "조"), (eok, "억"), (man, "만")] if v]
    return " ".join(labels[:2]) or "0"


def _card_html(row: pd.Series, pos: str, css_class: str, style: str = "") -> str:
    """선수 카드 HTML 조각 생성 (선발·교체 공통)."""
    grade      = int(row["강화"] or 0)
    enha       = str(grade) if grade else ""
    style_attr = f' style="{style}"' if style else ""
    enhance_div = f'<div class="card-enhance {_enhance_class(grade)}">{enha}</div>' if enha else ""
    spid_val   = int(row.get("spid", 0))
    name_esc   = str(row["이름"]).replace('"', "&quot;")
    price_val  = int(row.get("가격(BP)", 0))
    ovr_val    = int(row.get("OVR") or 0)
    season_icon = str(row.get("시즌아이콘", ""))
    cat        = str(row.get('대분류', 'FW'))
    cat_cls    = f"cat-{cat.lower()}"
    return f"""
<div class="{css_class} {cat_cls}"{style_attr} data-spid="{spid_val}" data-buildup="{grade}" data-name="{name_esc}" data-price="{price_val}" data-ovr="{ovr_val}" data-season-icon="{season_icon}" data-cat="{cat}">
  <div class="card-wrap">
    <img class="card-thumb" src="{row['이미지']}" onerror="this.style.display='none'" />
    <div class="card-tl">
      <span class="card-ovr">{row['OVR']}</span>
      <span class="card-pos">{pos}</span>
      <span class="card-pay">{row['급여']}</span>
    </div>
    {enhance_div}
  </div>
  <div class="card-label">
    <img class="season-icon" src="{row['시즌아이콘']}" onerror="this.style.display='none'" />
    <span class="card-name">{row['이름']}</span>
  </div>
  <div class="card-price">{_bp_korean(row['가격(BP)'])}</div>
</div>"""


def _collect_physicals(
    rows,
    is_starter: bool,
    h_all: list, w_all: list, a_all: list,
    h_st: list,  w_st: list,  a_st: list,
    today: date,
    ability_map: dict,
) -> None:
    """선수 행 목록에서 키·몸무게·만나이를 추출해 누적 리스트에 추가."""
    for _, row in rows:
        key  = f"{int(row.get('spid', 0))}_{int(row.get('강화') or 0)}"
        info = (ability_map.get(key) or {}).get('info', {})
        try:
            h = float(re.search(r'[\d.]+', info.get('height', '')).group())
            if 100 < h < 250:
                h_all.append(h)
                if is_starter:
                    h_st.append(h)
        except Exception:
            pass
        try:
            w = float(re.search(r'[\d.]+', info.get('weight', '')).group())
            if 30 < w < 200:
                w_all.append(w)
                if is_starter:
                    w_st.append(w)
        except Exception:
            pass
        try:
            p = info.get('birth', '').split('.')
            if len(p) >= 3:
                bd  = date(int(p[0]), int(p[1]), int(p[2]))
                age = today.year - bd.year
                if today < date(today.year, bd.month, bd.day):
                    age -= 1
                if 10 < age < 60:
                    a_all.append(age)
                    if is_starter:
                        a_st.append(age)
        except Exception:
            pass


def _fmt_avg_stat(all_v: list, st_v: list, unit: str) -> tuple[str, str]:
    """평균값·단위로 (전체 평균, 선발 전용 평균 괄호 문자열) 반환."""
    if not all_v:
        return '--', ''
    main = f"{sum(all_v) / len(all_v):.1f}{unit}"
    sub  = f"({sum(st_v) / len(st_v):.1f}{unit})" if st_v else ''
    return main, sub


# ==========================================
# UI 컴포넌트
# ==========================================
def render_formation_html(
    df: pd.DataFrame,
    df_sub: pd.DataFrame | None = None,
    price_map: dict | None = None,
    ability_map: dict | None = None,
    tc_map: dict | None = None,
    thumb_map: dict | None = None,
):
    """선수 썸네일을 필드 위에 배치하는 HTML 포메이션 뷰.
    df_sub 전달 시 pitch 바로 아래에 후보 카드를 함께 렌더링."""
    if df.empty:
        st.info("등록된 선수가 없습니다.")
        return

    cards = []
    for _, row in df.iterrows():
        pos = row["포지션"]
        if pos not in _POS_XY:
            continue
        x, y = _POS_XY[pos]
        top  = (115 - y) / 115 * 100
        cards.append(_card_html(row, pos, "pcard", f"left:{x:.1f}%;top:{top:.1f}%"))

    sub_html   = ""
    sub_height = 0
    if df_sub is not None and not df_sub.empty:
        sub_cards  = [_card_html(row, row["포지션"], "scard") for _, row in df_sub.iterrows()]
        n_rows     = (len(df_sub) + 9) // 10
        sub_height = 120 * n_rows + 50
        sub_html   = '<div class="section-title">교체명단</div><div class="sub-wrap">' + "".join(sub_cards) + "</div>"

    # 모바일 기준 (세로 레이아웃 + 차트 활성화) 명시적 높이 계산
    # Team Info(200) + Squad(320) + Price Analysis 패널(260) + Ability(390) + Price(481) + footer·여백(170)
    frame_h = 200 + 320 + sub_height + 260 + 390 + 481 + 170

    # Team Information 계산
    salary_total = int(pd.to_numeric(df["급여"], errors="coerce").fillna(0).sum())
    value_excl   = int(pd.to_numeric(df["가격(BP)"], errors="coerce").fillna(0).sum())
    value_incl   = value_excl + (
        int(pd.to_numeric(df_sub["가격(BP)"], errors="coerce").fillna(0).sum())
        if df_sub is not None and not df_sub.empty else 0
    )

    # 평균 키·몸무게·만나이 계산 (ability_map 있을 때만)
    _loading  = '<span class="chart-loading" style="padding:2px 0;font-size:11px">로딩 중...</span>'
    _h_all, _w_all, _a_all = [], [], []
    _h_st,  _w_st,  _a_st  = [], [], []
    _today = datetime.now().date()
    if ability_map is not None:
        _collect_physicals(df.iterrows(),  True,  _h_all, _w_all, _a_all, _h_st, _w_st, _a_st, _today, ability_map)
        if df_sub is not None and not df_sub.empty:
            _collect_physicals(df_sub.iterrows(), False, _h_all, _w_all, _a_all, _h_st, _w_st, _a_st, _today, ability_map)
        ti_height = _fmt_avg_stat(_h_all, _h_st, 'cm')
        ti_weight = _fmt_avg_stat(_w_all, _w_st, 'kg')
        ti_age    = _fmt_avg_stat(_a_all, _a_st, '세')
    else:
        ti_height = (_loading, '')
        ti_weight = (_loading, '')
        ti_age    = (_loading, '')

    # 포지션 대분류별 가격 (도넛 차트용)
    value_by_cat      = {'GK': 0, 'FW': 0, 'MF': 0, 'DF': 0}  # 선발 + 교체
    value_by_cat_excl = {'GK': 0, 'FW': 0, 'MF': 0, 'DF': 0}  # 선발만
    for _, row in df.iterrows():
        cat = _POS_CAT.get(row.get("포지션", ""), "")
        if cat in value_by_cat:
            val = int(pd.to_numeric(row.get("가격(BP)", 0), errors="coerce") or 0)
            value_by_cat[cat]      += val
            value_by_cat_excl[cat] += val
    if df_sub is not None and not df_sub.empty:
        for _, row in df_sub.iterrows():
            cat = _POS_CAT.get(row.get("포지션", ""), "")
            if cat in value_by_cat:
                value_by_cat[cat] += int(pd.to_numeric(row.get("가격(BP)", 0), errors="coerce") or 0)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:'FCOAllSans';src:url('{_FONT_BOLD_WOFF2}') format('woff2'),url('{_FONT_BOLD_WOFF}') format('woff');font-weight:700}}
@font-face{{font-family:'FCOAllSans';src:url('{_FONT_MED_WOFF2}') format('woff2'),url('{_FONT_MED_WOFF}') format('woff');font-weight:500}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:auto!important;overflow:visible!important}}
body{{background:transparent;font-family:'FCOAllSans','Malgun Gothic',sans-serif;padding-bottom:12px}}
.layout{{display:flex;gap:12px;align-items:stretch}}
.panel{{border-radius:10px;padding:10px 12px;background:#111318}}
.panel-left{{flex:3;display:flex;flex-direction:column;gap:12px}}
.panel-left>.panel:last-child{{flex:1}}
.right-col{{flex:2;display:flex;flex-direction:column;gap:12px}}
.pitch-wrap{{width:100%;padding-bottom:16px}}
.pitch{{position:relative;width:100%;aspect-ratio:1310/832;background-image:url('{_BG_SVG_URL}');background-size:100% 100%;overflow:visible}}
.pcard{{position:absolute;transform:translate(-50%,-50%);width:74px;text-align:center;cursor:pointer;z-index:5;transition:transform 0.25s cubic-bezier(0.34,1.56,0.64,1),filter 0.25s ease}}
.pcard:hover,.pcard.selected{{transform:translate(-50%,-55%) scale(1.2);z-index:100}}
.panel-left:has(.pcard:hover) .pcard:not(:hover),
.panel-left:has(.pcard:hover) .scard,
.panel-left:has(.scard:hover) .pcard,
.panel-left:has(.scard:hover) .scard:not(:hover),
.panel-left:has(.pcard.selected) .pcard:not(.selected):not(:hover),
.panel-left:has(.pcard.selected) .scard:not(:hover),
.panel-left:has(.scard.selected) .pcard:not(:hover),
.panel-left:has(.scard.selected) .scard:not(.selected):not(:hover){{opacity:0.35;transition:opacity 0.2s ease}}
.card-wrap{{position:relative;width:64px;height:69px;margin:0 auto;overflow:visible}}
.card-thumb{{position:absolute;bottom:0;left:50%;transform:translateX(-50%);width:64px;height:64px;object-fit:contain;z-index:1}}
.card-tl{{position:absolute;top:3px;left:4px;display:flex;flex-direction:column;align-items:flex-start;z-index:3;gap:1px}}
.card-ovr{{font-size:13px;font-weight:700;color:#fff;line-height:1;text-shadow:0 0 4px #000,1px 1px 0 #000}}
.card-pos{{font-size:9px;font-weight:700;color:#bebebe;line-height:1;text-shadow:0 0 3px #000}}
.card-pay{{font-size:9px;font-weight:700;color:#aaa;line-height:1;text-shadow:0 0 3px #000}}
.card-enhance{{position:absolute;bottom:0;right:0;width:16px;height:10px;font-size:7px;font-weight:700;line-height:10px;text-align:center;border-radius:0;z-index:5;border:none}}
.en1{{color:#c5c8c9;background:linear-gradient(140deg,#51545a,#42464d)}}
.en2{{color:#7e3f27;background:linear-gradient(140deg,#de946b,#ad5f42)}}
.en5{{color:#4e545e;background:linear-gradient(140deg,rgb(216,217,220),rgb(184,189,202))}}
.en8{{color:#695100;background:linear-gradient(140deg,#f9dd62,#dca908)}}
.en11{{color:#2d2b43;background:url('{_BG_PLT_URL}') no-repeat 0 0/100% 100%}}
.card-label{{display:flex;align-items:center;justify-content:center;gap:3px;margin-top:3px}}
.season-icon{{width:14px;height:11px;object-fit:contain;flex-shrink:0}}
.card-name{{font-size:10px;font-weight:500;color:#fff;text-shadow:1px 1px 0 #000,-1px 0 0 #000;white-space:nowrap}}
.card-price{{font-size:8px;color:#ffd700;text-shadow:1px 1px 0 #000,-1px 0 0 #000;white-space:nowrap;margin-top:1px}}
.cat-gk .card-pos{{color:#f2be57}}
.cat-df .card-pos{{color:#2b7def}}
.cat-mf .card-pos{{color:#00d28b}}
.cat-fw .card-pos{{color:#f6425f}}
.sub-wrap{{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;padding:8px 4px}}
.scard{{width:74px;text-align:center;cursor:pointer;transition:transform 0.25s cubic-bezier(0.34,1.56,0.64,1)}}
.scard:hover,.scard.selected{{transform:translateY(-6px) scale(1.15)}}
.section-title{{font-size:11px;font-weight:700;color:#777;letter-spacing:1px;padding:10px 0 6px;border-top:1px solid #2a2a35}}
.panel-title{{font-size:15px;font-weight:700;color:#e0e0e0;letter-spacing:0.5px;padding-bottom:10px;border-bottom:2px solid #2a2a35;margin-bottom:4px}}
.panel-title + .section-title{{border-top:none}}
@media(max-width:600px){{
  .layout{{flex-direction:column;align-items:stretch}}
  .panel-left,.right-col{{flex:none}}
  .pcard{{width:38px}}
  .card-wrap{{width:33px;height:36px}}
  .card-thumb{{width:33px;height:33px}}
  .card-ovr{{font-size:7px}}
  .card-pos,.card-pay{{font-size:5px}}
  .card-enhance{{width:10px;height:7px;font-size:5px;line-height:7px}}
  .card-name{{font-size:6px}}
  .card-price{{font-size:5px}}
  .season-icon{{width:8px;height:6px}}
}}
{_CHART_CSS}</style></head><body>
<div class="layout">
  <div class="panel-left">
    <div class="panel">
      <div class="panel-title">Team Information</div>
      <div class="ti-row">
        <div class="ti-stat-block">
          <div class="ti-stat-label">선발 급여</div>
          <div class="ti-stat-value">{salary_total:,}</div>
        </div>
        <div class="ti-stat-block">
          <div class="ti-stat-label">평균 키</div>
          <div class="ti-stat-value">{ti_height[0]}</div>
          <div class="ti-stat-sub">{ti_height[1]}</div>
        </div>
        <div class="ti-stat-block">
          <div class="ti-stat-label">평균 몸무게</div>
          <div class="ti-stat-value">{ti_weight[0]}</div>
          <div class="ti-stat-sub">{ti_weight[1]}</div>
        </div>
        <div class="ti-stat-block">
          <div class="ti-stat-label">평균 나이</div>
          <div class="ti-stat-value">{ti_age[0]}</div>
          <div class="ti-stat-sub">{ti_age[1]}</div>
        </div>
        <div class="ti-stat-block ti-chart-block">
          <div class="ti-stat-label">포지션별 평균 OVR</div>
          <div id="ti-abilities">
            <div class="chart-loading" style="font-size:10px;padding:4px 0">계산 중...</div>
          </div>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">Squad</div>
      <div class="section-title">선발명단</div>
      <div class="pitch-wrap"><div class="pitch">
        {"".join(cards)}
      </div></div>
      {sub_html}
    </div>
  </div>
  <div class="right-col">
    <div class="panel">
      <div class="panel-title">Price Analysis</div>
      <div class="pa-row">
        <div class="ti-squad-total">
          <div class="pa-stat-block">
            <span class="ti-squad-label">구단 가치</span>
            <span class="ti-squad-num">{_bp_korean(value_incl)}</span>
            <span class="ti-stat-sub">({_bp_korean(value_excl)})</span>
          </div>
          <div class="pa-stat-block">
            <div id="pa-hint" class="ability-hint" style="padding:8px 12px;font-size:11px">선수 카드를 클릭하면<br>포지션별 금액을 확인할 수 있습니다.</div>
            <span class="ti-squad-label" id="pa-pos-label" style="display:none"></span>
            <span class="ti-squad-num" id="pa-pos-value" style="display:none"></span>
            <span class="ti-stat-sub" id="pa-pos-sub" style="display:none"></span>
          </div>
        </div>
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;background:#16161f;border-radius:6px;padding:8px 10px">
          <span class="ti-squad-label">포지션별 금액 비중</span>
          <div class="ti-donut-wrap">
            <canvas id="ti-donut"></canvas>
            <div class="ti-donut-center">
              <div class="ti-donut-value"></div>
              <div class="ti-donut-cat" id="ti-donut-cat"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">Player Ability</div>
      <div id="ability-hint" class="ability-hint" style="display:{'none' if ability_map is None else ''}">선수 카드를 클릭하면<br>주요 능력치를 확인할 수 있습니다.</div>
      <div id="ability-loading" class="chart-loading" style="display:{'block' if ability_map is None else 'none'}">능력치 로딩 중...</div>
      <div id="ability-body" style="display:none"></div>
    </div>
    <div class="panel" id="price-panel">
      <div class="panel-title">Player Price Graph</div>
      <div id="chart-meta">
        <div id="meta-period-block">
          <div class="meta-label">기간</div>
          <div class="meta-price" id="meta-range"></div>
          <div class="meta-date" id="meta-period-days"></div>
        </div>
        <div id="meta-prices">
          <div class="meta-col">
            <div class="meta-label">현재가</div>
            <div class="meta-price" id="meta-current-price"></div>
            <div class="meta-date" id="meta-current-date"></div>
          </div>
          <div class="meta-col">
            <div class="meta-label">최고가</div>
            <div class="meta-price meta-high" id="meta-high-price"></div>
            <div class="meta-date" id="meta-high-date"></div>
          </div>
          <div class="meta-col">
            <div class="meta-label">최저가</div>
            <div class="meta-price meta-low" id="meta-low-price"></div>
            <div class="meta-date" id="meta-low-date"></div>
          </div>
        </div>
      </div>
      <div id="chart-hint" class="chart-hint" style="display:{'none' if price_map is None else ''}">선수 카드를 클릭하면<br>시세 동향을 확인할 수 있습니다.</div>
      <div id="chart-loading" class="chart-loading" style="display:{'block' if price_map is None else 'none'}">시세 데이터 로딩 중...</div>
      <div id="chart-error" class="chart-error" style="display:none"></div>
      <div id="chart-wrap" style="display:none"><canvas id="priceChart"></canvas></div>
    </div>
  </div>
</div>
<footer style="margin-top:24px;padding:16px 0 10px;border-top:1px solid #2a2a35;text-align:center;color:#444;font-size:10px;line-height:2.2">
  Powered by <a href="https://openapi.nexon.com" target="_blank" style="color:#555;text-decoration:none">NEXON Open API</a>
  &nbsp;·&nbsp; 본 서비스는 ㈜넥슨코리아와 무관하며 제휴 관계가 아닙니다.<br>
  <span style="color:#333">© 2025 FCO4 Citizen Data Scientist &nbsp;·&nbsp; FC Online 게임 데이터의 저작권은 ㈜넥슨코리아에 있습니다.</span>
</footer>
<script>const PRICE_DATA={json.dumps(price_map or {})};const ABILITY_DATA={json.dumps(ability_map or {})};const TC_DATA={json.dumps(tc_map or {})};const THUMB_DATA={json.dumps(thumb_map or {})};const PRICE_LOADED={'true' if price_map is not None else 'false'};const ABILITY_LOADED={'true' if ability_map is not None else 'false'};const TI_VALUE_DATA={json.dumps(value_by_cat)};const TI_VALUE_DATA_EXCL={json.dumps(value_by_cat_excl)};const _SAFE_H={frame_h};let _resizeEnabled=true;</script>
{_CHART_JS}
</body></html>"""

    components.html(html, height=frame_h, scrolling=False)


# ==========================================
# 데이터 맵 빌더
# ==========================================

def _build_player_maps(all_df: pd.DataFrame) -> tuple:
    """스쿼드 DataFrame에서 시세·능력치·썸네일·팀컬러 맵을 생성하여 반환."""
    player_keys = tuple(
        (int(r.get("spid", 0)), int(r.get("강화") or 0))
        for _, r in all_df.iterrows() if r.get("spid", 0)
    )
    ability_keys = tuple(
        (int(r.get("spid", 0)), int(r.get("강화") or 0),
         int(r.get("tc_id") or 0), int(r.get("tc_lv") or 0),
         int(r.get("tc_en_id") or 0), int(r.get("tc_en_lv") or 0),
         int(r.get("tc_ft_id") or 0))
        for _, r in all_df.iterrows() if r.get("spid", 0)
    )
    thumb_map = {
        f"{int(r['spid'])}_{int(r.get('강화') or 0)}": r.get("thumb_url", "")
        for _, r in all_df.iterrows() if r.get("spid", 0)
    }
    tc_map = {
        f"{int(r['spid'])}_{int(r.get('강화') or 0)}": [
            t for t in [
                {"name": r.get("tc1_name", ""), "skill": r.get("tc1_skill", ""), "img": r.get("tc1_img", "")},
                {"name": r.get("tc3_name", ""), "skill": r.get("tc3_skill", ""), "img": r.get("tc3_img", "")},
                {"name": r.get("tc2_name", ""), "skill": r.get("tc2_skill", ""), "img": r.get("tc2_img", "")},
            ] if t["name"]
        ]
        for _, r in all_df.iterrows() if r.get("spid", 0)
    }
    return player_keys, ability_keys, thumb_map, tc_map


# ==========================================
# 메인
# ==========================================
st.markdown(f"""<style>
@font-face {{font-family:'NexonGothicB';src:url('{_FONT_NEXON_B}') format('truetype')}}
h1, h1 * {{font-family:'NexonGothicB',sans-serif !important;color:#07f468 !important}}
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {{background:#161616 !important}}
section[data-testid="stMain"] {{background:#161616 !important}}
</style>""", unsafe_allow_html=True)
st.title("FCO4 Citizen Data Scientist")

if "do_search" not in st.session_state:
    st.session_state.do_search = False

def _on_enter():
    if st.session_state.nickname_input:
        st.session_state.do_search = True

col_input, col_btn = st.columns([5, 1])
with col_input:
    nickname = st.text_input("구단주명", placeholder="구단주 이름을 검색하세요.", label_visibility="collapsed",
                             key="nickname_input", on_change=_on_enter)
with col_btn:
    if st.button("🔍 검색", use_container_width=True) and st.session_state.nickname_input:
        st.session_state.do_search = True

nickname = st.session_state.nickname_input
if st.session_state.do_search and nickname:
    st.session_state.do_search = False
    with st.spinner(f"'{nickname}' 구단주 스쿼드 조회 중..."):
        df_st, df_sub, squad_name = get_squad_data(nickname)

    if df_st is None:
        st.error("❌ 존재하지 않는 구단주이거나 대표 스쿼드가 없습니다.")
    else:
        m  = re.search(r"(\d{14})", squad_name or "")
        ts = datetime.strptime(m.group(1), "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S") if m else squad_name
        st.success(f"✅ 로딩 완료: {ts} 기준")

        tab_price, tab_match = st.tabs(["Price", "Match"])

        with tab_price:
            all_df = pd.concat([df_st, df_sub], ignore_index=True)
            player_keys, ability_keys, thumb_map, tc_map = _build_player_maps(all_df)
            slot = st.empty()
            with slot:
                render_formation_html(
                    df_st, df_sub,
                    price_map=None, ability_map=None,
                    tc_map=tc_map, thumb_map=thumb_map,
                )
            price_map   = get_squad_price_data(player_keys)
            ability_map = get_squad_ability_data(ability_keys)
            with slot:
                render_formation_html(df_st, df_sub, price_map, ability_map, tc_map, thumb_map)
        with tab_match:
            st.info("경기분석 기능은 준비 중입니다.")
