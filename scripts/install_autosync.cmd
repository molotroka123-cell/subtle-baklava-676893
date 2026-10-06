@echo off
rem Ставит задачу Windows «Bossman-Showcase-Sync»: раз в час запускает sync_from_pc.cmd (работает, пока вы вошли в Windows).
rem Проверка: после запуска откройте сайт: вверху «данные обновлены N ч назад»; если больше 26 часов — красная строка.
rem Снять задачу:  schtasks /Delete /TN Bossman-Showcase-Sync /F
schtasks /Create /TN "Bossman-Showcase-Sync" /SC HOURLY /MO 1 /TR "\"%~dp0sync_from_pc.cmd\" auto" /F
schtasks /Query /TN "Bossman-Showcase-Sync"
pause
