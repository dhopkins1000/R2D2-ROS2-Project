# R2D2 Startup & Update System

## Konzept

Beim jedem Pi-Boot läuft folgende Sequenz:

```
Boot
  ↓
network-online.target (Netzwerk bereit)
  ↓
r2d2-update.service
  ├── git fetch origin/main
  ├── Wenn Änderungen: git pull + colcon build
  ├── Build OK → exit 0
  └── Build FAIL → exit 1 (r2d2.service geblockt!)
  ↓
r2d2.service (nur wenn r2d2-update.service erfolgreich)
  ├── Xtion Pro + Webcam
  ├── Foxglove Bridge
  └── micro-ROS Agent
```

## Installation

```bash
# Script ausführbar machen
chmod +x ~/ros2_ws/scripts/r2d2-update.sh

# Service installieren
sudo cp ~/ros2_ws/scripts/r2d2-update.service /etc/systemd/system/r2d2-update.service
sudo systemctl daemon-reload
sudo systemctl enable r2d2-update.service

# r2d2.service anpassen – muss NACH r2d2-update warten
# In /etc/systemd/system/r2d2.service unter [Unit] ergänzen:
#   After=r2d2-update.service
#   Requires=r2d2-update.service
```

## r2d2.service anpassen

Die bestehende `/etc/systemd/system/r2d2.service` [Unit]-Sektion muss
ergänzt werden:

```ini
[Unit]
Description=R2D2 Robot Bringup (cameras + Foxglove Bridge)
After=network.target r2d2-update.service
Requires=r2d2-update.service
Conflicts=foxglove-bridge.service
```

## Log überwachen

```bash
# Live-Log des Update-Scripts
journalctl -u r2d2-update -f

# Oder direkt die Log-Datei
tail -f /var/log/r2d2-update.log

# Status beider Services
sudo systemctl status r2d2-update r2d2
```

## Verhalten bei verschiedenen Szenarien

| Szenario | git pull | colcon build | r2d2.service |
|---|---|---|---|
| Kein Netzwerk | ⚠️ skip | ⚠️ skip | ✅ startet (alter Stand) |
| Kein Update nötig | ✅ up to date | ⚠️ skip | ✅ startet |
| Update + Build OK | ✅ pull | ✅ build | ✅ startet (neuer Stand) |
| Update + Build FAIL | ✅ pull | ❌ fail | ❌ geblockt |

## Manuelles Update (ohne Reboot)

```bash
# Update manuell triggern
sudo systemctl start r2d2-update

# Danach ROS2 neu starten
sudo systemctl restart r2d2
```

## Sicherheitsnetz: Rollback

Wenn ein fehlerhafter Commit den Boot kaputt macht:

```bash
# SSH auf den Pi
cd ~/ros2_ws
git log --oneline -5          # letzten Stand sehen
git revert HEAD               # letzten Commit rückgängig machen
git push origin main          # pushen
sudo reboot                   # Pi neu starten
```
