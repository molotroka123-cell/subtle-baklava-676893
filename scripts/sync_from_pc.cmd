@echo off
rem Обновить витрину данными с этого компьютера и отправить в GitHub (Netlify соберёт сайт сам).
rem Двойной клик или задача по расписанию. Нужны: Python 3 и git; ИИ и ключи не нужны ($0).
rem 1) Укажите папку репозитория AiMaxBossman (где лежит command-center):
set "BOSSMAN_REPO=%~dp0..\..\AiMaxBossman"
rem 2) Запуск: --live auto берёт счётчики самоулучшения у запущенного Bossman (если он не запущен — снимок только из git).
cd /d "%~dp0.."
git pull --ff-only
python scripts\sync_bossman.py --source "%BOSSMAN_REPO%" --live auto --push
echo.
pause
