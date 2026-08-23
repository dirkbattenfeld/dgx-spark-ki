# rag_gui/nicegui/ui.py
import os
import asyncio
import json
from nicegui import app, ui
from fastapi import Request
from rag_gui.core.config_core import core_orchestrator
from rag_gui.nicegui.presenter import NiceGUICockpitPresenter

@ui.page("/")
def index_page(request: Request):
    params = request.query_params
    user_id = params.get("user_id", "").strip()

    if not user_id:
        ui.label("❌ Zugriff verweigert: Keine UserID übergeben.").classes("text-red-500 text-xl font-bold p-4")
        return

    # 1. UI-Container & Elemente definieren
    ui.label(f"🎛️ RAG-Cockpit für: {user_id}").classes("text-2xl font-bold mb-4 text-slate-800")
    
    with ui.card().classes("w-full p-4 mb-4 bg-slate-50"):
        ui.label("⚙️ System-Zustand").classes("text-lg font-semibold text-slate-700")
        session_label = ui.label("Lade Sitzungskontext...")
    
    with ui.card().classes("w-full p-4 mb-4"):
        with ui.row().classes("w-full justify-between items-center mb-2"):
            ui.label("📥 Aktueller Dokumentenkorb").classes("text-lg font-semibold text-slate-700")
            clear_basket_btn = ui.button("Korb leeren", icon="delete_sweep").props("flat color=red density=compact")
        basket_container = ui.column().classes("w-full gap-2")

    with ui.card().classes("w-full p-4"):
        ui.label("📜 Turn- & Retrieval-Historie").classes("text-lg font-semibold mb-2 text-slate-700")
        with ui.scroll_area().classes("h-[50vh] w-full border rounded p-3 bg-slate-50"):
            history_container = ui.column().classes("w-full gap-4")

    # 2. Presenter initialisieren
    presenter = NiceGUICockpitPresenter(orchestrator=core_orchestrator, user_id=user_id)
    
    # 3. Reine UI-Render-Funktion (Framework-spezifisch)
    async def render(): 
        try:    
            view_state = await presenter.get_view_state()
                        
            # Session label aktualisieren
            session_label.set_text(f"Aktive Session: {view_state['active_session']}")
            
            # Basket rendern
            basket_container.clear()
            with basket_container:
                if not view_state["basket_ids"]:
                    ui.label("Der Wissenskorb ist momentan leer.").classes("text-gray-400 italic text-sm")
                else:
                    for b_id in view_state["basket_ids"]:
                        with ui.row().classes("w-full items-center justify-between bg-gray-50 p-2 rounded shadow-sm"):
                            ui.label(f"📦 Chunk: {b_id[:12]}...").classes("font-mono text-xs")
                            ui.button(icon="delete", on_click=lambda cid=b_id: asyncio.create_task(presenter.toggle_chunk(cid))).props("flat color=red density=compact")

            # Historie rendern
            history_container.clear()
            with history_container:
                if not view_state["history_turns"]:
                    ui.label("Noch keine Interaktionen in dieser Session.").classes("text-gray-400 italic text-sm")
                else:
                    total_turns = len(view_state["history_turns"])
                    for idx, turn in enumerate(view_state["history_turns"]):
                        display_turn_num = total_turns - idx
                        
                        # 3. Zuerst wird wie gehabt der User Prompt gerendert
                        with ui.card().classes("w-full p-3 bg-white border border-slate-200 shadow-sm"):
                            with ui.row().classes("w-full justify-between items-center"):
                                ui.label(f"💬 Turn {display_turn_num}: {turn['user_query']}").classes("font-bold text-slate-800")
                                if idx == 0:
                                    ui.badge("NEUSTER TURN", color="green")
                                    
                            # Ausgabe der ausgeführten prompt_query, prompt_llm und der verwendeten Chat Settings. 
                            with ui.expansion("Pipeline-Inspektor (Query-Rewriting & Settings)", icon="insights").classes("w-full mt-2 bg-slate-100 rounded border text-xs"):
                                with ui.column().classes("w-full p-3 gap-2"):
                                    ui.label("Tatsächlich ausgeführte Such-Query (prompt_query):").classes("font-semibold text-slate-700 mt-1")
                                    ui.label(turn.get("prompt_query") or "Keine Such-Query ausgeführt (Plain Mode)").classes("p-2 bg-slate-50 border rounded font-mono w-full text-slate-800")
                                    
                                    ui.label("Tatsächlicher LLM Context-Prompt (prompt_llm):").classes("font-semibold text-slate-700 mt-1")
                                    with ui.scroll_area().classes("h-32 w-full border rounded p-2 bg-slate-50 font-mono text-slate-800"):
                                        ui.label(turn.get("prompt_llm") or "Kein Prompt generiert")
                                        
                                    ui.label("Verwendete Chat-Settings:").classes("font-semibold text-slate-700")
                                    ui.code(json.dumps(turn.get("chat_settings", {}), indent=2), language="json").classes("w-full bg-slate-200 p-2 rounded text-slate-800")
                            
                            # Generierte Antwort des Modells
                            if turn.get("answer"):
                                with ui.expansion("Antwort anzeigen", icon="chat", value=False).classes("w-full mt-2 bg-slate-50 rounded border text-sm"):
                                    ui.markdown(turn["answer"]).classes("p-3")

                            # 3. Eingerückt die zugehörigen Chunks (absteigend sortiert nach rerank_score)
                            if turn["chunks"]:
                                ui.label("Zugehörige Quell-Chunks (nach ReRanker-Score absteigend sortiert):").classes("text-xs font-semibold text-slate-500 mt-3 pl-1")
                                
                                with ui.column().classes("w-full gap-2 mt-1"): 
                                    for c_idx, chunk in enumerate(turn["chunks"]):
                                        # ÄNDERUNG: Abgleich direkt über das Pydantic-Attribut chunk.id gegen basket_ids
                                        is_in = chunk.id in view_state["basket_ids"]
                                        btn_color = "green" if is_in else "grey"
                                        btn_icon = "shopping_cart" if is_in else "add_shopping_cart"
                                        
                                        with ui.row().classes("w-full items-center justify-between bg-slate-50 p-2 rounded border"):
                                            with ui.row().classes("items-center gap-2 text-xs"):
                                                # ÄNDERUNG: ReRanker-Angaben in ein einziges, durchgehend lila Badge zusammengefasst
                                                ui.badge(f"ReRanker: {chunk.rerank_score:.4f} (Rank #{chunk.rerank_rank})", color="purple")
                                                ui.badge(f"Qdrant: {chunk.qdrant_score:.4f} (Rank #{chunk.qdrant_rank})", color="blue")                                
                                                ui.label(f"📂 {chunk.source_path[-30:]}").classes("text-gray-600 font-mono")
                                            
                                            ui.button(
                                                icon=btn_icon, 
                                                # ÄNDERUNG: chunk.id direkt übergeben
                                                on_click=lambda cid=chunk.id: asyncio.create_task(presenter.toggle_chunk(cid))
                                            ).props(f"flat round density=compact color={btn_color}")
                                        
                                        # Ausklappbarer Volltext
                                        # ÄNDERUNG: Zugriff auf chunk.headings und chunk.text per Attribut
                                        with ui.expansion(f"Inhalt & Parent-Text ({chunk.headings or 'Keine Header'})", icon="expand_more").classes("w-full text-xs text-slate-600 border-x border-b rounded-b bg-white"):
                                            with ui.column().classes("w-full p-3 gap-2 bg-slate-50 text-slate-900"):
                                                ui.label("Chunk-Inhalt:").classes("font-semibold text-slate-500")
                                                ui.markdown(chunk.text).classes("p-2 bg-white border rounded w-full")
                                                
                                                ui.label("Parent-Text:").classes("font-semibold text-slate-500 mt-1")
                                                with ui.scroll_area().classes("h-40 w-full p-2 bg-white border rounded"):
                                                    # ÄNDERUNG: chunk.parent_text per Attribut
                                                    ui.markdown(chunk.parent_text)
        
        except Exception as e:
            # Das fängt JEDEN Fehler beim Rendern ab und gibt ihn im Terminal aus!
            print(f"❌ KRITISCHER RENDERING-FEHLER: {e}")
            import traceback
            traceback.print_exc()
            # Optional: Zeige dem Admin/User eine Fehlermeldung direkt in der GUI
            ui.notify(f"Rendering-Fehler: {e}", type="negative", position="top")                                                
                                
    # Event-Verdrahtung in der UI-Schicht
    clear_basket_btn.on_click(lambda: asyncio.create_task(presenter.clear_basket()))
    presenter.bind_render_trigger(render)

# Startup & Run Hooks bleiben identisch...
app.on_startup(lambda: core_orchestrator.event_bus.connect())
ui.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8501)), show=False, title="RAG Cockpit", reload=True)
