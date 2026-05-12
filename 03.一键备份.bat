@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ================================================
echo 小金库 9.0 一键备份
echo ================================================
echo.

cd /d "E:\AI-编程\start from scratch\20260331 炒股"
if errorlevel 1 (
    echo [错误] 无法切换到项目目录
    goto :error
)

echo [1/4] 检查有无新内容要备份...
git status --porcelain "stocks/Stock Selection/View Results/" "stocks/Stock Verification/warfare_config.json" > nul 2>&1
if errorlevel 1 (
    echo [错误] 不在 git 仓库里，或 git 不可用
    goto :error
)

for /f %%i in ('git status --porcelain "stocks/Stock Selection/View Results/" "stocks/Stock Verification/warfare_config.json"') do set HAS_CHANGES=1
if not defined HAS_CHANGES (
    echo.
    echo [跳过] View Results 和 warfare_config.json 都没变化，不需要备份
    echo.
    pause
    exit /b 0
)

echo [2/4] 添加选股结果和配置文件...
git add "stocks/Stock Selection/View Results/" "stocks/Stock Verification/warfare_config.json"
if errorlevel 1 (
    echo [错误] git add 失败
    goto :error
)

echo [3/4] 提交...
rem 用 PowerShell 生成安全的时间字符串（避免 %date% 带斜杠和中文星期）
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm"') do set STAMP=%%i
git commit -m "backup: 选股结果和权重配置 !STAMP!"
if errorlevel 1 (
    echo.
    echo [警告] git commit 失败，可能是没有实际变动（全是空白改动）或者其他原因
    echo         继续尝试 push，如果本地已经有未推送的 commit 也能推上去
    echo.
)

echo [4/4] 推送到 GitHub...
git push
if errorlevel 1 (
    echo.
    echo [错误] git push 失败 — 可能是网络问题或 GitHub 认证过期
    echo         手动排查：在这个窗口里输入 git push 看具体报错
    goto :error
)

echo.
echo ================================================
echo 备份完成！
echo ================================================
pause
exit /b 0

:error
echo.
echo ================================================
echo 备份失败 — 请把上面的错误信息告诉 Claude
echo ================================================
pause
exit /b 1
