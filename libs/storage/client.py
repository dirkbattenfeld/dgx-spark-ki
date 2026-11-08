import os
import fsspec
from pathlib import Path
import re
        
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
        try:
            fs.rm(path)
            # S3FS-Cache für diesen Pfad invalidieren, damit er nicht im Speicher verbleibt
            if hasattr(fs, "invalidate_cache"):
                fs.invalidate_cache(path)
        except Exception as e:
            raise RuntimeError(f"Fehler beim Löschen von '{path}': {e}")
    
    def delete_alt(self, bucket: str, filename: str = None):
        path = self._get_full_path(bucket, filename)
        fs = self._get_fs(path)
        if fs.exists(path):
            fs.rm(path)
            
    def list_files(self, bucket: str, glob_pattern: str = "*"):
        """Gibt eine Liste von vollqualifizierten URLs (s3:// oder file://) zurück."""
        base_path = self._get_full_path(bucket)
        fs = self._get_fs(base_path)
        
        protocol = fsspec.utils.get_protocol(base_path)
        
        # Hilfsfunktion, die z.B. '.pdf' in '.[pP][dD][fF]' umwandelt
        def make_case_insensitive_ext(pat: str) -> str:
            # Sucht nach Endungen am Ende des Musters (z.B. .pdf, .docx)
            match = re.search(r'\.([a-zA-Z0-9]+)$', pat)
            if match:
                ext = match.group(1)
                # Jeden Buchstaben der Endung in [gG] umwandeln
                ci_ext = "".join([f"[{char.lower()}{char.upper()}]" for char in ext])
                return pat[:match.start()] + "." + ci_ext
            return pat

        # Muster aufteilen und case-insensitiv machen
        patterns = [make_case_insensitive_ext(p.strip()) for p in glob_pattern.split(",")]
        raw_files = []
        
        for pat in patterns:
            pattern_path = f"{base_path}/{pat}" if not pat.startswith(base_path) else pat
            raw_files.extend(fs.glob(pattern_path))
            
        # Duplikate entfernen
        files = list(set(raw_files))
        
        clean_files = []
        for f in files:
            clean_path = f.replace(f"{protocol}://", "", 1)
            if protocol == "file" and not clean_path.startswith("/"):
                clean_path = "/" + clean_path
            clean_files.append(f"{protocol}://{clean_path}")
            
        return clean_files

        
    def mkdir(self, bucket: str):
        path = self._get_full_path(bucket)
        fs = self._get_fs(path)
        fs.mkdir(path)
        
    
    def copy_file(self, src_path: str, dest_path: str):
        """
        Kopiert eine Datei über fsspec-Dateisysteme hinweg 
        (z. B. lokal file:// nach S3 s3:// oder innerhalb von S3).
        """
        # Wir ermitteln das Dateisystem anhand des Quellpfads
        fs_src = self._get_fs(src_path)
        fs_dest = self._get_fs(dest_path)
        
        # Falls Quell- und Ziel-Filesystem identisch sind (z.B. S3 -> S3)
        if fs_src.protocol == fs_dest.protocol:
            try:
                fs_src.copy(src_path, dest_path)
                # Cache für Zielpfad invalidieren, falls vorhanden
                if hasattr(fs_dest, "invalidate_cache"):
                    fs_dest.invalidate_cache(dest_path)
                return
            except Exception as e:
                raise RuntimeError(f"❌ [StorageClient] Fehler beim Kopieren von '{src_path}' nach '{dest_path}': {e}")
        
        # Cross-Filesystem (z.B. lokal file:// -> S3 s3://)
        try:
            with fs_src.open(src_path, "rb") as f_src:
                with fs_dest.open(dest_path, "wb") as f_dest:
                    # In Chunks kopieren, um RAM bei großen PDFs (Docling) zu schonen
                    while chunk := f_src.read(1024 * 1024):  # 1 MB Chunks
                        f_dest.write(chunk)
                        
            if hasattr(fs_dest, "invalidate_cache"):
                fs_dest.invalidate_cache(dest_path)
                
        except Exception as e:
            raise RuntimeError(f"❌ [StorageClient] Cross-System-Kopierfehler von '{src_path}' nach '{dest_path}': {e}")

    def ensure_bucket_exists(self, bucket_name: str):
        """
        Prüft, ob ein Bucket existiert, und legt ihn an, falls er fehlt.
        """
        path = self._get_full_path(bucket_name)
        fs = self._get_fs(path)
        
        if not fs.exists(path):
            try:
                fs.mkdir(path)
                print(f"📁 [StorageClient] Bucket/Verzeichnis '{bucket_name}' erfolgreich erstellt.")
            except Exception as e:
                raise RuntimeError(f"❌ [StorageClient] Konnte Bucket '{bucket_name}' nicht erstellen: {e}")

