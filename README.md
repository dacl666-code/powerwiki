# 全作品战力评鉴所（本地版）

一个类似 [baike.zjhengde.com](https://baike.zjhengde.com) 的轻量级角色战力百科系统，**本地运行、单用户管理、数据自动保存**，可打包部署到任意服务器。

## 功能特性

- 按战力等级、作品、首字母、境界分类展示角色
- 角色详情页（介绍、战绩、能力说明、图片）
- 规则/世界观独立页面（可自由编辑）
- 搜索功能
- 单用户登录，只有管理员能增删改
- **编辑角色时自动保存草稿（每 10 秒）**
- **图片支持本地上传，不用先传图床**
- **双击 `app.py` 自动打开浏览器**
- **后台编辑器支持 Markdown（EasyMDE）**
- 前台自动渲染 Markdown 为 HTML
- 数据使用 SQLite 本地存储
- 纯 Python + HTML/CSS/JS，无复杂依赖

## 首次使用三步

### 第一步：安装依赖

```bash
pip install -r requirements.txt
```

### 第二步：启动

双击 `app.py`，或在文件夹里打开终端运行：

```bash
python app.py
```

### 第三步：打开浏览器

程序启动后会**自动打开浏览器**访问 `http://127.0.0.1:5000`。

如果没有自动打开，手动在浏览器输入这个地址。

## 登录后台

- 前台地址：`http://127.0.0.1:5000`
- 后台地址：`http://127.0.0.1:5000/admin`
- 首次启动时控制台会显示默认密码
- 也可以在 `data/admin.txt` 文件里查看密码

## 添加角色（最简单的方式）

1. 登录后台 → 点「角色管理」→「添加角色」
2. 按区块填写：
   - **基本信息**：名称、别名、作品、首字母
   - **战力与境界**：下拉选择战力等级和境界
   - **角色图片**：点「选择文件」直接上传电脑里的图片，或粘贴网络图片链接
   - **角色文案**：角色介绍/战绩、能力说明
3. 点最下面「保存角色」

> 编辑已有角色时，系统会**每 10 秒自动保存一次草稿**，防止丢失。

## 修改管理员密码

### 方式一：环境变量（推荐用于服务器）

```bash
# Linux / macOS
export ADMIN_PASSWORD=你的新密码
python app.py

# Windows
set ADMIN_PASSWORD=你的新密码
python app.py
```

### 方式二：修改文件

编辑 `data/admin.txt`，把里面内容换成你的新密码。

## 部署到 GitHub Pages（静态版，免费）

GitHub Pages 只能托管静态文件，跑不了 Python。所以流程是：

**本地编辑 → 一键导出静态 HTML → 推送到 GitHub Pages**

在线访客只能浏览，不能修改，正好符合「只有自己能改」的需求。

### 第一步：在 GitHub 建仓库

1. 打开 https://github.com/new
2. 仓库名填 `powerwiki`（或其他名字）
3. 选 **Public**（Pages 免费版需要公开库）
4. 不要勾选 README 和 .gitignore，直接创建

### 第二步：开启 Pages

进入刚建的仓库 → **Settings** → **Pages** → Source 选 `main` 分支，目录选 `/ (root)` → Save

几秒后会出现访问地址，形如：

```
https://你的用户名.github.io/powerwiki/
```

### 第三步：配置部署脚本

用记事本打开 `deploy.bat`，修改开头两行：

```bat
set REPO_URL=https://github.com/你的用户名/powerwiki.git
set BASE_PATH=/powerwiki
```

- `REPO_URL`：你的仓库地址
- `BASE_PATH`：如果仓库名是 `用户名.github.io` 就留空，否则填 `/仓库名`

### 第四步：一键部署

双击运行 `deploy.bat`，它会自动完成：

1. 导出静态站点到 `dist/`
2. 提交更改
3. 推送到 GitHub

推送完等 1~2 分钟，访问 Pages 地址就能看到网站了。

> 以后每次改完内容，重新双击 `deploy.bat` 即可更新线上站点。

### 手动导出（可选）

```bash
python export_static.py --base /powerwiki
```

导出结果在 `dist/` 目录。

---

## 部署到服务器（Flask 动态版）

如果你想在线也能编辑，需要部署 Flask 应用到支持 Python 的服务器。

### 使用 Gunicorn

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 使用 Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV ADMIN_PASSWORD=你的强密码
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### 使用宝塔 / 云服务器

1. 把 `powerwiki` 文件夹上传到服务器
2. 安装依赖：`pip install -r requirements.txt`
3. 用 Gunicorn 或 Supervisor 运行 `app.py`
4. Nginx 反向代理到 5000 端口
5. 设置环境变量 `ADMIN_PASSWORD` 为你的强密码

## 数据备份

所有数据都在 `data/powerwiki.db` 一个文件里，直接复制这个文件即可备份。上传的图片在 `static/uploads/` 里。

## 目录结构

```
powerwiki/
├── app.py                  # 主程序（双击启动）
├── export_static.py        # 静态站点导出脚本
├── deploy.bat              # GitHub Pages 一键部署
├── requirements.txt        # 依赖
├── README.md               # 本说明
├── data/                   # SQLite 数据库 & 密码文件
├── dist/                   # 导出的静态站点（导出后生成）
├── static/
│   ├── css/style.css       # 样式
│   ├── js/main.js          # 脚本
│   └── uploads/            # 你上传的图片
└── templates/              # HTML 模板
    ├── *.html              # 前台页面
    └── admin/              # 后台页面
```

## 自定义说明

- 战力等级分类：登录后台 → 分类管理
- 境界体系：登录后台 → 境界管理
- 规则/世界观页面：登录后台 → 页面管理
- 角色：登录后台 → 角色管理

## 后续可扩展

- Markdown 编辑器
- 批量导入导出 Excel/JSON
- 多用户权限
- 评论/投票系统
