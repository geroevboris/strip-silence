# Clear Silence

Независимая утилита для удаления тишины из аудиоклипов Ableton Live (macOS).

**Текущая версия: v0.2 (прототип).** Подготовлена для Ableton Live 12.4.6. Использует локальное приложение на Python 3 и MIDI Remote Script `ClearSilenceBridge` (не Max for Live).

- Анализ WAV по Threshold, Min Silence и Padding.
- Предпросмотр, выбор дорожек и замена клипов на исходных дорожках.
- Исходные WAV не перезаписываются; создаются новые WAV-фрагменты.
- Только WAV без Warp и Loop на текущем этапе.

**Внимание:** v0.2 проверена локальными тестами, но ещё не подтверждена в реальном Live. Используйте только на копии Live Set. Подробности — в `README_RU.md`.

Запуск: `01_INSTALL.command`, перезапуск Ableton, выбор `ClearSilenceBridge` в Control Surface, запуск `Clear Silence.app` или `02_START.command`.

Проект не связан с коммерческим StripSilencer Antoine Delvig.
