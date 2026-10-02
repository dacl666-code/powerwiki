# 全作品战力评鉴所

跨作品角色战力量级评鉴的**静态资料站**。无后端、无数据库，全部内容由 `data/` 下的
YAML / Markdown 文件生成，一键构建，直接推到 GitHub Pages。

在线地址：https://zhishixuebao2026.github.io/powerwiki/

---

## 它长什么样

| 页面 | 路径 | 内容 |
|---|---|---|
| 首页 | `/index.html` | 战力等级（92 个量级档位，按体系分段由弱到强排列） |
| 量级体系表 | `/page/tiers.html` | 档位表完整展开版：能量区间、覆盖尺度、判定要点、规则原文跳转 |
| 战力评级规则 | `/page/rules.html` | 《战力量级体系》全文，带侧边目录与阅读进度记忆 |
| 材质与破坏能量数据库 | `/page/cosmology.html` | 换算参考 |
| 各档位详情页 | `/category/<slug>.html` | 每档一个页面：所属量级、能量、尺度、上一档／下一档、该档角色 |
| 角色图鉴 | `/characters.html` | 全部角色 |
| 境界体系 | `/realm/index.html` | 按作品分组的境界阶梯 |
| 搜索 | `/search.html` | 按作品 / 量级 / 境界体系 / 境界筛选 |

---

## 核心：档位数据与规则原文同源

站点的「战力等级」不是手写死的，而是 `data/categories.yaml` 的直接渲染结果；
`categories.yaml` 的档位又逐条对应 `data/pages/rules.md` 的《战力量级体系》

```
data/pages/rules.md      体系原文（人读的方法论与定级口径）
        │  source 字段指向 rules.md 的小节标题
        ▼
data/categories.yaml     档位数据（机器读的 92 档 + 分段）
        │  构建时渲染
        ▼
首页战力等级 / 量级体系表 / 各档详情页 / 搜索筛选器
```

每个档位可通过 `source` 字段声明它出自 rules.md 的哪一节，构建时自动解析成锚点，
档位详情页与体系表页都能一键跳到规则原文对应小节。改规则不用改代码。

### 档位体系分段

| 分段 | 档位数 | 说明 |
|---|---|---|
| 第一部分 · 继承区 | 55 | 昆虫 ～ 爆恒星，沿用汪吧标准，含强大陆倒挂修正、爆街→爆城过渡区、爆褐矮星量级 |
| 第二部分 · 过渡带 A | 1 | 恒星 → 恒星系之间的命名空白（7.3 个数量级） |
| 第三部分 · 覆盖体系 | 24 + 24 | 恒星系 / 星团 / 星系 / 星系团 / 宇宙结构 / 宇宙级，按覆盖尺度 × F* 计算 |
| 第二部分 · 过渡带 B | 1 | 恒星系 → 星团之间的命名空白 |
| 3.10 · 广义无限区级 | 2 | 有限 · 不可计算 |
| 第四部分 · 论外级 | 8 | 真无限 ℵ₀ 起：门槛 / 三线 / 二线 / 一线 / 论天下·中·上 / 论天最上 |
| 未归档 | 1 | **未知/暂存**（体系之外的兜底档，不参与强弱排序） |

过渡带 A / B 之所以各自单独成段，是因为它们按能量轴上的真实位置排列，
不与相邻量级归拢——避免打乱「由弱到强」的顺序。

### 旧框架档位已废弃

旧档位沿用汪吧／维基式命名，与现行体系不符，已全部移除：

```
低维 / 微观                          → 取消（昆虫级以下不单列，落「未知/暂存」）
弱单体 · 单体 · 强单体 · 超单体       → 弱宇宙 / 标准宇宙 / 强宇宙 / 超宇宙
弱多元 · 多元 · 强多元 · 高阶多元
  · 无限多元                         → 星系团级 · 宇宙结构级，或广义无限区级
无限盒子 · 无限层无限盒子
  · 无限次方无限盒子 · 多层无限盒子
  · 无限指数塔 · 超指数塔
  · 高阶无限层/次方/指数塔            → 广义无限区级，或论外级
论外（单一档）                       → 论外级八档
```

完整对照写在 `data/categories.yaml` 文件头注释里。

---

## 本地构建

```bash
pip install pyyaml markdown      # 仅两个依赖

python build_site.py                       # 构建到 dist/
python build_site.py --base /powerwiki     # 指定站点子路径（默认 /powerwiki）
python build_site.py --check               # 只校验数据一致性，不写文件
python build_site.py --deploy-root         # 构建并把产物同步到仓库根目录
```

构建前会自动做数据自检，出问题直接中止并指出是哪一条：

- 档位 slug / sort_order 重复
- 分段 id 未在 `groups` 中定义
- **未归档档（未知/暂存）不在最末**
- **角色挂在已废弃或不存在的档位上**
- `pages.yaml` 引用的正文文件缺失
- 档位 `source` 在 rules.md 中找不到同名小节（仅提示）

### 产物清理

`--deploy-root` 模式会用 `.site-manifest.json` 记录本轮产物清单，
下一轮构建时比对上一轮清单，自动删除「这一轮不再生成」的文件
（比如档位改名后残留的 `category/xxx.html`）。清单之外的文件一律不动。

