@echo off
rem Обновить витрину данными с этого компьютера и отправить в GitHub (Netlify соберёт сайт сам).
rem Двойной клик, либо задача по расписанию (см. install_autosync.cmd; тогда запускается с аргументом auto: без паузы).
rem Нужны: Python 3 и git; ИИ и ключи не нужны ($0). Результат каждого запуска дописывается в sync.log рядом с витриной.
rem 1) Папка репозитория AiMaxBossman (где лежит command-center):
set "BOSSMAN_REPO=%~dp0..\..\AiMaxBossman"
cd /d "%~dp0.."
echo ==== %DATE% %TIME% >> sync.log
rem 2) Свежие данные: подтянуть витрину и (без слияний и без ваших правок) репозиторий Bossman.
git pull --ff-only >> sync.log 2>&1
git -C "%BOSSMAN_REPO%" pull --ff-only >> sync.log 2>&1
rem 3) Разбор. --live auto берёт счётчики самоулучшения у запущенного Bossman (не запущен — снимок только из git).
python scripts\sync_bossman.py --source "%BOSSMAN_REPO%" --live auto --push >> sync.log 2>&1
type sync.log | findstr /R "SYNC= PUSH=" 
if /I not "%~1"=="auto" pause
