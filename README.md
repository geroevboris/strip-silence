# Clear Silence

Независимая утилита для удаления тишины из аудиоклипов Ableton Live (macOS).

**Текущая версия: v0.3 (тестовый прототип).** Рассчитана на Ableton Live 12.4.6. Использует локальное приложение Python с отдельным окном WebKit и MIDI Remote Script `ClearSilenceBridge`.

- Выбор дорожек и анализ WAV по Threshold, Min Silence и Padding.
- Визуальный предпросмотр: зелёные области сохраняются, красные удаляются.
- Замена клипов на исходных дорожках без изменения исходных WAV.
- Проверка версии Remote Script до замены — защита от `Unknown action`.

**Внимание:** интерфейс окна требует однократной установки pywebview через `03_SETUP_UI.command`. Перед первым запуском обнови мост командой `01_INSTALL.command` и перезапусти Ableton. Затем открой `Clear Silence.app` или `02_START.command`.

**На данный момент проверено локальными тестами, но не в реальном Ableton/macOS. Работай только на копии Live Set.** Подробная инструкция — `README_RU.md`.

Проект не связан с коммерческим StripSilencer Antoine Delvig.
