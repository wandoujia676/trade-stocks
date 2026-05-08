@echo off
chcp 65001 >nul
echo ================================================
echo 小金库 9.0 一键备份
echo ================================================
echo.

cd /d "E:\AI-编程\start from scratch\20260331 炒股"

echo [1/3] 添加选股结果和配置文件...
git add "stocks/Stock Selection/View Results/" "stocks/Stock Verification/warfare_config.json"

echo [2/3] 提交...
git commit -m "backup: 备份选股结果和权重配置 %date% %time:~0,5%"

echo [3/3] 推送到 GitHub...
git push

echo.
echo ================================================
echo 备份完成！
echo ================================================
pause
