/* powerwiki 站点 UI 回归测试（jsdom）
 *
 * 覆盖：移动端阅读体验 · 体系表与战力等级同步 · 兜底档语义 · 档位卡片背景图
 *
 * 运行：  npm i jsdom && node tests/ui.test.js
 *
 * 注意：jsdom 需要装在能找到的位置（NODE_PATH 或本仓库 node_modules）。
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
let pass = 0, fail = 0;
const fails = [];

function ok(name, cond, extra) {
    if (cond) { pass++; console.log('  ✓ ' + name); }
    else { fail++; fails.push(name + (extra ? ' → ' + extra : '')); console.log('  ✗ ' + name + (extra ? ' → ' + extra : '')); }
}

const MAIN_JS = (() => {
    try { return fs.readFileSync(path.join(ROOT, 'static/js/main.js'), 'utf-8'); }
    catch (e) { return ''; }
})();

function load(rel) {
    const p = path.join(ROOT, rel);
    if (!fs.existsSync(p)) return null;
    const vc = new VirtualConsole();
    vc.on('jsdomError', () => {});
    let html = fs.readFileSync(p, 'utf-8');
    // 外链 <script src> 在 jsdom 里不会自动抓取（沙箱也无公网），
    // 这里摘掉它、改为 DOM 就绪后手动 eval，等价于浏览器里的加载顺序。
    html = html.replace(/<script[^>]+src="[^"]*main\.js"[^>]*>\s*<\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'dangerously',
        pretendToBeVisual: true,
        url: 'https://example.com/powerwiki/' + rel,
        virtualConsole: vc,
    });
    if (MAIN_JS) {
        try { dom.window.eval(MAIN_JS); } catch (e) { /* 忽略 jsdom 能力差异 */ }
    }
    try { dom.window.document.dispatchEvent(new dom.window.Event('load')); } catch (e) {}
    return dom;
}

function read(rel) {
    const p = path.join(ROOT, rel);
    return fs.existsSync(p) ? fs.readFileSync(p, 'utf-8') : null;
}

