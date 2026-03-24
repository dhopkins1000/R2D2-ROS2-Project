# ADR 005 – micro-ROS via Prebuilt Library statt micro_ros_platformio

## Status
Accepted

## Context
`micro_ros_platformio` versucht micro-ROS aus Source zu bauen und benötigt
dafür eine vollständige ROS2 CMake-Umgebung. Auf Jazzy/ARM64 fehlen
bestimmte CMake-Pakete (rmw_test_fixture, rosidl_typesupport_cpp u.a.)
die nicht als apt-Pakete verfügbar sind.

## Decision
Prebuilt static library aus dem `micro_ros_arduino` GitHub Release
direkt in PlatformIO einbinden, ohne Source-Build.

## Lösung
```bash
# Einmalig: prebuilt library herunterladen
bash esp32/r2d2_chassis_esp32/scripts/build_microros_lib.sh

# Danach normal bauen + flashen
cd esp32/r2d2_chassis_esp32
pio run --target upload
```

## Reasons
- micro_ros_platformio Source-Build schlägt auf Jazzy/ARM64 fehl
- Prebuilt library aus micro_ros_arduino ist stabil und getestet
- Kein ROS2 CMake-Environment zur Build-Zeit nötig
- Gleiche API, gleiche Funktionalität

## Consequences
- Library muss bei micro-ROS Version-Updates manuell aktualisiert werden
- `build_microros_lib.sh` Script im Repo dokumentiert den Prozess
- Kompilierung und Upload funktionieren zuverlässig vom Pi aus
