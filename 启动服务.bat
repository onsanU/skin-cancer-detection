@echo off
REM ============================================================
REM  皮肤癌图像检测系统 - Windows 一键启动 (双击本文件即可)
REM  原理: 调用 WSL 里项目目录下的 start.sh
REM ============================================================
chcp 65001 >nul
title 皮肤癌图像检测系统 - 启动中

echo.
echo   ============================================================
echo    皮肤癌图像检测系统 - 一键启动
echo   ============================================================
echo.
echo   正在通过 WSL 启动服务，首次加载模型约 10-20 秒，请稍候...
echo.

REM 项目在 WSL 中的路径（/mnt/d/... 对应 Windows 的 D:\...）
set PROJ_WSL=/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统

wsl bash -lc "cd '%PROJ_WSL%' && bash start.sh --bg"

if errorlevel 1 (
  echo.
  echo   [失败] 启动过程出错，请查看上面的提示。
  echo   日志位置: D:\Project\JXprojiect\Hermes-project\project\皮肤癌图像系统\logs\backend.log
  echo.
  pause
  exit /b 1
)

echo.
echo   ============================================================
echo    启动完成! 正在打开浏览器...
echo   ============================================================
echo.
echo    前台检测:  http://127.0.0.1:8000/app/
echo    管理后台:  http://127.0.0.1:8000/admin/
echo    API文档 :  http://127.0.0.1:8000/docs
echo.
echo    关闭服务: 双击 停止服务.bat
echo.

timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000/app/

echo   浏览器已打开，本窗口可以关闭。
pause
