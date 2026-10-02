/* ==========================================================================
   全站交互脚本
   --------------------------------------------------------------------------
   1. 阅读进度条    顶部细条 + 「顶部」按钮上的百分比
   2. 悬浮操作区   返回 / 顶部 / 目录 —— 滚到任何位置都够得着
   3. 阅读进度记忆 离开页面存位置，回来自动恢复（带 #锚点 时不恢复）
   4. 移动端目录抽屉  目录整块搬进底部抽屉，点条目即跳转并自动收起
   5. 锚点跳转偏移  按实际顶栏高度下移，避免标题被吸顶栏盖住
   6. 宽表格横向滚动 自动包一层可滑动容器，不再撑破整页
   7. 目录滚动高亮  当前所在小节在目录里高亮（桌面侧栏 + 移动抽屉通用）

   目录高亮不再依赖「.markdown-content 里的 h1~h4」，而是直接取目录链接指向的
   元素，因此规则页（Markdown 生成）和量级体系表页（表格生成）都能用同一套逻辑。
   ========================================================================== */
(function () {
    'use strict';

    /* ---------- 站点根路径：从本脚本的 src 反推，换部署路径也不用改 ---------- */
    var BASE = '/powerwiki';
    (function () {
        var el = document.querySelector('script[src*="/static/js/main.js"]');
        if (!el) return;
        var src = el.getAttribute('src') || '';
        var i = src.indexOf('/static/js/main.js');
        if (i >= 0) BASE = src.slice(0, i) || '';
    })();

    var $ = function (sel, root) { return (root || document).querySelector(sel); };
    var $$ = function (sel, root) {
        return Array.prototype.slice.call((root || document).querySelectorAll(sel));
    };

    var header = $('.site-header');
    var layout = $('.doc-layout');
    var isHome = (function () {
        var p = location.pathname.replace(/\/index\.html$/, '/');
        return p === BASE + '/' || p === BASE || p === '/index.html' || p === '/';
    })();
    var pageSlug = layout ? (layout.getAttribute('data-page-slug') || 'page') : '';

    /* ==================================================================
       1. 顶栏高度 -> CSS 变量（锚点偏移与跳转都靠它）
       ================================================================== */
    function syncHeaderHeight() {
        var h = header ? header.offsetHeight : 0;
        document.documentElement.style.setProperty('--header-h', (h + 8) + 'px');
        return h;
    }
    var headerH = syncHeaderHeight();
    window.addEventListener('resize', function () { headerH = syncHeaderHeight(); });
    window.addEventListener('orientationchange', function () {
        setTimeout(function () { headerH = syncHeaderHeight(); }, 250);
    });

    /* ==================================================================
       2. 宽表格 / 长代码块：包一层可横向滑动的容器
       ================================================================== */
    function wrapOverflowing(node, cls) {
        Array.prototype.forEach.call(node, function (el) {
            if (el.parentElement && el.parentElement.classList.contains(cls)) return;
            var wrap = document.createElement('div');
            wrap.className = cls;
            el.parentNode.insertBefore(wrap, el);
            wrap.appendChild(el);
        });
    }
    wrapOverflowing($$('.markdown-content table'), 'table-wrap');
    // pre 自身在 CSS 里已可横滑，不重复包裹（提示文案是针对表格的）

    /* 溢出提示：字体加载完成后宽度会变，load 后再判定一次 */
    function markOverflow() {
        $$('.table-wrap').forEach(function (w) {
            var t = w.firstElementChild;
            if (!t) return;
            if (t.scrollWidth > w.clientWidth + 4) w.classList.add('has-overflow');
            else w.classList.remove('has-overflow');
        });
    }
    markOverflow();
    window.addEventListener('load', markOverflow);

    /* ==================================================================
       3. 阅读进度条
       ================================================================== */
    var progressBar = document.createElement('div');
    progressBar.className = 'read-progress';
    progressBar.innerHTML = '<i></i>';
    document.body.appendChild(progressBar);
    var progressFill = $('i', progressBar);

    /* ==================================================================
       4. 悬浮操作区：返回 / 顶部 / 目录
       ================================================================== */
    var fabStack = document.createElement('div');
    fabStack.className = 'fab-stack';

    function makeFab(cls, label, title, onClick) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'fab ' + cls;
        b.setAttribute('title', title);
        b.setAttribute('aria-label', title);
        b.innerHTML = label;
        b.addEventListener('click', onClick);
        fabStack.appendChild(b);
        return b;
    }

    // 「顶部」按钮上带百分比，长文档里能看出读到哪
    var fabTop = makeFab('fab--top', '<span>顶部</span><span class="fab-pct">0%</span>',
        '回到顶部', function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    var pctEl = $('.fab-pct', fabTop);
    fabTop.classList.add('is-hidden');

    var fabToc = null;

    var fabBack = null;
    if (!isHome) {
        fabBack = makeFab('fab--back', '返回', '返回上一页', function () {
            saveProgress();
            if (window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = BASE + '/index.html';
            }
        });
    }
    document.body.appendChild(fabStack);

    /* ==================================================================
       5. 移动端目录抽屉
       ================================================================== */
    var toc = $('#doc-toc');
    var tocHome = toc ? toc.parentNode : null;
    var tocAnchor = toc ? toc.nextSibling : null;
    var backdrop, drawer, drawerBody;
    var tocLinks = [];

    function buildDrawer() {
        backdrop = document.createElement('div');
        backdrop.className = 'toc-backdrop';
        backdrop.addEventListener('click', closeToc);

        drawer = document.createElement('div');
        drawer.className = 'toc-drawer';
        drawer.setAttribute('aria-hidden', 'true');
        drawer.innerHTML =
            '<div class="toc-drawer-head">' +
            '  <span class="toc-drawer-title">目录</span>' +
            '  <button type="button" class="toc-drawer-close" aria-label="关闭目录">✕</button>' +
            '</div>' +
            '<div class="toc-drawer-body"></div>';
        drawerBody = $('.toc-drawer-body', drawer);
        $('.toc-drawer-close', drawer).addEventListener('click', closeToc);

        document.body.appendChild(backdrop);
        document.body.appendChild(drawer);
    }

    function openToc() {
        if (!drawer) return;
        drawer.classList.add('is-open');
        backdrop.classList.add('is-open');
        drawer.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        var active = $('.doc-toc-body a.active', drawer);
        if (active && active.scrollIntoView) {
            active.scrollIntoView({ block: 'center' });
        }
    }

    function closeToc() {
        if (!drawer) return;
        drawer.classList.remove('is-open');
        backdrop.classList.remove('is-open');
        drawer.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    function isNarrow() { return window.matchMedia('(max-width: 1080px)').matches; }

    function placeToc() {
        if (!toc || !drawer) return;
        if (isNarrow()) {
            if (toc.parentNode !== drawerBody) drawerBody.appendChild(toc);
            if (!fabToc) {
                fabToc = makeFab('fab--toc', '目录', '打开目录', openToc);
                // 「目录」插在「顶部」之上，保持 目录 / 顶部 / 返回 的自上而下顺序
                fabStack.insertBefore(fabToc, fabTop);
            }
            fabToc.classList.remove('is-hidden');
        } else {
            if (toc.parentNode !== tocHome) {
                if (tocAnchor && tocAnchor.parentNode === tocHome) {
                    tocHome.insertBefore(toc, tocAnchor);
                } else {
                    tocHome.appendChild(toc);
                }
            }
            if (fabToc) fabToc.classList.add('is-hidden');
            closeToc();
        }
    }

    /* ==================================================================
       6. 锚点跳转：按顶栏高度下移，移动端点完自动收起抽屉
       ================================================================== */
    function scrollToId(id) {
        var target = document.getElementById(id);
        if (!target) return false;
        var y = target.getBoundingClientRect().top + window.pageYOffset - headerH - 14;
        if (y < 0) y = 0;
        window.scrollTo({ top: y, behavior: 'smooth' });
        return true;
    }

    function refreshTocLinks() {
        var scope = toc ? (toc.parentNode === drawerBody ? drawer : toc) : null;
        if (!scope) { tocLinks = []; return; }
        tocLinks = $$('a[href^="#"]', scope).map(function (a) {
            return {
                a: a,
                el: document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)))
            };
        }).filter(function (t) { return t.el; });
    }

    function bindTocClicks() {
        if (!toc) return;
        toc.addEventListener('click', function (e) {
            var a = e.target.closest ? e.target.closest('a[href^="#"]') : null;
            if (!a) return;
            var id = decodeURIComponent(a.getAttribute('href').slice(1));
            if (!id || !document.getElementById(id)) return;
            e.preventDefault();
            closeToc();
            scrollToId(id);
            // 把位置同步到地址栏，方便复制分享，又不触发整页跳转
            if (history.replaceState) history.replaceState(null, '', '#' + id);
        });
    }

    /* ==================================================================
       7. 目录滚动高亮（桌面侧栏 + 移动抽屉通用）
       ================================================================== */
    var ticking = false;

    function updateActive() {
        if (!tocLinks.length) return;
        var offset = headerH + 24;
        var current = null;
        for (var i = 0; i < tocLinks.length; i++) {
            if (tocLinks[i].el.getBoundingClientRect().top - offset <= 0) current = tocLinks[i];
            else break;
        }
        if (!current && tocLinks.length) current = tocLinks[0];
        tocLinks.forEach(function (t) { t.a.classList.remove('active'); });
        if (current) current.a.classList.add('active');
    }

    /* ==================================================================
       8. 滚动总处理：进度条 + 悬浮按钮显隐 + 目录高亮 + 进度保存
       ================================================================== */
    var KEY = 'doc-progress-' + pageSlug;

    function saveProgress() {
        if (!layout) return;
        try {
            sessionStorage.setItem(KEY, JSON.stringify({
                y: window.pageYOffset || 0,
                hash: location.hash || ''
            }));
        } catch (e) { /* 隐私模式下忽略 */ }
    }

    function onScroll() {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(function () {
            var doc = document.documentElement;
            var max = (doc.scrollHeight - window.innerHeight) || 1;
            var y = window.pageYOffset || doc.scrollTop || 0;
            var pct = Math.min(100, Math.max(0, Math.round((y / max) * 100)));

            progressFill.style.width = pct + '%';
            if (pctEl) pctEl.textContent = pct + '%';

            // 滚过一屏才显示「顶部」，避免首屏就挡内容
            if (y > window.innerHeight * 0.6) fabTop.classList.remove('is-hidden');
            else fabTop.classList.add('is-hidden');

            updateActive();
            saveProgress();
            ticking = false;
        });
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', function () {
        headerH = syncHeaderHeight();
        placeToc();
        onScroll();
    }, { passive: true });

    /* ==================================================================
       9. 阅读进度恢复：带 #锚点 进入时不恢复，交给锚点自己定位
       ================================================================== */
    function restoreProgress() {
        if (!layout) return;
        if (location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)))) {
            // 从别页带着锚点进来（如首页「体系表 → 论外级」），优先落到锚点
            setTimeout(function () { scrollToId(decodeURIComponent(location.hash.slice(1))); }, 60);
            return;
        }
        var st = null;
        try {
            var raw = sessionStorage.getItem(KEY);
            if (raw) st = JSON.parse(raw);
        } catch (e) { /* 忽略 */ }
        if (st && typeof st.y === 'number' && st.y > 0) {
            window.scrollTo({ top: st.y, behavior: 'auto' });
        }
    }

    /* ==================================================================
       10. 非文档页：面包屑注入「返回」
       ================================================================== */
    function injectBreadcrumbBack() {
        if (isHome || layout) return;
        $$('.breadcrumb').forEach(function (crumb) {
            if ($('[data-back]', crumb)) return;
            var back = document.createElement('a');
            back.className = 'back-btn';
            back.setAttribute('data-back', '');
            back.setAttribute('href', BASE + '/index.html');
            back.textContent = '返回';
            crumb.insertBefore(back, crumb.firstChild);
            back.addEventListener('click', function (e) {
                e.preventDefault();
                if (window.history.length > 1) window.history.back();
                else window.location.href = BASE + '/index.html';
            });
        });
    }

    /* ==================================================================
       11. 文档页面包屑上的静态返回按钮：离开前先存进度
       ================================================================== */
    function bindStaticBack() {
        var backBtn = layout ? $('[data-back]') : null;
        if (!backBtn) return;
        backBtn.addEventListener('click', function (e) {
            e.preventDefault();
            saveProgress();
            if (window.history.length > 1) window.history.back();
            else window.location.href = backBtn.getAttribute('href') || (BASE + '/index.html');
        });
    }

    /* ==================================================================
       12. 杂项：flash 消息自动消失、首字母自动填充
       ================================================================== */
    function misc() {
        $$('.alert').forEach(function (alert) {
            setTimeout(function () {
                alert.style.opacity = '0';
                alert.style.transition = 'opacity .5s';
                setTimeout(function () { if (alert.parentNode) alert.parentNode.removeChild(alert); }, 500);
            }, 3000);
        });

        var nameInput = document.getElementById('name');
        var firstLetterInput = document.getElementById('first_letter');
        if (nameInput && firstLetterInput && !firstLetterInput.value) {
            nameInput.addEventListener('blur', function () {
                if (nameInput.value && !firstLetterInput.value) {
                    firstLetterInput.value = nameInput.value.trim().charAt(0).toUpperCase();
                }
            });
        }
    }

    /* ==================================================================
       启动
       ================================================================== */
    function init() {
        if (toc) {
            buildDrawer();
            bindTocClicks();
        }
        placeToc();
        refreshTocLinks();
        injectBreadcrumbBack();
        bindStaticBack();
        misc();

        headerH = syncHeaderHeight();
        onScroll();
        restoreProgress();
        window.addEventListener('load', function () {
            headerH = syncHeaderHeight();
            placeToc();
            refreshTocLinks();
            onScroll();
            restoreProgress();
        });
        window.addEventListener('hashchange', function () { refreshTocLinks(); onScroll(); });

        // ESC 关闭目录抽屉
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeToc();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
