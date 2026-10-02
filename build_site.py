"""
文件式静态站点生成器（无 Flask / 无 SQLite 依赖）

数据来源：data/ 下的可编辑 YAML 文件
  - categories.yaml   战力量级体系表（分组 + 档位），首页「战力等级」、
                      「量级体系表」页、分类页、搜索筛选器全部由它驱动
  - realms.yaml       境界体系（按作品分组）
  - characters.yaml   角色
  - pages.yaml        规则 / 世界观等独立页面（正文在 data/pages/*.md）

档位与规则原文的同步：categories.yaml 里每个档位的 source 字段写 rules.md 的
小节标题，构建时自动解析成该页的锚点，分类页与量级体系表页都能一键跳到原文。

使用方法：
    python build_site.py                       # 只构建到 dist/
    python build_site.py --base /powerwiki     # 指定站点子路径
    python build_site.py --deploy-root         # 构建并把产物同步到仓库根目录
                                               # （GitHub Pages 直接读根目录）
    python build_site.py --check               # 只校验数据一致性，不写文件

--deploy-root 会按 .site-manifest.json 清掉上一次生成、这一次已不存在的文件
（例如废弃档位留下的 category/xxx.html），源码文件不在清单里，不会被误删。

维护数据只需编辑 data/*.yaml 与 data/pages/*.md，然后重新运行本脚本。
"""

import os
import sys
import shutil
import json
import re
from urllib.parse import quote
import yaml
import markdown
from markdown.extensions.toc import slugify_unicode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DIST_DIR = os.path.join(BASE_DIR, 'dist')
STATIC_SRC = os.path.join(BASE_DIR, 'static')
MANIFEST_NAME = '.site-manifest.json'

BASE = '/powerwiki'
# 实际写盘目录：默认 dist/，--deploy-root 时同步阶段写仓库根目录
OUT_DIR = DIST_DIR
# 本次构建产出的相对路径清单（写盘时登记，用于下次清理孤儿文件）
_MANIFEST = []
# 只做数据校验、不写任何文件
CHECK_ONLY = False


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

    raw_categories = load('categories.yaml')
    # categories.yaml 支持两种写法：
    #   1) {groups: [...], items: [...]}  —— 现行写法，带体系分段
    #   2) [...]                          —— 旧的扁平写法，全部归入默认分段
    if isinstance(raw_categories, dict):
        categories = raw_categories.get('items') or []
        groups = raw_categories.get('groups') or []
    else:
        categories = raw_categories
        groups = []
    realms = load('realms.yaml')
    characters = load('characters.yaml')
    pages = load('pages.yaml')

    # 档位 slug 兜底 + 唯一化
    seen_c = set()
    for c in categories:
        s = c.get('slug') or slugify(c.get('name')) or 'tier'
        if s in seen_c:
            s = f"{s}-{len(seen_c)}"
        seen_c.add(s)
        c['slug'] = s

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

    # 档位卡片背景图（categories.yaml 的 backgrounds 块，外链不入库）
    if isinstance(raw_categories, dict):
        load_backgrounds(raw_categories)

    return categories, groups, realms, characters, pages


def validate_data(categories, groups, realms, characters, pages):
    """构建前的一致性自检。返回问题列表；有 error 级问题时构建中止。

    这一层是「档位表 ↔ 首页战力等级 ↔ 分类页 ↔ 搜索筛选器」保持同步的保险：
    任何一处数据写歪（重名 slug、排序值撞车、分段没定义、角色挂在废弃档上），
    都会在构建时直接报出来，而不是生成一个页面缺失的站点。
    """
    errors, warnings = [], []

    slugs = [c.get('slug') for c in categories]
    dup = {s for s in slugs if slugs.count(s) > 1}
    if dup:
        errors.append(f"档位 slug 重复：{', '.join(sorted(dup))}")

    names = [c.get('name') for c in categories]
    dupn = {n for n in names if names.count(n) > 1}
    if dupn:
        warnings.append(f"档位名重复（不影响构建，但搜索筛选会混）：{', '.join(sorted(map(str, dupn)))}")

    orders = [c.get('sort_order') for c in categories]
    dupo = {o for o in orders if orders.count(o) > 1}
    if dupo:
        errors.append(f"档位 sort_order 重复，首页排序会不稳定：{sorted(dupo, key=str)}")

    group_ids = [g.get('id') for g in groups]
    dupg = {g for g in group_ids if group_ids.count(g) > 1}
    if dupg:
        errors.append(f"分段 id 重复：{', '.join(sorted(dupg))}")
    for c in categories:
        if groups and c.get('group') not in group_ids:
            errors.append(f"档位 {c.get('slug')} 的 group「{c.get('group')}」未在 groups 中定义")

    # 未归档兜底档必须在最末（用户约定：「未知/暂存」排在战力等级最后）
    if categories:
        ordered = sorted(categories, key=lambda x: x.get('sort_order', 0))
        tail = [c.get('slug') for c in ordered if c.get('group') == 'unfiled']
        if tail and [c.get('slug') for c in ordered[-len(tail):]] != tail:
            errors.append(f"未归档档（{', '.join(tail)}）必须排在最末")

    # 角色引用检查：挂在已废弃/不存在的档位或境界上
    cat_slugs = set(slugs)
    realm_names = {r.get('name') for r in realms}
    for ch in characters:
        if ch.get('category') and ch['category'] not in cat_slugs:
            errors.append(f"角色「{ch.get('name')}」挂在不存在的档位 slug「{ch['category']}」上（旧框架档位已废弃，请改挂新档）")
        if ch.get('realm') and realms and ch['realm'] not in realm_names:
            warnings.append(f"角色「{ch.get('name')}」的境界「{ch['realm']}」未在 realms.yaml 中定义")

    # 独立页面正文检查
    for p in pages:
        cf = p.get('content_file')
        if cf and not os.path.exists(os.path.join(DATA_DIR, cf)):
            errors.append(f"页面 {p.get('slug')} 的正文文件 data/{cf} 不存在")
        if not cf and not p.get('content'):
            warnings.append(f"页面 {p.get('slug')} 既无 content_file 也无 content")

    # 档位 source 能否在规则页里找到对应小节（找不到只是少一个跳转链接）
    if _PAGE_ANCHORS.get('rules'):
        anchors = _PAGE_ANCHORS['rules']
        for c in categories:
            src = c.get('source')
            if src and src not in anchors:
                warnings.append(f"档位 {c.get('slug')} 的 source「{src}」在 rules.md 中找不到同名小节，已省略原文跳转")

    return errors, warnings



