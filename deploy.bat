@echo off
chcp 65001 >nul
setlocal

REM ============================================
REM  战力维基 - GitHub Pages 一键部署（单分支模型）
REM  main 分支同时保存源码与构建产物；本脚本重新生成站点、
REM  把 dist/ 产物同步到仓库根目录，再整体推送到 main。
REM  分支策略：日常在 source 分支改源码 -> 合并到 main -> 本脚本推送即上线。
REM ============================================

REM 你的 GitHub 仓库地址（账户已更名为 zhishixuebao2026）
set REPO_URL=https://github.com/zhishixuebao2026/powerwiki.git

REM 站点路径（仓库名非 用户名.github.io 时填 /powerwiki）
set BASE_PATH=/powerwiki

echo ============================================
echo   开始部署到 GitHub Pages
echo ============================================
echo.

echo [1/4] 生成静态站点...
python build_site.py --base %BASE_PATH%
if errorlevel 1 (
    echo 生成失败，请检查 Python 环境
    pause
    exit /b
)
echo.

echo [2/4] 同步构建产物到仓库根目录（dist/* -> 根目录）...
xcopy /E /Y /H dist\* . >nul
echo.

echo [3/4] 提交更改...
git add -A
git commit -m "deploy: 更新站点 %date% %time%"
if errorlevel 1 (
    echo 没有需要提交的更改，跳过
)
echo.

echo [4/4] 推送到 GitHub（main 分支）...
git remote remove origin 2>nul
git remote add origin %REPO_URL%
git push origin main
if errorlevel 1 (
    echo.
    echo 推送失败！请检查：
    echo   1. 仓库地址是否正确：%REPO_URL%
    echo   2. 是否已登录 GitHub（配置 Git 凭据 / PAT）
    echo   3. 仓库是否已在 GitHub 上创建
    pause
    exit /b
)

echo.
echo ============================================
echo   部署完成！访问 https://zhishixuebao2026.github.io/powerwiki/
echo ============================================
pause
