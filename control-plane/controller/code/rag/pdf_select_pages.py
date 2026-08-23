import os
from PyPDF2 import PdfReader, PdfWriter
from typing import List, Tuple

# 1. Arbeitsverzeichnis definieren
WORKING_DIR = "./meine_pdfs"

# 2. Input-Liste definieren
# Struktur: (Dateiname, [(Startseite, Endseite), ...])
# Hinweis: Die Seitenzahlen im Code sind 0-basiert (Seite 1 = Index 0)
pdf_config = [
    ("jahresbericht_2023.pdf", [(0, 2), (10, 15)]),
    ("henkel_nachhaltigkeit.pdf", [(5, 10)]),
]

def split_pdf_pages(config: List[Tuple[str, List[Tuple[int, int]]]], base_path: str):
    # Sicherstellen, dass das Verzeichnis existiert
    if not os.path.exists(base_path):
        print(f"Fehler: Verzeichnis {base_path} nicht gefunden.")
        return

    # 3. Über die Liste iterieren
    for filename, page_ranges in config:
        input_path = os.path.join(base_path, filename)
        
        if not os.path.exists(input_path):
            print(f"Datei übersprungen: {filename} existiert nicht.")
            continue

        try:
            # 4. PDF laden
            reader = PdfReader(input_path)
            writer = PdfWriter()

            print(f"Verarbeite: {filename}...")

            # 5. Selektierte Seitenbereiche behalten
            for start, end in page_ranges:
                # Wir gehen davon aus, dass 'end' inklusive ist
                for page_num in range(start, end + 1):
                    if page_num < len(reader.pages):
                        writer.add_page(reader.pages[page_num])
                    else:
                        print(f"  Warnung: Seite {page_num+1} nicht in {filename} vorhanden.")

            # 6. Als PDF abspeichern mit Suffix "_selection"
            name_part, extension = os.path.splitext(filename)
            output_filename = f"{name_part}_selection{extension}"
            output_path = os.path.join(base_path, output_filename)

            with open(output_path, "wb") as output_file:
                writer.write(output_file)
            
            print(f"  Erfolgreich gespeichert: {output_filename}")

        except Exception as e:
            print(f"  Fehler beim Verarbeiten von {filename}: {e}")

if __name__ == "__main__":
    split_pdf_pages(pdf_config, WORKING_DIR)
