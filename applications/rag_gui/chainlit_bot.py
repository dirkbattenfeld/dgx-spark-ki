# Ein Bot der in chainlit Testszenarien durchspielt

import asyncio
from playwright.asyncio import phoenix_browser, async_playwright

CHAINLIT_URL = "http://localhost:8000"  # Passe den Port deines Chainlit-Dienstes an

async def run_chainlit_bot():
    async with async_playwright() as p:
        # Wir starten den Browser sicht- oder unsichtbar (headless=False zeigt das Fenster)
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto(CHAINLIT_URL)
        await page.wait_for_load_state("networkidle")

        print("=== Starte Use Case 1: Standard-Chat ===")
        # Chainlit Textarea selektieren, tippen und absenden
        await page.fill("textarea[placeholder*='Message']", "Hallo! Extrahiere bitte die GHG-Kennzahlen für 2025.")
        await page.press("textarea[placeholder*='Message']", "Enter")
        # Kurz warten, bis die Antwort generiert wird (für die Logs)
        await asyncio.sleep(5)

        print("=== Starte Use Case 2: Chat-Settings modifizieren ===")
        # Chainlit hat meist ein Settings-Icon (Zahnrad oder Schieberegler)
        # Wir klicken auf den Button für die Chat-Einstellungen
        await page.click("button[id*='chat-settings']", timeout=5000)
        await asyncio.sleep(1)
        
        # Beispiel: Einen Slider für die Temperature anpassen
        # Hier musst du den exakten Selektor deines Chainlit-Setups prüfen
        # Oft reicht es, nach der Rolle oder dem Text zu suchen
        await page.fill("input[type='number']", "0.2")  # Setzt z.B. Temperature auf 0.2
        await page.click("button:has-text('Save')")    # Falls ein Save-Button existiert
        await asyncio.sleep(1)

        print("=== Starte Use Case 3: Chat mit neuen Settings ===")
        await page.fill("textarea[placeholder*='Message']", "Führe die Analyse nun mit niedrigerer Temperatur aus.")
        await page.press("textarea[placeholder*='Message']", "Enter")
        await asyncio.sleep(8)  # Genug Zeit für den RAG-Workflow im Backend

        await browser.close()
        print("=== Bot-Durchlauf beendet. Logs können inspiziert werden. ===")

if __name__ == "__main__":
    asyncio.run(run_chainlit_bot())


import asyncio
from playwright.asyncio import async_playwright

NICEGUI_URL = "http://localhost:8080"  # Deine NiceGUI-Adresse
CHAINLIT_URL = "http://localhost:8000"  # Deine Chainlit-Adresse

async def run_combined_bot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # headless=False zeigt die Action live
        
        # Wir erstellen zwei separate Browser-Tabs
        nicegui_page = await browser.new_page()
        chainlit_page = await browser.new_page()
        
        print("=== 1. Öffne NiceGUI Cockpit ===")
        await nicegui_page.goto(NICEGUI_URL)
        await nicegui_page.wait_for_load_state("networkidle")
        
        # Use Case 1: In NiceGUI ein Dokument für den Korb auswählen
        # Paßt die Selektoren an deine NiceGUI-Elemente an (z.B. Button-Text)
        await nicegui_page.click("button:has-text('Dokument in Korb legen')")
        print("Logs: Dokumenten-Auswahl in NiceGUI getriggert.")
        await asyncio.sleep(2)
        
        print("=== 2. Wechsel zu Chainlit für Chat-Eingabe ===")
        await chainlit_page.goto(CHAINLIT_URL)
        await chainlit_page.wait_for_load_state("networkidle")
        
        # Use Case 2: In Chainlit die Frage zu dem eben ausgewählten Dokument stellen
        await chainlit_page.fill("textarea[placeholder*='Message']", "Extrahiere die Metriken aus dem eben aktivierten Dokument.")
        await chainlit_page.press("textarea[placeholder*='Message']", "Enter")
        print("Logs: RAG-Anfrage in Chainlit gestartet.")
        await asyncio.sleep(6)  # Zeit für die Verarbeitung
        
        print("=== 3. Zurück zu NiceGUI für Status-Check ===")
        # Bringt den NiceGUI-Tab wieder in den Vordergrund (optional für die Ansicht)
        await nicegui_page.bring_to_front()
        
        # Use Case 3: Prüfen, ob NiceGUI den veränderten Zustand (z.B. Verarbeitungsstatus) anzeigt
        # Hier könntest du ein Element auslesen oder einfach nur warten, um die Backend-Logs zu füllen
        await nicegui_page.click("button:has-text('Aktualisieren')")
        await asyncio.sleep(3)
        
        await browser.close()
        print("=== Multipage-Durchlauf beendet. System-Logs bereit zur Inspektion. ===")

if __name__ == "__main__":
    asyncio.run(run_combined_bot())