/** 剥掉 CSS 注释后再检测，避免把注释里的示例代码误判成真实规则 */
function cssNoComments() {
    return (read('static/css/style.css') || '').replace(/\/\*[\s\S]*?\*\//g, '');
}

// cdn.devimg.cn 已开放的 82 项中文题材（写错会 404）
const VALID_CATS = new Set(('包包 电脑 电商主图 电子产品 耳机 服装 家电 键盘 礼物 美妆 母婴 ' +
    '手机 鼠标 数码产品 玩具 鞋子 餐饮门店 咖啡 咖啡馆 美食 水果 甜品 饮料 办公 办公桌 ' +
    '婚礼 健身 人物 书籍 新闻 学校 运动 城市 飞机 风景 火车 酒店 露营 旅行 轮船 摩托 ' +
    '汽车 无人机 中国城市 自行车 宠物 电竞 动漫 动物 古建筑 家具 建筑 商务 室内 医院 ' +
    '游戏 3DRender 玻璃 抽象艺术 国风 海洋 极简 节日 金属 科技 木纹 赛博朋克 森林 石头 ' +
    '水彩 太空 天空 天气 纹理 像素风 烟花 植物 植物盆栽 纸张 AI插画 CG LowPoly').split(' '));

console.log('\n=== powerwiki UI 回归测试 ===\n');

/* ---------------- 1. 产物存在性 ---------------- */
console.log('[1] 产物与数据');
const catFiles = fs.existsSync(path.join(ROOT, 'category'))
    ? fs.readdirSync(path.join(ROOT, 'category')).filter(f => f.endsWith('.html'))
    : [];
ok('档位详情页 92 个', catFiles.length === 92, '实际 ' + catFiles.length);
ok('兜底档 unknown.html 存在', catFiles.includes('unknown.html'));
ok('量级体系表页存在', !!read('page/tiers.html'));
ok('首页存在', !!read('index.html'));

/* ---------------- 2. 移动端 / 阅读体验 ---------------- */
console.log('\n[2] 移动端与阅读体验');
const idx = load('index.html');
ok('首页可加载', !!idx);
{
    const d = idx.window.document;
    ok('注入 js 渐进增强标记', d.documentElement.className.includes('js'));
    ok('存在阅读进度条 .read-progress', !!d.querySelector('.read-progress'));
    ok('存在悬浮按钮组 .fab-stack', !!d.querySelector('.fab-stack'));
    ok('存在回顶部按钮 .fab--top', !!d.querySelector('.fab--top'));
    ok('回顶部按钮含百分比 .fab-pct', !!d.querySelector('.fab--top .fab-pct'));
}
{
    const css = cssNoComments();
    ok('CSS 含移动端断点 (max-width: 860px)', /max-width:\s*860px/.test(css));
    ok('CSS 含窄屏断点 (max-width: 560px)', /max-width:\s*560px/.test(css));
    ok('CSS 含滚动锚点补偿 scroll-margin-top', /scroll-margin-top/.test(css));
    ok('CSS 含键盘焦点样式 :focus-visible', /:focus-visible/.test(css));
    ok('CSS 未给 html 加 overflow-x:hidden（会破坏 sticky 顶栏）',
        !/html\s*\{[^}]*overflow-x:\s*hidden/.test(css));
}
{
    const js = read('static/js/main.js') || '';
    ok('JS 含滚动进度更新 onScroll', /function onScroll/.test(js));
    ok('JS 含阅读进度记忆 restoreProgress', /function restoreProgress/.test(js));
    ok('JS 含目录抽屉 buildDrawer', /function buildDrawer/.test(js));
    ok('JS 只包裹 table 不再包裹 pre', /markOverflow/.test(js));
}

/* ---------------- 3. 体系表 ↔ 首页战力等级 同步 ---------------- */
console.log('\n[3] 体系表与首页战力等级同步');
{
    const tiersHtml = read('page/tiers.html') || '';
    const idxHtml = read('index.html') || '';
    const tierCards = (idxHtml.match(/class="category-card[ "]/g) || []).length;
    const tierLinks = new Set(tiersHtml.match(/\/category\/[a-z0-9-]+\.html/g) || []);
    ok('首页档位卡片 92 个', tierCards === 92, '实际 ' + tierCards);
    ok('体系表页覆盖全部 92 档', tierLinks.size === 92, '实际 ' + tierLinks.size);
    ok('体系表页目录链接 100 条（92 档 + 8 分段）',
        (tiersHtml.match(/href="#/g) || []).length === 100,
        '实际 ' + (tiersHtml.match(/href="#/g) || []).length);
    const anchors = [...tiersHtml.matchAll(/href="#([^"]+)"/g)].map(m => m[1]);
    const ids = new Set([...tiersHtml.matchAll(/id="([^"]+)"/g)].map(m => m[1]));
    const broken = [...new Set(anchors)].filter(a => !ids.has(a));
    ok('体系表页目录锚点全部有效（失效=0）', broken.length === 0, broken.join(','));
}

/* ---------------- 4. 兜底档语义 ---------------- */
console.log('\n[4] 兜底档（未知/暂存）语义');
{
    const unk = read('category/unknown.html') || '';
    ok('兜底档页不出现「更强」标签', !unk.includes('更强'));
    ok('兜底档页不出现「更弱」标签', !unk.includes('更弱'));
    ok('兜底档页使用 .tier-nav--flat', unk.includes('tier-nav--flat'));
    ok('兜底档页说明文案存在', unk.includes('不与正式量级比较强弱'));
    ok('兜底档位次显示为兜底档（非第 N 档）', unk.includes('兜底档 · 不参与强弱排序'));
    ok('兜底档位次不写成「第 92 / 92 档」', !unk.includes('第 92 / 92 档'));
}
{
    const top = read('category/beyond-sky-top.html') || '';
    ok('论天最上不再把「更强 →」指向未知/暂存',
        !/更强\s*→\s*<\/span><span class="tier-nav-name">未知\/暂存/.test(top));
    ok('论天最上标记为体系最强档', top.includes('体系最强档'));
    ok('论天最上位次为第 91 / 91 档', top.includes('第 91 / 91 档'));
}
{
    const insect = read('category/insect.html') || '';
    ok('最弱档标记为体系最弱档', insect.includes('体系最弱档'));
    ok('最弱档位次为第 1 / 91 档', insect.includes('第 1 / 91 档'));
}
{
    // 体系表里兜底档仍排在最末一行，但位次列显示「—」而不是 0 / 92
    const tiers = read('page/tiers.html') || '';
    ok('体系表含兜底档行', tiers.includes('id="tier-unknown"'));
    ok('体系表兜底档位次为「—」',
        /<td class="col-pos" data-label="位次">—<\/td>[\s\S]{0,200}id="tier-unknown"/.test(tiers)
        || /id="tier-unknown"[\s\S]{0,200}col-pos" data-label="位次">—</.test(tiers));
    ok('体系表兜底档位次不再是 0', !/col-pos" data-label="位次">0</.test(tiers));
    ok('体系表兜底档仍在全表最末（分段在最后）',
        tiers.indexOf('id="group-unfiled"') > tiers.indexOf('id="group-beyond"'));
}

/* ---------------- 5. 档位卡片背景图 ---------------- */
console.log('\n[5] 档位卡片背景图（外链 · 语义题材 · 10% 不透明度）');
{
    const idxHtml = read('index.html') || '';
    ok('全部 92 档卡片都带背景图',
        (idxHtml.match(/class="category-card has-bg"/g) || []).length === 92);
    const primary = [...idxHtml.matchAll(/data-bg="([^"]+)"/g)].map(m => m[1]);
    const alt = [...idxHtml.matchAll(/data-bg-alt="([^"]+)"/g)].map(m => m[1]);
    ok('主源 URL 92 条', primary.length === 92);
    ok('备源 URL 92 条', alt.length === 92);
    ok('主源为国内 CDN cdn.devimg.cn', primary.every(u => u.startsWith('https://cdn.devimg.cn/')));
    ok('备源为 picsum', alt.every(u => u.startsWith('https://picsum.photos/')));
    ok('主源全部带 seed 且互不相同',
        primary.every(u => /seed=/.test(u)) && new Set(primary).size === 92);
    ok('内联 style 写入 --tier-bg（无 JS 也有底图）',
        (idxHtml.match(/--tier-bg:url\(/g) || []).length === 92);
    ok('不透明度为 0.10', idxHtml.includes('--tier-bg-opacity:0.1'));
    ok('图片未下载进仓库（无本地图片产物）',
        !fs.existsSync(path.join(ROOT, 'static/img/tiers')));

    // 题材语义：底图内容必须跟档位量级对得上，不能是随机图
    const catOf = {};
    [...idxHtml.matchAll(/href="\/powerwiki\/category\/([^"]+)\.html"[^>]*data-bg="([^"]+)"/g)]
        .forEach(m => {
            const mm = /cat=([^&]+)/.exec(m[2]);
            catOf[m[1]] = mm ? decodeURIComponent(mm[1]) : null;
        });
    const catValues = Object.values(catOf);
    ok('全部 92 档都拿到了题材', catValues.length === 92 && catValues.every(Boolean),
        '实际 ' + catValues.filter(Boolean).length);
    ok('题材全部在图源开放的 82 项白名单内',
        catValues.every(c => VALID_CATS.has(c)),
        catValues.filter(c => !VALID_CATS.has(c)).join(','));
    ok('题材有多种（不是全站同一张图）', new Set(catValues).size >= 10,
        '实际 ' + new Set(catValues).size + ' 种');

    const expect = {
        'insect': '动物', 'weak-human': '人物', 'weak-brick': '石头',
        'city': '城市', 'country': '风景', 'eurasia-continent': '森林',
        'surface': '海洋', 'planet': '太空', 'star': '太空',
        'star-system': '天空', 'universe': '太空',
        'beyond-threshold': '抽象艺术', 'beyond-sky-top': '赛博朋克',
        'unknown': '纹理',
    };
    const missing = Object.keys(expect).filter(s => !(s in catOf));
    ok('关键档位都在首页卡片里', missing.length === 0, missing.join(','));
    const wrong = Object.entries(expect)
        .filter(([slug, c]) => catOf[slug] && catOf[slug] !== c)
        .map(([slug, c]) => `${slug}: 期望${c} 实际${catOf[slug]}`);
    ok('关键档位题材与量级语义一致', wrong.length === 0, wrong.join(' | '));
}
{
    const js = read('static/js/main.js') || '';
    ok('JS 含背景图探测 tierBackgrounds', /function tierBackgrounds/.test(js));
    ok('JS 含备源回退 probeBg', /function probeBg/.test(js));
    ok('全部源失败时摘掉 has-bg（不留破图）', /classList\.remove\('has-bg'\)/.test(js));
}
{
    const css = cssNoComments();
    ok('底图挂在 ::before 伪元素上（不淡文字）', /\.category-card::before/.test(css));
    ok('has-bg 时伪元素不透明度取自变量',
        /\.category-card\.has-bg::before\s*\{\s*opacity:\s*var\(--tier-bg-opacity/.test(css));
    ok('卡片内容 z-index 提升，压在底图之上', /\.category-card\s*>\s*\*\s*\{[^}]*z-index:\s*1/.test(css));
    ok('含 .tier-nav--flat 样式', /\.tier-nav--flat/.test(css));
}

/* ---------------- 6. 站点只放内容 ---------------- */
console.log('\n[6] 站点只放内容（维护信息不进页面）');
{
    const all = ['index.html', 'page/tiers.html', 'page/rules.html']
        .map(read).filter(Boolean).join('\n');
    const devWords = ['data/categories.yaml', 'build_site.py', '重新构建', '口径与维护',
                      '已定稿', '未定稿事项', 'CHANGELOG'];
    const hit = devWords.filter(w => all.includes(w));
    ok('页面内无开发者向关键词', hit.length === 0, hit.join(','));
    ok('仓库内存在 CHANGELOG.md', fs.existsSync(path.join(ROOT, 'CHANGELOG.md')));
}

/* ---------------- 7. HTML 结构 ---------------- */
console.log('\n[7] HTML 结构');
{
    const files = ['index.html', 'page/tiers.html', 'page/rules.html',
                   'category/unknown.html', 'category/beyond-sky-top.html'];
    const bad = [];
    for (const f of files) {
        const h = read(f);
        if (!h) { bad.push(f + '(缺失)'); continue; }
        const open = (h.match(/<div\b/g) || []).length;
        const close = (h.match(/<\/div>/g) || []).length;
        if (open !== close) bad.push(f + `(div ${open}/${close})`);
    }
    ok('关键页面 div 标签闭合平衡', bad.length === 0, bad.join(' '));
}

console.log('\n========================================');
console.log(`结果：${pass} 通过 / ${fail} 失败（共 ${pass + fail}）`);
if (fail) { console.log('\n失败项：'); fails.forEach(f => console.log('  - ' + f)); }
console.log('========================================\n');
process.exit(fail ? 1 : 0);