def render_markdown(text):
    if not text:
        return ''
    return markdown.markdown(text, extensions=['extra', 'tables', 'toc'],
                             extension_configs=TOC_CONFIG)


# TOC 配置：用 unicode slugify，中文标题也能得到可读、可外链的锚点
# （默认 slugify 会把中文全部剥掉，导致 rules.html 的锚点退化成 _1 / _2 / 13 这种
#   无意义 id，档位页没法精确跳到体系表原文对应小节）
TOC_CONFIG = {'toc': {'slugify': slugify_unicode, 'toc_depth': '1-3', 'separator': '-'}}


def render_markdown_full(text):
    """返回 (正文 HTML, 目录 HTML, 标题文本->锚点 id 映射)。

    目录由 TOC 扩展生成，与正文标题 id 完全一致；锚点映射供 categories.yaml
    的 source 字段解析成「跳到规则原文对应小节」的链接。
    """
    if not text:
        return '', '', {}
    md = markdown.Markdown(extensions=['extra', 'tables', 'toc'],
                           extension_configs=TOC_CONFIG)
    body = md.convert(text)
    toc = md.toc or ''
    anchors = {}

    def walk(tokens):
        for t in tokens or []:
            name = (t.get('name') or '').strip()
            if name and t.get('id'):
                anchors.setdefault(name, t['id'])
            walk(t.get('children'))

    walk(getattr(md, 'toc_tokens', []))
    # 移除空白 toctitle 容器（title 为空时可能残留 <div class="toctitle"></div>）
    toc = re.sub(r'<div class="toctitle">.*?</div>', '', toc, flags=re.S)
    toc = re.sub(r'<span class="toctitle">.*?</span>', '', toc, flags=re.S)
    return body, toc, anchors


