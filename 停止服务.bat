@echo off
REM ============================================================
REM  皮肤癌图像检测系统 - 停止服务 (双击本文件即可)
REM ============================================================
chcp 65001 >nul
title 皮肤癌图像检测系统 - 停止服务

set PROJ_WSL=/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统

echo.
echo   正在停止皮肤癌检测系统服务...
echo.
wsl bash -lc "cd '%PROJ_WSL%' && bash stop.sh"
echo.
pause