---

## 部署到 GitHub Pages

### 首次配置

1. Settings → Pages → Source 选 `main` 分支，目录 `/ (root)`
2. 仓库名不是 `用户名.github.io` 时，`--base` 填 `/仓库名`

### 每次更新

```bash
python build_site.py --base /powerwiki --deploy-root
git add -A
git commit -m "deploy: 更新站点"
git push origin main
```

Windows 上直接双击 `deploy.bat` 即可（内部调用的就是上面这套流程）。

`--deploy-root` 会：构建到 `dist/` → 同步到仓库根目录 → 清理失效产物。
`.nojekyll` 与 `.site-manifest.json` 会一并写入根目录。

---

## 站点放什么、仓库放什么

**站点页面只放给读者看的内容**（档位、规则、换算表、角色）。以下内容一律留在仓库里，
不生成到网页上：

- 改档流程、字段说明、构建与部署步骤 —— 写在本 README
- 档位迁移对照、废弃档位说明 —— 写在 `data/categories.yaml` 文件头注释
- 版本变更记录 —— 见 [CHANGELOG.md](CHANGELOG.md)（含《战力量级体系》的定稿与待定事项），
  以及提交信息与 Release；不在页面里维护更新日志

页面上的「阅读口径」只解释**怎么读这张表**（排序、分段、兜底档含义），
不涉及怎么改数据。

## 维护数据

| 想改什么 | 改哪个文件 |
|---|---|
| 量级档位（增删改名、调能量区间、调排序、加分段） | `data/categories.yaml` |
| 评级方法论 / 体系原文 | `data/pages/rules.md` |
| 材质与破坏能量数据 | `data/pages/cosmology.md` |
| 独立页面（新增、改名、调导航顺序） | `data/pages.yaml` |
| 角色 | `data/characters.yaml` |
| 境界体系 | `data/realms.yaml` |
| 站点样式 | `static/css/style.css` |

改完重新构建，首页、体系表、各档详情页、搜索筛选器、全局导航全部同步更新。

### 改档流程

```
编辑 data/categories.yaml  ->  python build_site.py --deploy-root  ->  提交推送
```

档位字段含义（完整说明见 `data/categories.yaml` 文件头）：

| 字段 | 作用 |
|---|---|
| `slug` | URL 标识，改名会导致旧链接失效 |
| `name` | 档位名，取自 rules.md 1.3 量级表与第三、四部分 |
| `type` | 固定 `power`（战力量级档位） |
| `group` | 体系分段 id，必须在 `groups` 里定义过 |
| `parent` | 所属量级（父档），如「爆砖」 |
| `sort_order` | 由弱到强，间隔 10 便于后续插档 |
| `energy` / `scale` | 能量区间与覆盖尺度，照抄 rules.md |
| `note` | 判定要点，显示在体系表与档位详情页 |
| `source` | rules.md 的小节标题，用于生成规则原文深链 |

旧框架的汪吧/维基式档位（弱单体 · 多元 · 高阶多元 · 无限盒子系列 · 指数塔系列 ·
低维 · 微观等）已全部废弃，完整对照写在 `data/categories.yaml` 文件头注释里。

### 加一个档位

在 `data/categories.yaml` 的 `items` 里加一条：

```yaml
- slug: my-tier            # URL 标识，category/my-tier.html
  name: 我的档位
  type: power
  group: cover             # 所属分段 id，必须在 groups 里定义过
  parent: 恒星系级         # 所属量级（父档）
  sort_order: 595          # 由弱到强，间隔 10 便于插档
  energy: 1×10⁵⁵ J         # 能量区间
  scale: 覆盖直径 5 万 AU   # 覆盖尺度 / 参照物
  note: 判定要点（可选）    # 显示在体系表与详情页
  source: 3.3 恒星系级（半球扩散）   # rules.md 的小节标题，用于生成原文跳转
```

---

## 目录结构

```
powerwiki/
├── build_site.py          静态站点生成器（唯一构建入口）
├── deploy.bat             Windows 一键部署
├── data/
│   ├── categories.yaml    战力量级体系表：分段 + 93 个档位  ← 站点核心数据
│   ├── pages.yaml         独立页面清单
│   ├── pages/
│   │   ├── rules.md       《战力量级体系》原文
│   │   └── cosmology.md   材质与破坏能量数据库
│   ├── characters.yaml    角色（尚未收录）
│   └── realms.yaml        境界体系（尚未收录）
├── static/
│   ├── css/style.css      样式
│   └── js/main.js         目录滚动高亮、阅读进度、返回按钮
├── dist/                  构建产物（.gitignore 忽略）
├── .site-manifest.json    产物清单，用于清理失效文件
├── index.html             以下为 --deploy-root 同步到根目录的产物
├── page/                  规则页 / 量级体系表页
├── category/              各档位详情页
└── characters.html
```

> 根目录的 HTML 是构建产物，不是源码。改内容请改 `data/` 与 `static/`，
> 再跑一次构建，不要手改根目录的 HTML——下次构建会被覆盖。
