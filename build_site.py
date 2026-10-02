"""
文件式静态站点生成器（无 Flask / 无 SQLite 依赖）

数据来源：data/ 下的可编辑 YAML 文件
  - categories.yaml   量级分类（含 76 个战力档位）
  - realms.yaml       境界体系（按作品分组）
  - characters.yaml   角色
  - pages.yaml        规则 / 世界观等独立页面

使用方法：
    python build_site.py                  # 默认部署到 /powerwiki
    python build_site.py --base /powerwiki

输出在 dist/，把 dist/ 内容推到 GitHub Pages 仓库即可。
维护数据只需编辑 data/*.yaml，然后重新运行本脚本。
"""

import os
import sys
import shutil
import json
import re
import yaml
import markdown

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DIST_DIR = os.path.join(BASE_DIR, 'dist')
STATIC_SRC = os.path.join(BASE_DIR, 'static')

BASE = '/powerwiki'


def slugify(text):
    """生成 URL 友好的 slug。"""
    if not text:
        return ''
    s = str(text).strip().lower()
    s = re.sub(r'[^\w一-龥]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s or 'item'


def url(path):
    path = path.lstrip('/')
    return f'{BASE}/{path}' if BASE else f'/{path}'


def load_data():
    def load(name):
        p = os.path.join(DATA_DIR, name)
        if not os.path.exists(p):
            return []
        with open(p, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data or []

    categories = load('categories.yaml')
    realms = load('realms.yaml')
    characters = load('characters.yaml')
    pages = load('pages.yaml')

    # 角色 slug 兜底 + 唯一化
    seen = set()
    for c in characters:
        s = c.get('slug') or slugify(c.get('name')) or 'char'
        if s in seen:
            s = f"{s}-{len(seen)}"
        seen.add(s)
        c['slug'] = s

    # 境界 slug 兜底 + 唯一化（按名称）
    seen_r = set()
    for r in realms:
        s = r.get('slug') or slugify(r.get('name')) or 'realm'
        if s in seen_r:
            s = f"{s}-{len(seen_r)}"
        seen_r.add(s)
        r['slug'] = s

    return categories, realms, characters, pages


def render_markdown(text):
    if not text:
        return ''
    return markdown.markdown(text, extensions=['extra', 'tables', 'toc'])


def render_markdown_full(text):
    """返回 (正文 HTML, 目录 HTML)。目录由 TOC 扩展生成，与正文标题 id 完全一致。"""
    if not text:
        return '', ''
    md = markdown.Markdown(extensions=['extra', 'tables', 'toc'])
    body = md.convert(text)
    toc = md.toc or ''
    # 移除空白 toctitle 容器（title 为空时可能残留 <div class="toctitle"></div>）
    toc = re.sub(r'<div class="toctitle">.*?</div>', '', toc, flags=re.S)
    toc = re.sub(r'<span class="toctitle">.*?</span>', '', toc, flags=re.S)
    return body, toc


# ---------------------- 页面骨架 ----------------------
def nav_links_html():
    """全局导航：固定入口 + data/pages.yaml 中的独立页面（改名后自动同步）。"""
    items = [
        (url('/index.html'), '首页'),
        (url('/characters.html'), '角色图鉴'),
        (url('/realm/index.html'), '境界体系'),
    ]
    for p in _PAGES:
        items.append((url(f"/page/{p['slug']}.html"), p['title']))
    items.append((url('/search.html'), '搜索'))
    return '\n'.join(f'                <a href="{h}">{t}</a>' for h, t in items)


def footer_nav_html():
    items = [
        (url('/index.html'), '首页'),
        (url('/characters.html'), '角色图鉴'),
        (url('/realm/index.html'), '境界体系'),
    ]
    for p in _PAGES:
        items.append((url(f"/page/{p['slug']}.html"), p['title']))
    items.append((url('/search.html'), '搜索'))
    return '\n'.join(f'                <a href="{h}">{t}</a>' for h, t in items)


def render_page(title, body, desc=''):
    meta = f'<meta name="description" content="{desc}">' if desc else ''
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {meta}
    <title>{title} - 全作品战力评鉴所</title>
    <link rel="stylesheet" href="{url('/static/css/style.css')}">
</head>
<body>
    <header class="site-header">
        <div class="container header-inner">
            <a href="{url('/index.html')}" class="logo">全作品战力评鉴所</a>
            <nav class="main-nav">
{nav_links_html()}
            </nav>
        </div>
    </header>

    <main class="main-content" id="main">
{body}
    </main>

    <footer class="site-footer">
        <div class="container footer-inner">
            <div>
                <p class="footer-brand">全作品战力评鉴所</p>
                <p class="footer-note">跨作品角色战力量级评鉴 · 静态资料站</p>
            </div>
            <nav class="footer-nav">
{footer_nav_html()}
            </nav>
        </div>
    </footer>

    <script src="{url('/static/js/main.js')}"></script>
</body>
</html>
'''


# ---------------------- 各页面构建 ----------------------
def build_index(categories, realms, characters, pages):
    power_categories = sorted(
        [c for c in categories if c.get('type', 'power') == 'power'],
        key=lambda x: x.get('sort_order', 0))
    realm_groups = {}
    for r in realms:
        realm_groups.setdefault(r.get('series') or '通用', []).append(r)
    realm_groups = dict(sorted(realm_groups.items()))

    body = f'''    <div class="container">
        <section class="hero">
            <div class="hero-inner">
                <h1>全作品战力评鉴所</h1>
                <p class="hero-sub">跨作品角色战力量级评鉴 · 境界体系收集与对照</p>
                <form action="{url('/search.html')}" method="get" class="search-form">
                    <input type="text" name="q" placeholder="搜索角色、作品、境界、量级...">
                    <button type="submit">搜索</button>
                </form>
                <div class="hero-stats">
                    <a href="{url('/characters.html')}" class="stat"><b>{len(characters)}</b><span>角色</span></a>
                    <a href="{url('/realm/index.html')}" class="stat"><b>{len(realms)}</b><span>境界</span></a>
                    <span class="stat"><b>{len(power_categories)}</b><span>量级档位</span></span>
                    <a href="{url('/page/rules.html')}" class="stat"><b>{len(pages)}</b><span>规则页</span></a>
                </div>
            </div>
        </section>
'''

    if pages:
        # 区块标题：与 data/pages.yaml 中页面性质保持一致
        # （当前收录《战力评级规则》与《材质与破坏能量数据库》）
        body += '''        <section class="panel">
            <div class="panel-header">
                <h2>规则与数据库</h2>
                <span class="panel-note">评级方法论与换算参考</span>
            </div>
            <div class="page-list">
'''
        for page in sorted(pages, key=lambda x: x.get('sort_order', 0)):
            href = url(f"/page/{page['slug']}.html")
            body += f'                <a href="{href}" class="page-tag">{page["title"]}</a>\n'
        body += '''            </div>
        </section>
'''

    if characters:
        shown = characters[:12]
        body += f'''        <section class="panel">
            <div class="panel-header">
                <h2>角色图鉴</h2>
                <a href="{url('/characters.html')}" class="btn btn-sm">查看全部 {len(characters)} 位</a>
            </div>
            <div class="character-grid">
'''
        for char in shown:
            body += character_card_html(char)
        body += '''            </div>
        </section>
'''

    body += '''        <section class="panel">
            <div class="panel-header">
                <h2>战力等级</h2>
                <span class="panel-note">由弱到强排列的量级档位</span>
            </div>
            <div class="category-grid">
'''
    for cat in power_categories:
        cnt = sum(1 for c in characters if c.get('category') == cat.get('slug'))
        body += f'''                <a href="{url(f"/category/{cat['slug']}.html")}" class="category-card">
                    <span class="cat-name">{cat['name']}</span>
                    <span class="cat-count">{cnt}</span>
                </a>
'''
    body += '''            </div>
        </section>
'''

    if realm_groups:
        body += f'''        <section class="panel">
            <div class="panel-header">
                <h2>境界体系</h2>
                <a href="{url('/realm/index.html')}" class="btn btn-sm">体系总览</a>
            </div>
            <div class="realm-system-grid">
'''
        for i, (sname, rs) in enumerate(realm_groups.items()):
            rs_sorted = sorted(rs, key=lambda x: x.get('sort_order', 0))
            ladder = ' → '.join(r['name'] for r in rs_sorted[:7])
            if len(rs_sorted) > 7:
                ladder += ' …'
            total_chars = sum(1 for c in characters if c.get('realm') in [x['name'] for x in rs_sorted])
            body += f'''                <a href="{url('/realm/index.html')}#sys-{i}" class="system-card">
                    <div class="system-head">
                        <span class="system-name">{sname}</span>
                        <span class="system-count">{len(rs_sorted)} 阶</span>
                    </div>
                    <div class="system-ladder">{ladder}</div>
                    <div class="system-meta">收录 {total_chars} 个角色</div>
                </a>
'''
        body += '''            </div>
        </section>
'''

    body += '''    </div>
'''
    write('index.html', render_page('首页', body))


def character_card_html(char):
    href = url(f"/character/{char['slug']}.html")
    img = f'<img src="{char["image_url"]}" alt="{char["name"]}">' if char.get('image_url') else '<div class="no-image">暂无图片</div>'
    cat_name = category_name_for(char)
    cat_tag = f'<span class="tag tag-power">{cat_name}</span>' if cat_name else ''
    realm_tag = f'<span class="tag tag-realm">{char["realm"]}</span>' if char.get('realm') else ''
    series_line = f'<p class="char-series">{char["series"]}</p>' if char.get('series') else ''
    return f'''                <a href="{href}" class="character-card">
                    <div class="char-image">{img}</div>
                    <div class="char-info">
                        <h3>{char['name']}</h3>
                        {series_line}
                        <div class="char-tags">{cat_tag}{realm_tag}</div>
                    </div>
                </a>
'''


def category_name_for(char):
    # 占位：实际映射在 build 中通过全局 categories 解析
    return _CAT_MAP.get(char.get('category'), '')


_CAT_MAP = {}
_CAT_ORDER = {}
# 独立页面列表（供全局导航使用，改名后导航自动同步）
_PAGES = []


def build_categories(categories, characters):
    for cat in categories:
        slug = cat['slug']
        chars = [c for c in characters if c.get('category') == slug]
        chars.sort(key=lambda x: (x.get('series') or '', x.get('name') or ''))
        body = f'''    <div class="container">
        <div class="breadcrumb">
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <span>{cat['name']}</span>
        </div>

        <section class="panel">
            <div class="panel-header">
                <h1>{cat['name']}</h1>
                <span class="badge">{len(chars)} 个角色</span>
            </div>
'''
        if cat.get('description'):
            body += f'            <p class="category-desc">{cat["description"]}</p>\n'

        if chars:
            body += '            <div class="character-grid">\n'
            for char in chars:
                body += character_card_html(char)
            body += '            </div>\n'
        else:
            body += '            <div class="empty-state"><div class="empty-icon">◇</div><h3>暂无角色</h3><p>该量级档位下还没有收录角色。</p></div>\n'

        body += '''        </section>
    </div>
'''
        write(os.path.join('category', f'{slug}.html'), render_page(cat['name'], body))


def build_characters_index(characters):
    cards = []
    for char in characters:
        img = f'<img src="{char["image_url"]}" alt="{char["name"]}">' if char.get('image_url') else '<div class="no-image">暂无图片</div>'
        cat_tag = f'<span class="tag tag-power">{_CAT_MAP.get(char.get("category"), "")}</span>' if char.get('category') else ''
        realm_tag = f'<span class="tag tag-realm">{char["realm"]}</span>' if char.get('realm') else ''
        series_line = f'<p class="char-series">{char["series"]}</p>' if char.get('series') else ''
        cards.append(f'''                <a href="{url(f"/character/{char['slug']}.html")}" class="character-card" data-name="{char['name']}" data-series="{char.get('series') or ''}">
                    <div class="char-image">{img}</div>
                    <div class="char-info">
                        <h3>{char['name']}</h3>
                        {series_line}
                        <div class="char-tags">{cat_tag}{realm_tag}</div>
                    </div>
                </a>
''')

    grid_inner = ''.join(cards) if cards else '            <div class="empty-state"><div class="empty-icon">◇</div><h3>暂无角色</h3><p>还没有收录任何角色，去 data/characters.yaml 添加吧。</p></div>\n'

    body = f'''    <div class="container">
        <div class="breadcrumb">
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <span>角色图鉴</span>
        </div>

        <section class="panel">
            <div class="panel-header">
                <h1>角色图鉴</h1>
                <span class="badge">{len(characters)} 位角色</span>
            </div>
            <div class="char-toolbar">
                <input type="text" id="name-filter" placeholder="按名称或作品快速过滤..." class="filter-input">
            </div>
            <div class="character-grid" id="char-grid">
'''
    body += grid_inner
    body += '''            </div>
            <p class="empty" id="no-result" style="display:none">没有匹配的角色</p>
        </section>
    </div>
'''
    body += CHAR_FILTER_JS
    write('characters.html', render_page('角色图鉴', body))


def build_character_detail(characters, categories, realms):
    for char in characters:
        cat = next((c for c in categories if c.get('slug') == char.get('category')), None)
        realm = next((r for r in realms if r.get('name') == char.get('realm')), None)
        img = f'<img src="{char["image_url"]}" alt="{char["name"]}">' if char.get('image_url') else '<div class="no-image">暂无图片</div>'
        alias = f'<p class="alias">别名：{char["alias"]}</p>' if char.get('alias') else ''
        cat_href = url(f"/category/{cat['slug']}.html") if cat else ''
        cat_tag = f'<a href="{cat_href}" class="tag">{cat["name"]}</a>' if cat else ''
        realm_href = url(f"/realm/{realm['slug']}.html") if realm else ''
        realm_tag = f'<a href="{realm_href}" class="tag tag-realm">{realm["name"]}</a>' if realm else ''
        series_tag = f'<span class="tag tag-series">{char["series"]}</span>' if char.get('series') else ''

        desc_html = render_markdown(char.get('description'))
        power_html = render_markdown(char.get('power_description'))

        body = f'''    <div class="container">
        <div class="breadcrumb">
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
'''
        if cat:
            body += f'''            <a href="{url(f"/category/{cat['slug']}.html")}">{cat['name']}</a>
            <span>/</span>
'''
        body += f'''            <span>{char['name']}</span>
        </div>

        <article class="detail-panel">
            <div class="detail-header">
                <div class="detail-image">{img}</div>
                <div class="detail-meta">
                    <h1>{char['name']}</h1>
                    {alias}
                    <div class="meta-tags">
                        {cat_tag}
                        {realm_tag}
                        {series_tag}
                    </div>
                </div>
            </div>

            <div class="detail-body">
'''
        if desc_html:
            body += '''                <section class="detail-section">
                    <h2>角色介绍 / 战绩</h2>
                    <div class="markdown-content">{desc_html}</div>
                </section>
'''.replace('{desc_html}', desc_html)
        if power_html:
            body += '''                <section class="detail-section">
                    <h2>能力说明</h2>
                    <div class="markdown-content">{power_html}</div>
                </section>
'''.replace('{power_html}', power_html)
        body += '''            </div>
        </article>
    </div>
'''
        write(os.path.join('character', f'{char["slug"]}.html'), render_page(char['name'], body))


def build_realm_index(realms, characters):
    groups = {}
    for r in realms:
        groups.setdefault(r.get('series') or '通用', []).append(r)
    groups = dict(sorted(groups.items()))

    body = f'''    <div class="container">
        <div class="breadcrumb">
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <span>境界体系</span>
        </div>

        <section class="panel">
            <div class="panel-header">
                <h1>境界体系总览</h1>
                <span class="badge">{len(groups)} 个作品体系 · 共 {len(realms)} 阶</span>
            </div>
            <p class="category-desc">不同作品有各自特有的境界划分。这里按作品分别收集其境界阶梯，便于跨作品对照与量级分析。</p>
        </section>
'''
    if not groups:
        body += '''        <div class="empty-state"><div class="empty-icon">◇</div><h3>暂无境界体系</h3><p>还没有收录任何作品境界。可在 data/realms.yaml 为各作品建立境界阶梯（如修真 / 龙珠 / 一拳超人等），此处将自动按作品分组展示。</p></div>
'''
    else:
        for i, (sname, rs) in enumerate(groups.items()):
            rs_sorted = sorted(rs, key=lambda x: x.get('sort_order', 0))
            total = sum(1 for c in characters if c.get('realm') in [x['name'] for x in rs_sorted])
            body += f'''        <section class="panel" id="sys-{i}">
            <div class="panel-header">
                <h2>{sname}</h2>
                <span class="badge">{len(rs_sorted)} 阶 · {total} 个角色</span>
            </div>
            <ol class="realm-ladder">
'''
            for r in rs_sorted:
                cnt = sum(1 for c in characters if c.get('realm') == r['name'])
                desc = r.get('description') or ''
                body += f'''                <li class="ladder-step">
                    <span class="step-order">{r.get('sort_order', 0)}</span>
                    <div class="step-body">
                        <a href="{url(f"/realm/{r['slug']}.html")}" class="step-name">{r['name']}</a>
                        <span class="step-desc">{desc}</span>
                    </div>
                    <span class="step-count">{cnt}</span>
                </li>
'''
            body += '''            </ol>
        </section>
'''
    body += '''    </div>
'''
    write(os.path.join('realm', 'index.html'), render_page('境界体系', body))


def build_realm_detail(realms, characters):
    for realm in realms:
        chars = [c for c in characters if c.get('realm') == realm.get('name')]
        chars.sort(key=lambda x: (x.get('series') or '', x.get('name') or ''))
        sname = realm.get('series') or '通用'
        body = f'''    <div class="container">
        <div class="breadcrumb">
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <a href="{url('/realm/index.html')}">境界体系</a>
            <span>/</span>
            <span>{sname}</span>
            <span>/</span>
            <span>{realm['name']}</span>
        </div>

        <section class="panel">
            <div class="panel-header">
                <h1>{realm['name']}</h1>
                <span class="badge">{len(chars)} 个角色</span>
            </div>
            <p class="realm-meta">
                <span class="tag tag-realm">所属体系：{sname}</span>
                <span class="tag tag-power">阶梯序位 {realm.get('sort_order', 0)}</span>
            </p>
'''
        if realm.get('description'):
            body += f'            <p class="category-desc">{realm["description"]}</p>\n'

        if chars:
            body += '            <div class="character-grid">\n'
            for char in chars:
                body += character_card_html(char)
            body += '            </div>\n'
        else:
            body += '            <div class="empty-state"><div class="empty-icon">◇</div><h3>暂无角色</h3><p>该境界下还没有收录角色。</p></div>\n'

        body += '''        </section>
    </div>
'''
        write(os.path.join('realm', f'{realm["slug"]}.html'), render_page(realm['name'], body))


def resolve_page_content(page):
    """优先读取 content_file 指向的独立 Markdown 文件（相对 data 目录），
    否则回退到内联 content。文件缺失时给出明确提示而非崩溃。"""
    cf = page.get('content_file')
    if cf:
        p = os.path.join(DATA_DIR, cf)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()
        return (f'> **内容待补充**：未在 `data/{cf}` 找到内容文件。\n>\n'
                f'> 请将对应 Markdown 放入 `data/{cf}` 后重新构建。')
    return page.get('content') or ''


def build_pages(pages):
    for page in sorted(pages, key=lambda x: x.get('sort_order', 0)):
        content_html, toc_html = render_markdown_full(resolve_page_content(page))
        if toc_html.strip():
            toc_block = f'''            <aside class="doc-toc" id="doc-toc">
                <p class="doc-toc-title">目录</p>
                <div class="doc-toc-body">
{toc_html}
                </div>
            </aside>'''
        else:
            toc_block = ''
        body = f'''    <div class="container">
        <div class="breadcrumb">
            <a class="back-btn" href="{url('/index.html')}" data-back>返回</a>
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <span aria-current="page">{page['title']}</span>
        </div>

        <div class="doc-layout" data-page-slug="{page['slug']}">
            <article class="detail-panel">
                <div class="panel-header">
                    <h1>{page['title']}</h1>
                </div>
                <div class="detail-body">
                    <div class="markdown-content">{content_html}</div>
                </div>
            </article>
{toc_block}
        </div>
    </div>
'''
        write(os.path.join('page', f'{page["slug"]}.html'), render_page(page['title'], body))


def build_search(characters, categories, realms):
    index_data = []
    for c in characters:
        index_data.append({
            'slug': c['slug'],
            'name': c.get('name', ''),
            'alias': c.get('alias', ''),
            'series': c.get('series', ''),
            'category': _CAT_MAP.get(c.get('category'), ''),
            'catOrder': _CAT_ORDER.get(c.get('category'), 0),
            'realm': c.get('realm', ''),
            'realmSeries': next((r.get('series') for r in realms if r.get('name') == c.get('realm')), '') or '',
            'realmOrder': next((r.get('sort_order', 0) for r in realms if r.get('name') == c.get('realm')), 0),
            'desc': (c.get('description') or '')[:400],
            'power': (c.get('power_description') or '')[:400],
            'image': c.get('image_url', ''),
        })
    index_json = json.dumps(index_data, ensure_ascii=False)
    base = BASE
    no_result_text = '暂无角色数据，去 data/characters.yaml 添加后重新生成即可' if not characters else '没有匹配的角色，试试放宽条件'

    body = f'''    <div class="container">
        <div class="breadcrumb">
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <span>搜索</span>
        </div>

        <section class="panel">
            <div class="panel-header">
                <h1>搜索</h1>
            </div>
            <form class="search-form inline" id="search-form">
                <input type="text" id="search-input" placeholder="角色名 / 别名 / 作品 / 境界 / 量级 / 简介关键词">
                <button type="submit">搜索</button>
            </form>

            <div class="filter-bar">
                <label>作品<select id="f-series"></select></label>
                <label>量级<select id="f-category"></select></label>
                <label>境界体系<select id="f-rseries"></select></label>
                <label>境界<select id="f-realm"></select></label>
                <label>排序
                    <select id="f-sort">
                        <option value="name">按名称</option>
                        <option value="cat">按量级高低</option>
                        <option value="realm">按境界阶序</option>
                    </select>
                </label>
                <button type="button" id="f-reset" class="btn btn-sm">重置</button>
            </div>

            <div id="active-filters" class="active-filters"></div>
            <p class="search-tip" id="search-tip"></p>
            <div id="search-results" class="character-grid"></div>
            <p class="empty" id="no-result" style="display:none">{no_result_text}</p>
        </section>
    </div>
'''
    js = SEARCH_JS_TEMPLATE.replace('/*INDEXDATA*/', index_json).replace('/*BASE*/', base)
    body += js
    write('search.html', render_page('搜索', body))


def build_404():
    body = f'''    <div class="container">
        <section class="panel">
            <div class="panel-header">
                <h1>页面不存在</h1>
            </div>
            <p class="empty">你访问的页面不存在，<a href="{url('/index.html')}">返回首页</a></p>
        </section>
    </div>
'''
    write('404.html', render_page('404', body))


# ---------------------- 脚本模板（用 token 替换避免花括号转义） ----------------------
CHAR_FILTER_JS = '''
    <script>
        (function() {
            var input = document.getElementById('name-filter');
            var cards = document.querySelectorAll('#char-grid .character-card');
            var noResult = document.getElementById('no-result');
            if (!input) return;
            input.addEventListener('input', function() {
                var q = this.value.trim().toLowerCase();
                var shown = 0;
                cards.forEach(function(c) {
                    var hay = (c.dataset.name + ' ' + c.dataset.series).toLowerCase();
                    var ok = !q || hay.indexOf(q) !== -1;
                    c.style.display = ok ? '' : 'none';
                    if (ok) shown++;
                });
                noResult.style.display = shown === 0 ? '' : 'none';
            });
        })();
    </script>
'''

SEARCH_JS_TEMPLATE = '''
    <script>
        var indexData = /*INDEXDATA*/;
        var BASE = "/*BASE*/";

        var el = function(id){ return document.getElementById(id); };
        var qEl = el('search-input'), fSeries = el('f-series'), fCat = el('f-category'),
            fRS = el('f-rseries'), fRealm = el('f-realm'), fSort = el('f-sort'),
            resultsEl = el('search-results'), tipEl = el('search-tip'),
            noRes = el('no-result'), activeBox = el('active-filters');

        var uniq = function(arr){ return Array.from(new Set(arr.filter(Boolean))).sort(function(a,b){return String(a).localeCompare(String(b),'zh');}); };

        function fillOptions(sel, values, keep) {
            sel.innerHTML = '<option value="">全部</option>' + values.map(function(v){
                return '<option value="'+v+'"'+(v===keep?' selected':'')+'>'+v+'</option>';
            }).join('');
        }

        function refreshOptions() {
            var sub = indexData.filter(function(c){
                return (!fSeries.value || c.series === fSeries.value) &&
                       (!fRS.value || c.realmSeries === fRS.value);
            });
            fillOptions(fSeries, uniq(indexData.map(function(c){return c.series;})), fSeries.value);
            fillOptions(fRS, uniq(indexData.map(function(c){return c.realmSeries;})), fRS.value);
            fillOptions(fCat, uniq(sub.map(function(c){return c.category;})), fCat.value);
            fillOptions(fRealm, uniq(sub.map(function(c){return c.realm;})), fRealm.value);
        }

        function match(c) {
            var kw = qEl.value.trim().toLowerCase();
            if (kw) {
                var hay = [c.name, c.alias, c.series, c.category, c.realm, c.realmSeries, c.desc, c.power].join(' ').toLowerCase();
                if (hay.indexOf(kw) === -1) return false;
            }
            if (fSeries.value && c.series !== fSeries.value) return false;
            if (fCat.value && c.category !== fCat.value) return false;
            if (fRS.value && c.realmSeries !== fRS.value) return false;
            if (fRealm.value && c.realm !== fRealm.value) return false;
            return true;
        }

        function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

        function render() {
            var list = indexData.filter(match);
            var s = fSort.value;
            if (s === 'cat') list.sort(function(a,b){return b.catOrder-a.catOrder;});
            else if (s === 'realm') list.sort(function(a,b){return b.realmOrder-a.realmOrder;});
            else list.sort(function(a,b){return String(a.name).localeCompare(String(b.name),'zh');});

            resultsEl.innerHTML = list.map(function(c){
                var img = c.image ? '<img src="'+esc(c.image)+'" alt="">' : '<div class="no-image">暂无图片</div>';
                return '<a href="'+BASE+'/character/'+c.slug+'.html" class="character-card">'+
                    '<div class="char-image">'+img+'</div>'+
                    '<div class="char-info"><h3>'+esc(c.name)+'</h3>'+
                    (c.series?'<p class="char-series">'+esc(c.series)+'</p>':'')+
                    '<div class="char-tags">'+
                    (c.category?'<span class="tag tag-power">'+esc(c.category)+'</span>':'')+
                    (c.realm?'<span class="tag tag-realm">'+esc(c.realm)+'</span>':'')+
                    '</div></div></a>';
            }).join('');

            noRes.style.display = list.length ? 'none' : '';
            tipEl.textContent = '匹配 ' + list.length + ' / ' + indexData.length + ' 位角色';
            renderActive();
            syncURL();
        }

        function renderActive() {
            var chips = [];
            var add = function(label, value, key){
                chips.push('<span class="chip">'+label+'：'+esc(value)+'<button type="button" data-clear="'+key+'">&times;</button></span>');
            };
            if (qEl.value.trim()) add('关键词', qEl.value.trim(), 'q');
            if (fSeries.value) add('作品', fSeries.value, 'series');
            if (fCat.value) add('量级', fCat.value, 'category');
            if (fRS.value) add('体系', fRS.value, 'rseries');
            if (fRealm.value) add('境界', fRealm.value, 'realm');
            activeBox.innerHTML = chips.join('');
            activeBox.querySelectorAll('button[data-clear]').forEach(function(btn){
                btn.addEventListener('click', function(){
                    var t = btn.dataset.clear;
                    if (t==='q') qEl.value='';
                    else if (t==='series') fSeries.value='';
                    else if (t==='category') fCat.value='';
                    else if (t==='rseries') fRS.value='';
                    else if (t==='realm') fRealm.value='';
                    refreshOptions(); render();
                });
            });
        }

        function syncURL() {
            var p = new URLSearchParams();
            if (qEl.value.trim()) p.set('q', qEl.value.trim());
            if (fSeries.value) p.set('series', fSeries.value);
            if (fCat.value) p.set('category', fCat.value);
            if (fRS.value) p.set('rseries', fRS.value);
            if (fRealm.value) p.set('realm', fRealm.value);
            var qs = p.toString();
            history.replaceState(null, '', qs ? ('?'+qs) : location.pathname);
        }

        function readURL() {
            var p = new URLSearchParams(location.search);
            qEl.value = p.get('q') || '';
            fSeries.value = p.get('series') || '';
            fRS.value = p.get('rseries') || '';
            fCat.value = p.get('category') || '';
            fRealm.value = p.get('realm') || '';
        }

        el('search-form').addEventListener('submit', function(e){ e.preventDefault(); render(); });
        qEl.addEventListener('input', render);
        [fSeries, fCat, fRS, fRealm, fSort].forEach(function(sel){
            sel.addEventListener('change', function(){ refreshOptions(); render(); });
        });
        el('f-reset').addEventListener('click', function(){
            qEl.value=''; fSeries.value=''; fCat.value=''; fRS.value=''; fRealm.value=''; fSort.value='name';
            refreshOptions(); render();
        });

        readURL();
        refreshOptions();
        render();
    </script>
'''


# ---------------------- 输出 ----------------------
def write(rel, content):
    path = os.path.join(DIST_DIR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def copy_static():
    os.makedirs(os.path.join(DIST_DIR, 'static', 'css'), exist_ok=True)
    os.makedirs(os.path.join(DIST_DIR, 'static', 'js'), exist_ok=True)
    css_src = os.path.join(STATIC_SRC, 'css', 'style.css')
    if os.path.exists(css_src):
        shutil.copy2(css_src, os.path.join(DIST_DIR, 'static', 'css', 'style.css'))
    js_src = os.path.join(STATIC_SRC, 'js', 'main.js')
    if os.path.exists(js_src):
        shutil.copy2(js_src, os.path.join(DIST_DIR, 'static', 'js', 'main.js'))
    uploads_src = os.path.join(STATIC_SRC, 'uploads')
    if os.path.exists(uploads_src):
        shutil.copytree(uploads_src, os.path.join(DIST_DIR, 'static', 'uploads'), dirs_exist_ok=True)
    with open(os.path.join(DIST_DIR, '.nojekyll'), 'w') as f:
        f.write('')


def main():
    global BASE, _CAT_MAP, _CAT_ORDER, _PAGES
    if '--base' in sys.argv:
        idx = sys.argv.index('--base')
        if idx + 1 < len(sys.argv):
            BASE = sys.argv[idx + 1].strip().rstrip('/')
    elif os.environ.get('SITE_BASE') is not None:
        BASE = os.environ.get('SITE_BASE').strip().rstrip('/')

    categories, realms, characters, pages = load_data()

    # 分类映射（slug -> name / sort_order），供卡片与搜索使用
    _CAT_MAP = {c['slug']: c['name'] for c in categories}
    _CAT_ORDER = {c['slug']: c.get('sort_order', 0) for c in categories}
    # 供全局导航渲染（按 sort_order 排序）
    _PAGES = sorted(pages, key=lambda x: x.get('sort_order', 0))

    print('=' * 55)
    print('生成静态站点（文件式，无后端）...')
    print(f'站点路径：{BASE if BASE else "/（根路径）"}')
    print(f'数据：分类 {len(categories)} · 境界 {len(realms)} · 角色 {len(characters)} · 页面 {len(pages)}')
    print('=' * 55)

    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    for sub in ['character', 'category', 'realm', 'page', 'static/css', 'static/js']:
        os.makedirs(os.path.join(DIST_DIR, sub), exist_ok=True)

    print('\n[1/9] 复制静态资源...')
    copy_static()

    print('[2/9] 生成首页...')
    build_index(categories, realms, characters, pages)

    print('[3/9] 生成分类页...')
    build_categories(categories, characters)

    print('[4/9] 生成角色页...')
    build_characters_index(characters)
    build_character_detail(characters, categories, realms)

    print('[5/9] 生成境界页...')
    build_realm_index(realms, characters)
    build_realm_detail(realms, characters)

    print('[6/9] 生成规则页面...')
    build_pages(pages)

    print('[7/9] 生成搜索页...')
    build_search(characters, categories, realms)

    print('[8/9] 生成 404...')
    build_404()

    print('\n' + '=' * 55)
    print('导出完成！输出目录：', DIST_DIR)
    print('把 dist 目录内容推到 GitHub Pages 仓库即可。')
    print('=' * 55)


if __name__ == '__main__':
    main()
