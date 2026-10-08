/* ============================================================
 * 皮肤癌检测系统 · 管理后台共享脚本
 * 提供：guardAdmin 守卫 / api 封装 / 布局渲染 / 通用工具
 * 参考医小喵 admin_api 同构做法（token 同源 localStorage）
 * ============================================================ */
(function (global) {
  'use strict';

  const KEY_TOKEN = 'skin_token';
  const KEY_USER = 'skin_admin_user';
  const API = '/api';
  const ADMIN_API = '/admin/api';

  // ---------- 令牌 ----------
  function getToken() { return localStorage.getItem(KEY_TOKEN); }
  function getUser() {
    try { return JSON.parse(localStorage.getItem(KEY_USER) || 'null'); }
    catch (e) { return null; }
  }
  function logout() {
    localStorage.removeItem(KEY_TOKEN);
    localStorage.removeItem(KEY_USER);
    location.replace('login.html');
  }

  /**
   * 页面守卫：无 token / 非管理员 → 跳登录页
   * 每个后台页面首行都必须调用
   */
  function guardAdmin() {
    const t = getToken();
    const u = getUser();
    if (!t || !u || u.role !== 'admin') {
      location.replace('login.html');
      return false;
    }
    return true;
  }

  // ---------- 请求封装 ----------
  /**
   * @param {string} path   如 '/records?limit=10'（自动补 /admin/api 前缀）
   * @param {object} opts   {method, body}
   * @param {boolean} raw   true 时返回完整 {status, data}
   */
  async function api(path, opts = {}, raw = false) {
    const token = getToken();
    const res = await fetch(ADMIN_API + path, {
      method: opts.method || 'GET',
      headers: Object.assign({
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + (token || '')
      }, opts.headers || {}),
      body: opts.body ? JSON.stringify(opts.body) : undefined
    });

    // 401 未登录 / 403 非管理员 → 踢回登录页
    if (res.status === 401 || res.status === 403) {
      logout();
      throw new Error(res.status === 403 ? '需要管理员权限' : '登录已过期');
    }
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (raw) return { status: res.status, data };
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || ('请求失败 (' + res.status + ')');
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return data;
  }

  /** 公共 API（非管理，如健康检查 / 退出登录） */
  async function publicApi(path, opts = {}) {
    const res = await fetch(API + path, {
      method: opts.method || 'GET',
      headers: { 'Content-Type': 'application/json' },
      body: opts.body ? JSON.stringify(opts.body) : undefined
    });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) throw new Error((data && data.detail) || ('请求失败 ' + res.status));
    return data;
  }

  // ---------- 通用工具 ----------
  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  function fmtTime(s) {
    if (!s) return '—';
    return String(s).replace('T', ' ').slice(0, 19);
  }

  function fmtPct(v, digits = 2) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    return (Number(v) * 100).toFixed(digits) + '%';
  }

  function toast(msg, type = 'success') {
    const id = 'toast-' + Date.now();
    const color = { success: 'text-bg-success', danger: 'text-bg-danger',
                    warning: 'text-bg-warning', info: 'text-bg-info' }[type] || 'text-bg-success';
    const icon = { success: 'check-circle', danger: 'x-circle',
                   warning: 'exclamation-triangle', info: 'info-circle' }[type] || 'check-circle';
    const el = document.createElement('div');
    el.id = id;
    el.className = 'toast align-items-center border-0 ' + color;
    el.setAttribute('role', 'alert');
    el.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;min-width:220px';
    el.innerHTML =
      '<div class="d-flex"><div class="toast-body">' +
      '<i class="bi bi-' + icon + '"></i> ' + esc(msg) +
      '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" ' +
      'data-bs-dismiss="toast"></button></div>';
    document.body.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: 2600 });
    t.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
  }

  /** 简易确认框（Promise<boolean>） */
  function confirmBox(message, title = '请确认') {
    return new Promise(resolve => {
      const id = 'cfm-' + Date.now();
      const el = document.createElement('div');
      el.id = id;
      el.className = 'modal fade';
      el.innerHTML =
        '<div class="modal-dialog modal-dialog-centered"><div class="modal-content">' +
        '<div class="modal-header"><h5 class="modal-title">' + esc(title) + '</h5>' +
        '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>' +
        '<div class="modal-body">' + esc(message) + '</div>' +
        '<div class="modal-footer">' +
        '<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>' +
        '<button type="button" class="btn btn-danger" id="' + id + '-ok">确定</button>' +
        '</div></div></div>';
      document.body.appendChild(el);
      const m = new bootstrap.Modal(el);
      let done = false;
      document.getElementById(id + '-ok').onclick = () => { done = true; m.hide(); };
      el.addEventListener('hidden.bs.modal', () => {
        el.remove();
        resolve(done);
      });
      m.show();
    });
  }

  // ---------- 布局 ----------
  const MENU = [
    { href: 'index.html', icon: 'speedometer2', text: '数据看板' },
    { href: 'records.html', icon: 'images', text: '检测记录' },
    { href: 'users.html', icon: 'people', text: '用户统计' },
    { href: 'accounts.html', icon: 'person-badge', text: '账号管理' },
    { href: 'model.html', icon: 'robot', text: '模型管理' },
    { href: 'logs.html', icon: 'journal-text', text: '操作日志' },
    { href: 'system.html', icon: 'cpu', text: '系统状态' }
  ];

  /**
   * 渲染「侧栏 + 顶栏」布局，并把页面主体塞进 .app-main
   * 页面里放 <div id="app-content">…</div> 即可
   */
  function renderLayout(activeHref, pageTitle) {
    const u = getUser() || { username: '—' };
    const navItems = MENU.map(m => {
      const active = m.href === activeHref ? ' active' : '';
      return '<li class="nav-item"><a href="' + m.href + '" class="nav-link' + active + '">' +
        '<i class="nav-icon bi bi-' + m.icon + '"></i><p>' + m.text + '</p></a></li>';
    }).join('');

    const brand = '皮肤癌检测 · 后台';

    const html =
      '<div class="app-wrapper">' +
      // 侧栏
      '<nav class="app-header navbar navbar-expand bg-body border-bottom">' +
      '<div class="container-fluid">' +
      '<ul class="navbar-nav">' +
      '<li class="nav-item"><a class="nav-link" data-lte-toggle="sidebar" href="#" role="button">' +
      '<i class="bi bi-list"></i></a></li>' +
      '<li class="nav-item d-none d-md-block"><a href="index.html" class="nav-link">' + brand + '</a></li>' +
      '</ul>' +
      '<ul class="navbar-nav ms-auto">' +
      '<li class="nav-item"><a class="nav-link" href="/app/" target="_blank" title="打开检测系统">' +
      '<i class="bi bi-box-arrow-up-right"></i> 检测系统</a></li>' +
      '<li class="nav-item dropdown">' +
      '<a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">' +
      '<i class="bi bi-person-circle"></i> ' + esc(u.username) +
      ' <span class="badge text-bg-danger ms-1">admin</span></a>' +
      '<ul class="dropdown-menu dropdown-menu-end">' +
      '<li><h6 class="dropdown-header">' + esc(u.email || '') + '</h6></li>' +
      '<li><a class="dropdown-item" href="system.html"><i class="bi bi-cpu me-2"></i>系统状态</a></li>' +
      '<li><hr class="dropdown-divider"></li>' +
      '<li><a class="dropdown-item text-danger" href="#" id="btn-logout">' +
      '<i class="bi bi-box-arrow-right me-2"></i>退出登录</a></li>' +
      '</ul></li></ul></div></nav>' +
      // 侧边菜单
      '<aside class="app-sidebar bg-body-secondary shadow" data-bs-theme="dark">' +
      '<div class="sidebar-brand"><a href="index.html" class="brand-link">' +
      '<i class="bi bi-heart-pulse-fill brand-image opacity-75"></i>' +
      '<span class="brand-text fw-light">管理后台</span></a></div>' +
      '<div class="sidebar-wrapper"><nav class="mt-2"><ul class="nav sidebar-menu flex-column" ' +
      'data-lte-toggle="treeview" role="menu" data-accordion="false">' + navItems +
      '</ul></nav></div></aside>' +
      // 主体
      '<main class="app-main">' +
      '<div class="app-content-header"><div class="container-fluid">' +
      '<div class="row"><div class="col-sm-6"><h3 class="mb-0">' + esc(pageTitle) + '</h3></div>' +
      '<div class="col-sm-6"><ol class="breadcrumb float-sm-end">' +
      '<li class="breadcrumb-item"><a href="index.html">首页</a></li>' +
      '<li class="breadcrumb-item active">' + esc(pageTitle) + '</li>' +
      '</ol></div></div></div></div>' +
      '<div class="app-content"><div class="container-fluid" id="app-content-slot"></div></div>' +
      '</main>' +
      '<footer class="app-footer"><div class="float-end d-none d-sm-inline">v1.1.0</div>' +
      '<strong>© 2026 皮肤癌图像检测系统 · 管理后台</strong> ' +
      '<span class="text-muted small ms-2">仅内部演示使用</span></footer>' +
      '</div>';

    document.body.insertAdjacentHTML('afterbegin', html);

    // 把原页面内容搬到 slot
    const src = document.getElementById('app-content');
    if (src) document.getElementById('app-content-slot').appendChild(src);

    const lo = document.getElementById('btn-logout');
    if (lo) lo.onclick = e => { e.preventDefault(); logout(); };
  }

  /** 生成分页条 HTML */
  function pager(total, limit, offset, idPrefix = 'pg') {
    const pages = Math.max(1, Math.ceil(total / limit));
    const cur = Math.floor(offset / limit) + 1;
    let nums = [];
    let s = Math.max(1, cur - 2), e = Math.min(pages, s + 4);
    s = Math.max(1, e - 4);
    for (let i = s; i <= e; i++) nums.push(i);

    let html = '<nav><ul class="pagination pagination-sm mb-0">';
    html += '<li class="page-item ' + (cur <= 1 ? 'disabled' : '') +
      '"><a class="page-link" href="#" data-pg="' + (cur - 1) + '">上一页</a></li>';
    if (s > 1) html += '<li class="page-item"><a class="page-link" href="#" data-pg="1">1</a></li>' +
      (s > 2 ? '<li class="page-item disabled"><span class="page-link">…</span></li>' : '');
    nums.forEach(n => {
      html += '<li class="page-item ' + (n === cur ? 'active' : '') +
        '"><a class="page-link" href="#" data-pg="' + n + '">' + n + '</a></li>';
    });
    if (e < pages) html += (e < pages - 1 ?
      '<li class="page-item disabled"><span class="page-link">…</span></li>' : '') +
      '<li class="page-item"><a class="page-link" href="#" data-pg="' + pages + '">' + pages + '</a></li>';
    html += '<li class="page-item ' + (cur >= pages ? 'disabled' : '') +
      '"><a class="page-link" href="#" data-pg="' + (cur + 1) + '">下一页</a></li>';
    html += '</ul></nav>';

    return {
      html,
      bind(cb) {
        document.querySelectorAll('[data-pg]').forEach(a => {
          a.onclick = ev => {
            ev.preventDefault();
            const p = parseInt(a.dataset.pg, 10);
            if (!isNaN(p) && p >= 1 && p <= pages && p !== cur) cb(p);
          };
        });
      },
      pages, cur
    };
  }

  global.Admin = {
    KEY_TOKEN, KEY_USER, API, ADMIN_API,
    getToken, getUser, logout, guardAdmin,
    api, publicApi, esc, fmtTime, fmtPct, toast, confirmBox,
    renderLayout, pager, MENU
  };
})(window);