# ---------------------- 页面骨架 ----------------------
def nav_links_html():
    """全局导航：固定入口 + data/pages.yaml 中的独立页面（改名后自动同步）。"""
    items = [
        (url('/index.html'), '首页'),
        (url('/characters.html'), '角色图鉴'),
        (url('/realm/index.html'), '境界体系'),
        (url(f'/page/{TIERS_PAGE_SLUG}.html'), TIERS_PAGE_TITLE),
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
        (url(f'/page/{TIERS_PAGE_SLUG}.html'), TIERS_PAGE_TITLE),
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
    <script>document.documentElement.className += ' js';</script>
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


# ---------------------- 档位（战力量级）渲染 ----------------------
def html_escape(text, attr=False):
    """HTML 转义。attr=True 时额外转义引号，用于 title / alt 等属性位。"""
    if text is None:
        return ''
    s = str(text)
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if attr:
        s = s.replace('"', '&quot;').replace("'", '&#39;')
    return s


def ordered_power_categories(categories):
    """战力档位按 sort_order 由弱到强排序。"""
    return sorted([c for c in categories if c.get('type', 'power') == 'power'],
                  key=lambda x: x.get('sort_order', 0))


def group_display(gid):
    return (_GROUP_MAP.get(gid) or {}).get('name') or gid


def group_note(gid):
    return (_GROUP_MAP.get(gid) or {}).get('note') or ''


def tier_energy_label(cat):
    """档位卡片上显示的能量口径；兜底档不在能量轴上。"""
    e = (cat.get('energy') or '').strip()
    if e:
        return e
    return '兜底档' if cat.get('group') == 'unfiled' else '未定档'


def char_counts(characters):
    counts = {}
    for ch in characters:
        counts[ch.get('category')] = counts.get(ch.get('category'), 0) + 1
    return counts


def tier_card_html(cat, count):
    tip = cat.get('name') or ''
    if cat.get('parent'):
        tip += f"｜所属量级：{cat['parent']}"
    if cat.get('energy'):
        tip += f"｜{cat['energy']}"
    href = url(f"/category/{cat['slug']}.html")
    count_attr = ' data-empty' if count == 0 else ''
    # 背景图：外链、不入库。主源写在内联 style 里（无 JS 也能看到），
    # 备源放 data-bg-alt，由 main.js 在主源加载失败时顶上；都失败就撤掉底图。
    bg_style = ''
    bg_class = ''
    bg_attr = ''
    urls = tier_bg_urls(cat)
    if urls:
        bg_class = ' has-bg'
        bg_style = (
            f" style=\"--tier-bg:url('{html_escape(urls[0], True)}');"
            f"--tier-bg-opacity:{_BG_OPACITY}\""
        )
        bg_attr = f' data-bg="{html_escape(urls[0], True)}"'
        if len(urls) > 1:
            bg_attr += f' data-bg-alt="{html_escape(urls[1], True)}"'
    return (
        f'                <a href="{href}" class="category-card{bg_class}"{bg_style}{bg_attr}'
        f' title="{html_escape(tip, True)}">\n'
        f'                    <span class="cat-name">{html_escape(cat.get("name"))}</span>\n'
        f'                    <span class="cat-count"{count_attr}>{count}</span>\n'
        f'                    <span class="cat-energy">{html_escape(tier_energy_label(cat))}</span>\n'
        f'                </a>\n'
    )


def tier_groups_html(power_categories, characters):
    """按体系分段渲染档位网格。

    严格按 sort_order 由弱到强遍历，分段切换时才插入分段标题——过渡带 A / B
    因此各自出现在能量轴上的真实位置，而不是被归拢到一起打乱强弱顺序。
    """
    counts = char_counts(characters)
    tiers_href = url(f'/page/{TIERS_PAGE_SLUG}.html')
    segments = iter_segments(power_categories)
    out = []
    for seg in segments:
        note = group_note(seg['gid'])
        note_html = (f'\n                <p class="tier-group-note">{html_escape(note)}</p>'
                     if note else '')
        out.append(
            f'            <div class="tier-group" id="group-{seg["key"]}">\n'
            f'                <div class="tier-group-head">\n'
            f'                    <h3 class="tier-group-name">{html_escape(seg["label"])}</h3>\n'
            f'                    <span class="tier-group-meta">{len(seg["members"])} 档 · {html_escape(seg["span"])}</span>\n'
            f'                    <a class="tier-group-link" href="{tiers_href}#group-{seg["key"]}">体系表</a>\n'
            f'                </div>{note_html}\n'
            f'                <div class="category-grid">\n'
        )
        for cat in seg['members']:
            out.append(tier_card_html(cat, counts.get(cat.get('slug'), 0)))
        out.append('                </div>\n            </div>\n')
    return ''.join(out)


def rules_source_link(cat):
    """把档位的 source（rules.md 小节标题）解析成规则页深链，返回 (href, 标题)。"""
    src = (cat.get('source') or '').strip()
    if not src:
        return '', ''
    aid = (_PAGE_ANCHORS.get('rules') or {}).get(src)
    href = url(f'/page/rules.html#{aid}') if aid else url('/page/rules.html')
    return href, src


def iter_segments(power_categories):
    """把按强弱排序的档位切成连续分段。

    同一个 group 可能被其它分段（如过渡带 B）从中间切开，切成几段就是几段：
    每段的 key 形如「cover」「cover-2」，段内档位在能量轴上严格相邻。
    分段标题因此不会重复、锚点也不会撞 id。
    """
    segments, seen = [], {}
    for cat in power_categories:
        gid = cat.get('group') or 'misc'
        if not segments or segments[-1]['gid'] != gid:
            seen[gid] = seen.get(gid, 0) + 1
            key = gid if seen[gid] == 1 else f'{gid}-{seen[gid]}'
            segments.append({'key': key, 'gid': gid, 'members': []})
        segments[-1]['members'].append(cat)
    for seg in segments:
        members = seg['members']
        if len(members) > 1:
            seg['span'] = f"{members[0]['name']} → {members[-1]['name']}"
        else:
            seg['span'] = members[0]['name']
        if seg['gid'] in seen and sum(1 for x in segments if x['gid'] == seg['gid']) > 1:
            idx = [x['key'] for x in segments if x['gid'] == seg['gid']].index(seg['key'])
            total = sum(1 for x in segments if x['gid'] == seg['gid'])
            seg['label'] = f"{group_display(seg['gid'])}（{idx + 1}/{total}）"
        else:
            seg['label'] = group_display(seg['gid'])
    return segments


def tier_position(power_categories, slug):
    """返回 (本档序号, 总档数, 上一档, 下一档)。

    强弱轴只包含参与排序的档位；未归档的兜底档（未知/暂存）不在轴上，
    查询它时返回 (0, 排名档总数, None, None) —— 它既不是最强也不是最弱。
    """
    ranked = [c for c in power_categories if c.get('group') != 'unfiled']
    for i, c in enumerate(ranked):
        if c.get('slug') == slug:
            prev_c = ranked[i - 1] if i > 0 else None
            next_c = ranked[i + 1] if i + 1 < len(ranked) else None
            return i + 1, len(ranked), prev_c, next_c
    return 0, len(ranked), None, None

# ---------------------- 各页面构建 ----------------------
def build_index(categories, groups, realms, characters, pages):
    power_categories = ordered_power_categories(categories)
    tiers_href = url(f'/page/{TIERS_PAGE_SLUG}.html')
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
                    <a href="{tiers_href}" class="stat"><b>{len(power_categories)}</b><span>量级档位</span></a>
                    <a href="{url('/page/rules.html')}" class="stat"><b>{len(pages)}</b><span>规则页</span></a>
                </div>
            </div>
        </section>
'''

    if pages or power_categories:
        # 区块标题：与 data/pages.yaml 中页面性质保持一致
        # （当前收录《战力评级规则》与《材质与破坏能量数据库》）
        body += f'''        <section class="panel">
            <div class="panel-header">
                <h2>规则与数据库</h2>
                <span class="panel-note">评级方法论与换算参考</span>
            </div>
            <div class="page-list">
                <a href="{url(f'/page/{TIERS_PAGE_SLUG}.html')}" class="page-tag">{TIERS_PAGE_TITLE} · {len(power_categories)} 档</a>
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

    body += f'''        <section class="panel">
            <div class="panel-header">
                <h2>战力等级</h2>
                <a href="{tiers_href}" class="btn btn-sm">量级体系表 · {len(power_categories)} 档</a>
            </div>
            <p class="tier-intro">与《战力评级规则》的战力量级体系表同源同步，由弱到强按体系分段排列；每档标注能量区间，点击卡片查看该档角色。</p>
            <div class="tier-groups">
{tier_groups_html(power_categories, characters)}            </div>
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


def character_card_html(char, power_categories=None):
    href = url('/character/%s.html' % char['slug'])
    name = html_escape(char.get('name'))
    if char.get('image_url'):
        img = '<img src="%s" alt="%s">' % (html_escape(char['image_url'], True), html_escape(char.get('name'), True))
    else:
        img = '<div class="no-image">暂无图片</div>'
    cat = _CAT_BY_SLUG.get(char.get('category')) or {}
    cat_name = cat.get('name') or ''
    cat_tag = ''
    if cat_name:
        tip = cat_name
        if cat.get('energy'):
            tip += '｜' + cat['energy']
        cat_tag = ('<span class="tag tag-power" title="%s">%s</span>'
                   % (html_escape(tip, True), html_escape(cat_name)))
    realm_tag = ('<span class="tag tag-realm">%s</span>' % html_escape(char['realm'])
                 if char.get('realm') else '')
    series_line = ('<p class="char-series">%s</p>' % html_escape(char['series'])
                   if char.get('series') else '')
    return (f'                <a href="{href}" class="character-card">\n'
            f'                    <div class="char-image">{img}</div>\n'
            f'                    <div class="char-info">\n'
            f'                        <h3>{name}</h3>\n'
            f'                        {series_line}\n'
            f'                        <div class="char-tags">{cat_tag}{realm_tag}</div>\n'
            f'                    </div>\n'
            f'                </a>\n')


def category_name_for(char):
    # 占位：实际映射在 build 中通过全局 categories 解析
    return _CAT_MAP.get(char.get('category'), '')


_CAT_MAP = {}
_CAT_ORDER = {}
_CAT_BY_SLUG = {}
# 体系分段（categories.yaml 的 groups），按档位在表中首次出现的顺序展示
_GROUP_MAP = {}
_GROUPS_ORDERED = []
# 独立页面列表（供全局导航使用，改名后导航自动同步）
_PAGES = []
# page slug -> {标题文本: 锚点 id}，把档位的 source 解析成规则原文深链
_PAGE_ANCHORS = {}
# page slug -> (正文 HTML, 目录 HTML)，避免同一份 Markdown 渲染两遍
_PAGE_CACHE = {}
# 档位卡片背景图配置（categories.yaml 的 backgrounds 块）
_BG_ENABLED = False
_BG_OPACITY = 0.15
_BG_URLS = {}   # slug -> [主源 URL, 备源 URL, ...]


def load_backgrounds(raw):
    """解析 categories.yaml 的 backgrounds 块。

    图源全部走外链，不下载进仓库。占位符 {slug}/{w}/{h}/{cat} 在渲染时替换。
    seed 取档位 slug，所以同一档位永远拿到同一张图；
    cat 取题材，由 cat_by_slug → cat_by_parent → default_cat 三级查表得到，
    让底图内容跟档位的量级语义对上（爆砖→石头、爆恒星→太空…）。
    """
    global _BG_ENABLED, _BG_OPACITY, _BG_URLS
    _BG_ENABLED, _BG_OPACITY, _BG_URLS = False, 0.10, {}
    if not isinstance(raw, dict):
        raw = {}
    cfg = raw.get('backgrounds') or {}
    if not cfg.get('enabled'):
        return
    sources = [str(s).strip() for s in (cfg.get('sources') or []) if str(s).strip()]
    if not sources:
        return
    try:
        w = int(cfg.get('width') or 400)
        h = int(cfg.get('height') or 300)
    except (TypeError, ValueError):
        w, h = 400, 300
    try:
        op = float(cfg.get('opacity'))
        if not 0 < op <= 1:
            raise ValueError
    except (TypeError, ValueError):
        op = 0.10

    by_slug = cfg.get('cat_by_slug') or {}
    by_parent = cfg.get('cat_by_parent') or {}
    default_cat = cfg.get('default_cat')

    _BG_ENABLED = True
    _BG_OPACITY = op
    for cat in raw.get('items') or []:
        slug = cat.get('slug')
        if not slug:
            continue
        topic = (by_slug.get(slug)
                 or by_parent.get(cat.get('parent'))
                 or default_cat)
        if not topic:
            continue
        # 题材是中文，URL 里要 percent-encode
        _BG_URLS[slug] = [
            s.format(slug=slug, w=w, h=h, cat=quote(str(topic), safe=''))
            for s in sources
        ]


def tier_bg_urls(cat):
    """该档位卡片的背景图候选 URL（按优先级）。未启用时返回空列表。"""
    if not _BG_ENABLED:
        return []
    return _BG_URLS.get(cat.get('slug')) or []

# 量级体系表页：由 categories.yaml 直接生成，与首页「战力等级」同源同步
TIERS_PAGE_SLUG = 'tiers'
TIERS_PAGE_TITLE = '量级体系表'


def build_categories(categories, characters, power_categories=None):
    """分类（档位）详情页。

    页面内容由 categories.yaml 的字段驱动：所属量级、体系分段、能量区间、
    覆盖尺度、判定要点、体系内位次（上一档 / 下一档）、规则原文深链。
    """
    ordered = power_categories if power_categories is not None else ordered_power_categories(categories)
    for cat in ordered:
        slug = cat['slug']
        chars = [c for c in characters if c.get('category') == slug]
        chars.sort(key=lambda x: (x.get('series') or '', x.get('name') or ''))
        pos, total, prev_c, next_c = tier_position(ordered, slug)
        src_href, src_title = rules_source_link(cat)

        body = f'''    <div class="container">
        <div class="breadcrumb">
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <a href="{url(f'/page/{TIERS_PAGE_SLUG}.html')}">{TIERS_PAGE_TITLE}</a>
            <span>/</span>
            <span>{cat['name']}</span>
        </div>

        <section class="panel">
            <div class="panel-header">
                <h1>{cat['name']}</h1>
                <span class="badge">{len(chars)} 个角色</span>
            </div>
            <div class="tier-meta">
'''
        meta_rows = [
            ('所属量级', cat.get('parent') or '—'),
            ('体系分段', group_display(cat.get('group'))),
            ('能量区间', cat.get('energy') or '—'),
            ('覆盖尺度', cat.get('scale') or '—'),
            ('体系位次', (f"第 {pos} / {total} 档" if pos
                        else f"兜底档 · 不参与强弱排序（共 {total} 档正式量级）")),
        ]
        for label, value in meta_rows:
            body += (f'                <div class="tier-meta-row">'
                     f'<span class="tier-meta-k">{label}</span>'
                     f'<span class="tier-meta-v">{html_escape(value)}</span></div>\n')
        if src_href:
            body += (f'                <div class="tier-meta-row">'
                     f'<span class="tier-meta-k">规则原文</span>'
                     f'<span class="tier-meta-v"><a href="{src_href}">'
                     f'{html_escape(src_title)} →</a></span></div>\n')
        body += '''            </div>
'''
        if cat.get('note'):
            body += f'            <p class="category-desc">{html_escape(cat.get("note"))}</p>\n'

        # 上/下一档快捷跳转（强弱轴上的相邻档，不是分段内相邻）
        if cat.get('group') == 'unfiled':
            # 兜底档不在强弱轴上，给它「更强/更弱」标签是错的
            body += ('            <div class="tier-nav tier-nav--flat">\n'
                     '                <span class="tier-nav-note">本档为体系之外的兜底档，'
                     '不与正式量级比较强弱；补齐材料后应转出到对应档位。</span>\n'
                     '            </div>\n')
        elif prev_c or next_c:
            body += '            <div class="tier-nav">\n'
            if prev_c:
                prev_href = url('/category/%s.html' % prev_c['slug'])
                body += (f'                <a class="tier-nav-item" href="{prev_href}">'
                         f'<span class="tier-nav-dir">← 更弱</span>'
                         f'<span class="tier-nav-name">{html_escape(prev_c["name"])}</span></a>\n')
            else:
                body += ('                <span class="tier-nav-item is-edge">'
                         '<span class="tier-nav-dir">←</span>'
                         '<span class="tier-nav-name">体系最弱档</span></span>\n')
            if next_c:
                next_href = url('/category/%s.html' % next_c['slug'])
                body += (f'                <a class="tier-nav-item" href="{next_href}">'
                         f'<span class="tier-nav-dir">更强 →</span>'
                         f'<span class="tier-nav-name">{html_escape(next_c["name"])}</span></a>\n')
            else:
                body += ('                <span class="tier-nav-item is-edge">'
                         '<span class="tier-nav-dir">→</span>'
                         '<span class="tier-nav-name">体系最强档</span></span>\n')
            body += '            </div>\n'

        if chars:
            body += '            <div class="character-grid">\n'
            for char in chars:
                body += character_card_html(char, ordered)
            body += '            </div>\n'
        else:
            body += ('            <div class="empty-state"><div class="empty-icon">◇</div>'
                     '<h3>暂无角色</h3><p>该量级档位下还没有收录角色。</p></div>\n')

        body += '''        </section>
    </div>
'''
        write(os.path.join('category', f'{slug}.html'), render_page(cat['name'], body))


def build_tiers_page(categories, characters):
    """量级体系表页：categories.yaml 的完整展开版。

    与首页「战力等级」读同一份数据、用同一个渲染函数，只是多出能量区间、
    覆盖尺度、判定要点、规则原文深链四列，并把兜底档明确标注。
    """
    power_categories = ordered_power_categories(categories)
    counts = char_counts(characters)
    rules_href = url('/page/rules.html')
    segments = iter_segments(power_categories)
    toc_block = toc_block_html(build_tiers_toc(segments))

    body = f'''    <div class="container">
        <div class="breadcrumb">
            <a class="back-btn" href="{url('/index.html')}" data-back>返回</a>
            <a href="{url('/index.html')}">首页</a>
            <span>/</span>
            <span aria-current="page">{TIERS_PAGE_TITLE}</span>
        </div>

        <div class="doc-layout" data-page-slug="{TIERS_PAGE_SLUG}">
            <article class="detail-panel">
                <div class="panel-header">
                    <h1>{TIERS_PAGE_TITLE}</h1>
                </div>
                <p class="tier-intro">
                    共 <b>{len(power_categories)}</b> 个量级档位，由弱到强排列。本表与
                    <a href="{rules_href}">《战力评级规则》</a> 的战力量级体系表一一对应：
                    档位名取自 1.3 量级表与第三、四部分的定级口径，能量区间与覆盖尺度照抄原文。
                    每档右侧「规则原文」可跳到《战力评级规则》的对应小节。
                </p>
'''
    for seg in iter_segments(power_categories):
        note = group_note(seg['gid'])
        note_html = (f'\n                    <p class="tier-group-note">{html_escape(note)}</p>'
                     if note else '')
        body += f"""        <section class="panel tier-section" id="group-{seg['key']}">
            <div class="panel-header">
                <h2>{html_escape(seg['label'])}</h2>
                <span class="badge">{len(seg['members'])} 档</span>
            </div>{note_html}
            <table class="tier-table">
                <thead>
                    <tr>
                        <th class="col-pos">#</th>
                        <th class="col-name">档位</th>
                        <th class="col-parent">所属量级</th>
                        <th class="col-energy">能量区间</th>
                        <th class="col-scale">覆盖尺度 / 参照</th>
                        <th class="col-count">角色</th>
                        <th class="col-src">规则原文</th>
                    </tr>
                </thead>
                <tbody>
"""
        for cat in seg['members']:
            pos, total, _, _ = tier_position(power_categories, cat.get('slug'))
            src_href, src_title = rules_source_link(cat)
            cnt = counts.get(cat.get('slug'), 0)
            cat_href = url('/category/%s.html' % cat.get('slug'))
            name_html = (f'<a href="{cat_href}">'
                         f'{html_escape(cat.get("name"))}</a>')
            note_cell = (f'<p class="tier-note">{html_escape(cat.get("note"))}</p>'
                         if cat.get('note') else '')
            src_html = (f'<a href="{src_href}" class="tier-src">{html_escape(src_title)}</a>'
                        if src_href else '<span class="tier-src muted">—</span>')
            # data-label：移动端隐藏表头后，靠它渲染中文列名
            cells = [
                # 兜底档不在强弱轴上，位次列给「—」而不是 0 或 92
                ('col-pos', '位次', str(pos) if pos else '—'),
                ('col-name', '档位', name_html + note_cell),
                ('col-parent', '量级', html_escape(cat.get('parent') or '—')),
                ('col-energy', '能量', html_escape(tier_energy_label(cat))),
                ('col-scale', '尺度', html_escape(cat.get('scale') or '—')),
                ('col-count', '角色', str(cnt)),
                ('col-src', '原文', src_html),
            ]
            body += (f'                    <tr id="tier-{cat.get("slug")}">\n')
            for cls, label, value in cells:
                body += (f'                        <td class="{cls}" data-label="{label}">'
                         f'{value}</td>\n')
            body += '                    </tr>\n'
        body += '                </tbody>\n            </table>\n        </section>\n'

    body += f'''
        <section class="panel">
            <div class="panel-header">
                <h2>阅读口径</h2>
            </div>
            <div class="markdown-content">
                <ul>
                    <li><b>排序</b>：由弱到强，首页与本表共用同一顺序。</li>
                    <li><b>分段</b>：对应《战力评级规则》的体系分段，按档位在能量轴上的真实位置切分。
                        因此过渡带 A / B 各自单列，不与相邻量级归拢，避免打乱强弱顺序；
                        同一分段被过渡带隔开时会标注（1/2）、（2/2）。</li>
                    <li><b>能量与尺度</b>：能量区间为焦耳，覆盖尺度给出该档的典型参照物；
                        论外级已不在能量轴上，改按规模与结构标注。</li>
                    <li><b>兜底档</b>：末尾「未知/暂存」不属于任何体系分段，不参与强弱排序。
                        <b>未知</b>——信息不足、连区间都圈不出来；
                        <b>暂存</b>——区间已可圈定、只差坐实（若证明高估则下调至对应正式档）。</li>
                    <li><b>规则原文</b>：每档末列可跳转到《战力评级规则》中定级该档的小节。</li>
                </ul>
            </div>
        </section>
            </article>
{toc_block}
        </div>
    </div>
'''
    write(os.path.join('page', f'{TIERS_PAGE_SLUG}.html'), render_page(TIERS_PAGE_TITLE, body))

def build_characters_index(characters, power_categories=None):
    cards = []
    for char in characters:
        href = url('/character/%s.html' % char['slug'])
        img = ('<img src="%s" alt="%s">' % (html_escape(char['image_url'], True), html_escape(char.get('name'), True))
               if char.get('image_url') else '<div class="no-image">暂无图片</div>')
        cat = _CAT_BY_SLUG.get(char.get('category')) or {}
        cat_tag = ('<span class="tag tag-power">%s</span>' % html_escape(cat.get('name'))
                   if cat.get('name') else '')
        realm_tag = ('<span class="tag tag-realm">%s</span>' % html_escape(char['realm'])
                     if char.get('realm') else '')
        series_line = ('<p class="char-series">%s</p>' % html_escape(char['series'])
                       if char.get('series') else '')
        cards.append(f'''                <a href="{href}" class="character-card" data-name="{html_escape(char.get('name'), True)}" data-series="{html_escape(char.get('series') or '', True)}">
                    <div class="char-image">{img}</div>
                    <div class="char-info">
                        <h3>{html_escape(char.get('name'))}</h3>
                        {series_line}
                        <div class="char-tags">{cat_tag}{realm_tag}</div>
                    </div>
                </a>
''')

    grid_inner = ''.join(cards) if cards else '            <div class="empty-state"><div class="empty-icon">◇</div><h3>暂无角色</h3><p>角色图鉴正在整理中，尚未收录条目。</p></div>\n'

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
        body += '''        <div class="empty-state"><div class="empty-icon">◇</div><h3>暂无境界体系</h3><p>尚未收录任何作品的境界体系。境界阶梯按作品分组展示，便于跨作品对照与量级分析。</p></div>
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


def render_page_content(page):
    """渲染独立页正文，结果缓存，并把标题锚点登记到 _PAGE_ANCHORS。

    档位的 source 字段靠这份映射解析成「跳到规则原文对应小节」的深链。
    """
    key = page.get('slug')
    if key in _PAGE_CACHE:
        return _PAGE_CACHE[key]
    text = resolve_page_content(page)
    html_body, toc, anchors = render_markdown_full(text)
    if key:
        _PAGE_ANCHORS.setdefault(key, {}).update(anchors)
    _PAGE_CACHE[key] = (html_body, toc)
    return _PAGE_CACHE[key]


def toc_block_html(toc_inner):
    """目录侧栏。移动端由 main.js 把整块搬进底部抽屉，桌面端保持右侧吸附。"""
    if not (toc_inner or '').strip():
        return ''
    return f"""            <aside class="doc-toc" id="doc-toc">
                <p class="doc-toc-title">目录</p>
                <div class="doc-toc-body">
{toc_inner}
                </div>
            </aside>"""


def build_tiers_toc(segments):
    """量级体系表页的目录：分段为一级，档位为二级。"""
    out = ['<div class="toc">', '  <ul>']
    for seg in segments:
        out.append(f'    <li><a href="#group-{seg["key"]}">{html_escape(seg["label"])}</a>')
        out.append('      <ul>')
        for cat in seg['members']:
            out.append(f'        <li><a href="#tier-{cat.get("slug")}">'
                       f'{html_escape(cat.get("name"))}</a></li>')
        out.append('      </ul>')
        out.append('    </li>')
    out.append('  </ul>')
    out.append('</div>')
    return '\n'.join(out)


def build_pages(pages):
    for page in sorted(pages, key=lambda x: x.get('sort_order', 0)):
        content_html, toc_html = render_page_content(page)
        toc_block = toc_block_html(toc_html)
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
    no_result_text = '暂无角色数据，稍后会陆续补充' if not characters else '没有匹配的角色，试试放宽条件'

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
    """写盘并登记到清单（清单用于下次构建清理孤儿文件）。"""
    rel = rel.replace(os.sep, '/')
    if CHECK_ONLY:
        _MANIFEST.append(rel)
        return
    path = os.path.join(OUT_DIR, rel)
    os.makedirs(os.path.dirname(path) or OUT_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    _MANIFEST.append(rel)


def copy_static():
    if CHECK_ONLY:
        return
    os.makedirs(os.path.join(OUT_DIR, 'static', 'css'), exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, 'static', 'js'), exist_ok=True)
    css_src = os.path.join(STATIC_SRC, 'css', 'style.css')
    if os.path.exists(css_src):
        shutil.copy2(css_src, os.path.join(OUT_DIR, 'static', 'css', 'style.css'))
        _MANIFEST.append('static/css/style.css')
    js_src = os.path.join(STATIC_SRC, 'js', 'main.js')
    if os.path.exists(js_src):
        shutil.copy2(js_src, os.path.join(OUT_DIR, 'static', 'js', 'main.js'))
        _MANIFEST.append('static/js/main.js')
    uploads_src = os.path.join(STATIC_SRC, 'uploads')
    if os.path.exists(uploads_src):
        shutil.copytree(uploads_src, os.path.join(OUT_DIR, 'static', 'uploads'), dirs_exist_ok=True)
    for root, _dirs, files in os.walk(os.path.join(OUT_DIR, 'static', 'uploads')):
        for fn in files:
            _MANIFEST.append(os.path.relpath(os.path.join(root, fn), OUT_DIR).replace(os.sep, '/'))
    nojekyll = os.path.join(OUT_DIR, '.nojekyll')
    with open(nojekyll, 'w') as f:
        f.write('')
    _MANIFEST.append('.nojekyll')


def clean_orphans(previous, target=None):
    """删除上一次构建留下、这一轮已不存在的产物文件。

    典型场景：档位改名或废弃后，旧的 category/xxx.html 会一直挂在仓库根目录上，
    手动删容易漏、也容易误删源码。清单之外的文件一律不动。
    """
    target = target or OUT_DIR
    current = set(_MANIFEST)
    removed = 0
    for rel in sorted(previous - current):
        path = os.path.join(target, rel)
        if os.path.isfile(path):
            os.remove(path)
            removed += 1
            print('    清理孤儿文件：' + rel)
    return removed


def save_manifest():
    if CHECK_ONLY:
        return
    with open(os.path.join(OUT_DIR, MANIFEST_NAME), 'w', encoding='utf-8') as f:
        json.dump({'files': sorted(set(_MANIFEST))}, f, ensure_ascii=False, indent=1)


def sync_to_root():
    """把 dist/ 内容同步到仓库根目录（GitHub Pages 直接读根目录）。"""
    for root, _dirs, files in os.walk(DIST_DIR):
        rel_dir = os.path.relpath(root, DIST_DIR)
        if rel_dir == '.':
            target_dir = BASE_DIR
        else:
            target_dir = os.path.join(BASE_DIR, rel_dir)
        os.makedirs(target_dir, exist_ok=True)
        for fn in files:
            src = os.path.join(root, fn)
            dst = os.path.join(target_dir, fn)
            shutil.copy2(src, dst)


def main():
    global BASE, OUT_DIR, CHECK_ONLY
    global _CAT_MAP, _CAT_ORDER, _CAT_BY_SLUG, _GROUP_MAP, _GROUPS_ORDERED, _PAGES

    if '--base' in sys.argv:
        idx = sys.argv.index('--base')
        if idx + 1 < len(sys.argv):
            BASE = sys.argv[idx + 1].strip().rstrip('/')
    elif os.environ.get('SITE_BASE') is not None:
        BASE = os.environ.get('SITE_BASE').strip().rstrip('/')

    CHECK_ONLY = '--check' in sys.argv
    deploy_root = '--deploy-root' in sys.argv
    # OUT_DIR 恒为 dist/：始终先构建到独立目录，再由 sync_to_root() 同步到仓库根。
    # 若直接把仓库根当输出目录，static 源目录会与目标同路径，copy 会撞 SameFileError。
    OUT_DIR = DIST_DIR

    categories, groups, realms, characters, pages = load_data()

    # 档位映射：slug -> 名称 / 排序值 / 完整档位对象（卡片与搜索共用）
    _CAT_MAP = {c['slug']: c['name'] for c in categories}
    _CAT_ORDER = {c['slug']: c.get('sort_order', 0) for c in categories}
    _CAT_BY_SLUG = {c.get('slug'): c for c in categories}
    # 体系分段（按档位在轴上首次出现的顺序展示）
    _GROUP_MAP = {g.get('id'): g for g in groups}
    power_categories = ordered_power_categories(categories)
    _GROUPS_ORDERED = list(dict.fromkeys((c.get('group') or 'misc') for c in power_categories))
    # 供全局导航渲染（按 sort_order 排序）
    _PAGES = sorted(pages, key=lambda x: x.get('sort_order', 0))

    print('=' * 58)
    print('生成静态站点（文件式，无后端）...')
    print(f'站点路径：{BASE if BASE else "/（根路径）"}')
    print(f'输出目录：{OUT_DIR}'
          + ('（仅校验，不写文件）' if CHECK_ONLY else ''))
    print(f'数据：档位 {len(power_categories)} · 分段 {len(_GROUPS_ORDERED)} '
          f'· 境界 {len(realms)} · 角色 {len(characters)} · 页面 {len(pages) + 1}')
    print('=' * 58)

    # ---- 准备输出目录（必须先于任何写盘，否则产物会被随后的清理误删）----
    # 上一轮产物的清单：deploy-root 模式靠它识别「这一轮不再生成」的失效文件
    previous_manifest = set()
    if not CHECK_ONLY and deploy_root:
        mf_path = os.path.join(BASE_DIR, MANIFEST_NAME)
        if os.path.exists(mf_path):
            try:
                with open(mf_path, 'r', encoding='utf-8') as f:
                    previous_manifest = set(json.load(f).get('files') or [])
            except (ValueError, OSError):
                previous_manifest = set()

    if not CHECK_ONLY:
        if os.path.exists(DIST_DIR):
            shutil.rmtree(DIST_DIR)
        for sub in ['character', 'category', 'realm', 'page', 'static/css', 'static/js']:
            os.makedirs(os.path.join(OUT_DIR, sub), exist_ok=True)

    # ---- 先渲染规则页：档位的 source 要靠它解析成原文深链 ----
    build_pages(pages)

    # ---- 构建前自检 ----
    print('\n[1/9] 数据一致性自检...')
    errors, warnings = validate_data(categories, groups, realms, characters, pages)
    for w in warnings:
        print('    [warn] ' + w)
    if errors:
        for e in errors:
            print('    [ERROR] ' + e)
        print('\n数据校验未通过，已中止构建。请修正 data/*.yaml 后重试。')
        sys.exit(1)
    print(f'    通过（{len(warnings)} 条提示）')

    print('[2/9] 复制静态资源...')
    copy_static()

    print('[3/9] 生成首页（战力等级按体系分段）...')
    build_index(categories, groups, realms, characters, pages)

    print('[4/9] 生成量级体系表页...')
    build_tiers_page(categories, characters)

    print('[5/9] 生成各档位详情页...')
    build_categories(categories, characters, power_categories)

    print('[6/9] 生成角色页...')
    build_characters_index(characters, power_categories)
    build_character_detail(characters, categories, realms)

    print('[7/9] 生成境界页...')
    build_realm_index(realms, characters)
    build_realm_detail(realms, characters)

    print('[8/9] 生成搜索页...')
    build_search(characters, categories, realms)

    print('[9/9] 生成 404...')
    build_404()

    if CHECK_ONLY:
        print('\n' + '=' * 58)
        print('校验完成，未写入任何文件。')
        print('=' * 58)
        return

    save_manifest()

    if deploy_root:
        print('\n同步产物到仓库根目录...')
        sync_to_root()
        print(f'    已写入 {len(set(_MANIFEST))} 个文件')
        shutil.copy2(os.path.join(DIST_DIR, MANIFEST_NAME),
                     os.path.join(BASE_DIR, MANIFEST_NAME))
        # 孤儿清理放在同步之后：拿本轮清单与上一轮清单比对，只删真正失效的产物
        if previous_manifest:
            print('\n清理上一轮遗留的失效产物...')
            removed = clean_orphans(previous_manifest, BASE_DIR)
            print(f'    清理 {removed} 个文件')

    print('\n' + '=' * 58)
    print('导出完成！输出目录：', OUT_DIR)
    if deploy_root:
        print('产物已同步到仓库根目录，提交推送后 GitHub Pages 即生效。')
    else:
        print('把 dist 目录内容推到 GitHub Pages 仓库即可。')
    print('=' * 58)


if __name__ == '__main__':
    main()
