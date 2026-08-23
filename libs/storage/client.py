import os
import fsspec
from pathlib import Path

class StorageClient:
    def __init__(self):
    # Wir laden die Konfiguration
        self.s3_config = {
            "key": os.getenv("S3_KEY"),
            "secret": os.getenv("S3_SECRET"),
            "client_kwargs": {"endpoint_url": os.getenv("S3_ENDPOINT")}
        }
        
        # Jetzt prüfen wir die Liste der fehlenden Werte wirklich
        missing = [key for key, value in self.s3_config.items() 
                    if value is None or (isinstance(value, dict) and not any(value.values()))]

        if missing:
            raise ValueError(
                f"❌ StorageClient: Folgende S3-Konfigurationen fehlen: {missing}. "
                "Bitte prüfe deine .env Datei."
            )

    def _get_fs(self, path: str):
        if "://" not in path:
            raise ValueError(f"❌ Pfad '{path}' benötigt ein Protokoll.")

        protocol = fsspec.utils.get_protocol(path)
        if protocol == "s3":
            fs = fsspec.filesystem("s3", **self.s3_config)

            # Wir extrahieren dynamisch den Bucket-Namen aus dem Pfad (z.B. 'docling-01')
            try:
                clean_path = path.replace("s3://", "", 1)
                bucket_name = clean_path.split("/")[0]
                if bucket_name:
                    # Ein 'ls' auf den Bucket liest nur – erzeugt aber denselben
                    # internen Cache-Zustand wie dein funktionierender Alibi-Write!
                    fs.ls(bucket_name, detail=False)
            except Exception:
                pass

            return fs
        return fsspec.filesystem(protocol)

    def _get_full_path(self, bucket: str, filename: str = None) -> str:
        # 1. Wenn schon ein Protokoll da ist (s3:// oder file://), dann direkt nutzen
        if "://" in bucket:
            return f"{bucket}/{filename}" if filename else bucket
        
        # 2. Wenn es ein absoluter lokaler Pfad ist (beginnt mit /), nutze file://
        if bucket.startswith("/"):
            return f"file://{bucket}" + (f"/{filename}" if filename else "")
        
        # 3. Fallback: S3-Bucket (dein Standard-Verhalten)
        return f"s3://{bucket}/{filename}" if filename else f"s3://{bucket}"

    def open(self, bucket: str, filename: str = None, mode: str = "r"):
        path = self._get_full_path(bucket, filename)
        fs = self._get_fs(path)
        return fs.open(path, mode)

    def write(self, bucket: str, filename: str = None, content: str = ""):
        path = self._get_full_path(bucket, filename)
        fs = self._get_fs(path)
        with fs.open(path, "w") as f:
            f.write(content)

    def read(self, bucket: str, filename: str = None) -> str:
        path = self._get_full_path(bucket, filename)
        fs = self._get_fs(path)
        with fs.open(path, "r") as f:
            return f.read()

    def exists(self, bucket: str, filename: str = None) -> bool:
        path = self._get_full_path(bucket, filename)
        fs = self._get_fs(path)
        return fs.exists(path)

    def delete(self, bucket: str, filename: str = None):
        path = self._get_full_path(bucket, filename)
        fs = self._get_fs(path)
        if fs.exists(path):
            fs.rm(path)

    def list_files(self, bucket: str, glob_pattern: str = "*"):
        """Gibt eine Liste von vollqualifizierten URLs (s3:// oder file://) zurück."""
        base_path = self._get_full_path(bucket)
        fs = self._get_fs(base_path)
        
        # Protokoll extrahieren (z.B. "s3" oder "file")
        import fsspec
        protocol = fsspec.utils.get_protocol(base_path)
        
        # Holen der nackten Dateien vom Dateisystem/S3
        files = fs.glob(f"{base_path}/{glob_pattern}")
        
        clean_files = []
        for f in files:
            # fsspec liefert Pfade oft ohne Protokoll. Wir säubern sie:
            # (S3 liefert oft 'bucket/key', lokal liefert es '/absolute/path')
            clean_path = f.replace(f"{protocol}://", "", 1)
            
            # Sicherstellen, dass lokale absolute Pfade nicht ihren führenden / verlieren
            if protocol == "file" and not clean_path.startswith("/"):
                clean_path = "/" + clean_path
                
            clean_files.append(f"{protocol}://{clean_path}")
            
        return clean_files
        
    def mkdir(self, bucket: str):
        path = self._get_full_path(bucket)
        fs = self._get_fs(path)
        fs.mkdir(path)
