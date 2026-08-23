import subprocess
import os
import socket

def is_logdy_running(port: int = 8080) -> bool:
    """Prüft, ob auf dem Logdy-Port bereits ein Server lauscht."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_logdy(logfile_path: str):
    """Sorgt dafür, dass Logdy läuft und offen bleibt – ohne Stress."""
    
    # Datei initialisieren, falls sie fehlt
    os.makedirs(os.path.dirname(logfile_path), exist_ok=True)
    if not os.path.exists(logfile_path):
        with open(logfile_path, "w", encoding="utf-8") as f:
            f.write("")

    # Falls Logdy schon läuft (z.B. vom vorherigen Skript-Run), machen wir einfach gar nichts!
    if is_logdy_running(8080):
        print("🔄 Logdy läuft bereits im Hintergrund. Neue Logs werden live gestreamt!")
        return

    print(f"🚀 Starte eine dauerhafte Logdy-Instanz für {logfile_path}...")
    cmd = ["logdy", "follow", logfile_path, "--full-read"]
    
    # Starten OHNE zu blockieren und OHNE Kopplung an dieses Skript (via Popen)
    subprocess.Popen(
        cmd, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL,
        start_new_session=True  # Trennt den Prozess vom Lebenszyklus dieses Python-Skripts
    )
    print("🌐 Logdy geöffnet: http://localhost:8080")
