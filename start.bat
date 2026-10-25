@echo off
chcp 65001 >nul
title MediaBoss
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [MediaBoss] 未找到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"
  pause
  exit /b 1
)
echo [MediaBoss] 启动服务: http://127.0.0.1:8656  (默认密码 admin)
python server.py
pause
