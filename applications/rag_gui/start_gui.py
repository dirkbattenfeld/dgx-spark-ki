# start_stack.py
import subprocess
import sys
import os

def run():
    print("🚀 Starte RAG Full Stack (Chainlit + NiceGUI)...")
    
    # 1. Starte NiceGUI als Hintergrundprozess
    nicegui_process = subprocess.Popen(
        [sys.executable, "/spark/applications/rag_gui/nicegui/ui.py"],
        env=os.environ.copy()
    )
    
    # 2. Starte Chainlit im Vordergrund (blockierend)
    try:
        subprocess.run(
            ["chainlit", "run",
             "/spark/applications/rag_gui/chainlit/ui.py",
             "--port", "8080",
             "--host", "0.0.0.0"],
            check=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Beende RAG Stack...")
    finally:
        # Sicherstellen, dass NiceGUI auch gekillt wird, wenn Chainlit stoppt
        nicegui_process.terminate()
        nicegui_process.wait()

if __name__ == "__main__":
    run()