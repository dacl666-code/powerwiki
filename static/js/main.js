// 通用交互脚本

document.addEventListener('DOMContentLoaded', function () {
    // 自动隐藏 flash 消息
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.5s';
            setTimeout(function () { alert.remove(); }, 500);
        }, 3000);
    });

    // 首字母自动填充
    const nameInput = document.getElementById('name');
    const firstLetterInput = document.getElementById('first_letter');
    if (nameInput && firstLetterInput && !firstLetterInput.value) {
        nameInput.addEventListener('blur', function () {
            if (nameInput.value && !firstLetterInput.value) {
                const first = nameInput.value.trim().charAt(0).toUpperCase();
                firstLetterInput.value = first;
            }
        });
    }

    // 文档页：右侧目录(scrollspy + 窄屏折叠) + 返回按钮 + 浏览进度保存/恢复
    const layout = document.querySelector('.doc-layout');
    if (layout) {
        const slug = layout.getAttribute('data-page-slug') || 'page';
        const KEY = 'doc-progress-' + slug;
        const toc = document.getElementById('doc-toc');
        const backBtn = document.querySelector('[data-back]');

        // ---- 目录滚动高亮 (scrollspy) ----
        let onScroll = function () {};
        if (toc) {
            const title = toc.querySelector('.doc-toc-title');
            const links = Array.from(toc.querySelectorAll('.doc-toc-body a'));
            const headings = Array.from(document.querySelectorAll(
                '.markdown-content h1, .markdown-content h2, .markdown-content h3, .markdown-content h4'
            ));

            // 窄屏（<=1080px）默认收起目录，点击标题切换
            if (title && window.matchMedia('(max-width: 1080px)').matches) {
                toc.classList.add('collapsed');
                title.addEventListener('click', function () {
                    toc.classList.toggle('collapsed');
                });
            }

            // 标题 id -> 对应目录链接
            const map = {};
            links.forEach(function (a) {
                const href = a.getAttribute('href') || '';
                const id = href.split('#')[1];
                if (id) map[id] = a;
            });

            let ticking = false;
            onScroll = function () {
                if (ticking) return;
                ticking = true;
                requestAnimationFrame(function () {
                    let current = null;
                    const offset = 110;
                    for (let i = 0; i < headings.length; i++) {
                        if (headings[i].getBoundingClientRect().top - offset <= 0) {
                            current = headings[i].id;
                        } else {
                            break;
                        }
                    }
                    if (!current && headings.length) current = headings[0].id;
                    links.forEach(function (a) { a.classList.remove('active'); });
                    if (current && map[current]) map[current].classList.add('active');
                    ticking = false;
                });
            };
            window.addEventListener('scroll', onScroll, { passive: true });
            window.addEventListener('resize', onScroll, { passive: true });
        }

        // ---- 浏览进度保存 / 恢复 ----
        function saveProgress() {
            try {
                sessionStorage.setItem(KEY, JSON.stringify({
                    y: window.scrollY || window.pageYOffset || 0,
                    hash: location.hash || ''
                }));
            } catch (e) { /* 忽略隐私模式等异常 */ }
        }

        let tick = false;
        window.addEventListener('scroll', function () {
            if (tick) return;
            tick = true;
            requestAnimationFrame(function () { saveProgress(); tick = false; });
        }, { passive: true });
        window.addEventListener('hashchange', saveProgress);

        // 进入页面时恢复上次位置（load 后高度稳定，DOMContentLoaded 先试一次）
        function restore() {
            let st = null;
            try {
                const raw = sessionStorage.getItem(KEY);
                if (raw) st = JSON.parse(raw);
            } catch (e) {}
            if (st && typeof st.y === 'number') {
                window.scrollTo(0, st.y);
                onScroll();
            }
        }
        restore();
        window.addEventListener('load', restore);

        // ---- 返回按钮：优先回上一页，无历史则回链接兜底；离开前保存进度 ----
        if (backBtn) {
            backBtn.addEventListener('click', function (e) {
                e.preventDefault();
                saveProgress();
                if (window.history.length > 1) {
                    window.history.back();
                } else {
                    window.location.href = backBtn.getAttribute('href') || '/';
                }
            });
        }
    }
});
