@echo off
chcp 65001 >nul
REM marl-ecdsa self-evolve watch wrapper (hourly, read-only)
set PY=C:\Users\Administrator\.office-raccoon\agent\box-agent-runtime\runtime\python\python.exe
set DIR=C:\Users\Administrator\RaccoonWork\self-evolve
set LOG=%DIR%\watch.log
set PYTHONIOENCODING=utf-8

echo. >> "%LOG%"
echo ===== self-evolve watch ===== >> "%LOG%"
"%PY%" "%DIR%\pr5_watch.py" >> "%LOG%" 2>&1
"%PY%" "%DIR%\repo_health.py" >> "%LOG%" 2>&1
set HEALTH_RC=%ERRORLEVEL%
REM repo_health 退出码：0=正常 1=全部路径失败 2=补丁异常（回退/语法错/缺失）
REM 显式把异常退出码记进日志，便于定时任务历史 / 巡检回溯感知。
echo [health_rc=%HEALTH_RC%] >> "%LOG%"
if not "%HEALTH_RC%"=="0" (
    echo !!! repo_health 异常，rc=%HEALTH_RC% !!! >> "%LOG%"
)
exit /b %HEALTH_RC%
