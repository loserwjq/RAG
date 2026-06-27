@echo off
chcp 65001 >nul
echo ========================================
echo   RAG 知识库问答系统 - PM2 部署
echo ========================================
echo.

:: 检查 PM2 是否安装
where pm2 >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/4] 安装 PM2...
    npm install -g pm2
    npm install -g pm2-windows-startup
) else (
    echo [1/4] PM2 已安装，跳过
)

:: 停止旧进程（如果有）
echo [2/4] 清理旧进程...
pm2 delete all 2>nul

:: 启动服务
echo [3/4] 启动前后端服务...
cd /d D:\minerU_local
pm2 start ecosystem.config.cjs

:: 保存并设置开机自启
echo [4/4] 设置开机自启...
pm2 save

echo.
echo ========================================
echo   部署完成！
echo ========================================
echo.
echo   前端: http://localhost:5173
echo   后端: http://localhost:8005
echo   API:  http://localhost:8005/docs
echo.
echo   常用命令:
echo     pm2 list          查看进程状态
echo     pm2 monit         实时监控
echo     pm2 logs          查看所有日志
echo     pm2 restart all   重启所有服务
echo.
echo   日志目录: D:\minerU_local\logs\
echo ========================================
pause
