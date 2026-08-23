# applications/rag_gui/chainlit/ui.py
import uuid
import chainlit as cl
from rag_gui.chainlit.config_chainlit import active_presenter
from rag_gui.core.config_core import core_orchestrator
from chainlit.input_widget import Select, Slider, Switch
import traceback


@cl.on_chat_start
async def start():
    # Verbindung zu Redis
    try:
        await core_orchestrator.event_bus.connect()
    except Exception as e:
        print(f"⚠️ Chainlit konnte keine Verbindung zu Redis aufbauen: {e}")

    # User ID abfragen
    res = await cl.AskUserMessage(
        content="Willkommen! Bitte geben Sie Ihre UserID ein, um zu beginnen.", 
        timeout=240
    ).send()
    
    if res is None or "output" not in res:
        user_id = "DefaultUser"  # Fallback, damit das System nicht crasht
    else:
        user_id = res["output"].strip()
    
    session_id = str(uuid.uuid4())
    
    nicegui_url = f"http://localhost:8501/?user_id={user_id}"
    await cl.Message(
        content=f"Hallo {user_id}! Dein RAG Cockpit findest du hier: [RAG Cockpit öffnen]({nicegui_url})"
    ).send()
    
    await active_presenter.orchestrator.set_user_active_session(user_id, session_id)
    cl.user_session.set("user_id", user_id)
    cl.user_session.set("id", session_id)   
   
    # Qdrant Collections holen
    available_collections = await active_presenter.get_collections()
    
    settings = await cl.ChatSettings([
        Select(
            id="compute_mode",
            label="🧠 Betriebsmodus",
            values=["RAG Retrieval (neue Chunks suchen)", "LLM (auf selektierten chunks)", "Plain LLM"],
            initial_index=0,
            description="Bestimmt, ob das Modell auf den im Warenkorb ausgewählten Chunks rechnet oder neu sucht."
        ),
        # Qdrant
        Select(
            id="collection_name",
            label="📂 Qdrant Collection",
            values=available_collections,  # Deine Collections
            initial_index=0,
        ),
        Slider(
            id="limit",
            label="🔍 Qdrant Limit (Roh-Suche)",
            initial=50,
            min=1,
            max=200,
            step=1,
        ),
        Slider(
            id="score_threshold",
            label="🎯 Qdrant Score Threshold",
            initial=0.5,
            min=0.0,
            max=1.0,
            step=0.05,
        ),
        # RERANKER
        Slider(
            id="top_n",
            label="✂️ ReRanker Top-N (an LLM)",
            initial=5,
            min=1,
            max=20,
            step=1,
        ),
        # GENERATE LLM
        Slider(
            id="temperature",
            label="🌡️ LLM Temperature",
            initial=0.2,
            min=0.0,
            max=2,
            step=0.1,
        ),
        Slider(
            id="max_tokens",
            label="🪙 LLM Max Tokens",
            initial=1024,
            min=256,
            max=16384,
            step=256,
        ),
        Switch(
            id="display_chunks",
            label="📄 Gefundene Dokumente anzeigen",
            initial=False,
        ),           
    ]).send()

    cl.user_session.set("pipeline_settings", settings)
    # Nur für Kompatibilität zum alten Code (ToDo)
    cl.user_session.set("compute_mode", settings["compute_mode"])
    
    active_presenter.update_session_settings(session_id, settings)
    
    await cl.Message(content="### 🎛️ Information-Retrieval-System betriebsbereit").send()


@cl.on_settings_update
async def setup_agent(settings):
    session_id = cl.user_session.get("id")
    if session_id:
        active_presenter.update_session_settings(session_id, settings)
        
    cl.user_session.set("pipeline_settings", settings)
    # Nur für Kompatibilität zum alten Code (ToDo)
    cl.user_session.set("compute_mode", settings["compute_mode"])
    print(f"⚙️ Parameter-Update empfangen und an Presenter weitergeleitet: {settings}")
        

@cl.on_message
async def main(message: cl.Message):
    try:
        session_id = cl.user_session.get("id")
        user_id = cl.user_session.get("user_id")
        current_mode = cl.user_session.get("compute_mode") or "Plain LLM"
        text = message.content.strip()

        if not user_id or not session_id:
            await cl.Message(content="❌ **Fehler:** Sitzungskontext verloren. Bitte lade die Seite neu.").send()
            return

        # Modus-Weiche ausführen
        if "RAG Retrieval" in current_mode:
            result = await active_presenter.handle_rag_query(text, session_id, user_id)
        elif "selektierten chunks" in current_mode:
            result = await active_presenter.handle_basket_compute(text, session_id, user_id)
        else: 
            result = await active_presenter.handle_plain_compute(text, session_id, user_id)
            
        if not result or "answer" not in result:
            await cl.Message(content="⚠️ **Warnung:** Das Backend lieferte eine leere Antwortstruktur.").send()
            return

        # 1. Hauptantwort ausgeben
        await cl.Message(content=result["answer"]).send()
        
        # 2. Chunks verarbeiten
        chunks = result.get("chunks", [])
        basket = await active_presenter.get_basket(user_id)
        
        # 3. Chunks ausgeben wenn in chat settings gewünscht
        chat_settings = cl.user_session.get("chat_settings") or {}
        show_chunks_in_ui = chat_settings.get("display_chunks", False)
        
        if chunks and show_chunks_in_ui:
            await cl.Message(content="--- \n### 📄 Gefundene Quell-Chunks (Nachweis & Relevanz):").send()
            
            for idx, chunk in enumerate(chunks):  
                # ÄNDERUNG: Direkter Zugriff auf Pydantic-Attribute statt Dictionary-Lookups!
                chunk_id = chunk.id or f"chunk_{idx}"
                
                in_basket = chunk_id in basket
                button_label = "🗑️ Aus Korb entfernen" if in_basket else "➕ In Korb legen"

                actions = [
                    cl.Action(
                        name="toggle_chunk", 
                        value=chunk_id, 
                        label=button_label,
                        payload={"chunk_id": chunk_id, "user_id": user_id}
                    )
                ]
                
                chunk_info_card = (
                    f"**[{idx+1}] {chunk.source_path}**\n"
                    f"↳ *Kontext:* {chunk.headings}\n"
                    f"📊 **Reranker:** `{chunk.rerank_score:.4f}` (Rank #{chunk.rerank_rank}) | "
                    f"**Qdrant:** `{chunk.qdrant_score:.4f}` (Rank #{chunk.qdrant_rank})"
                )
                
                text_element = cl.Text(
                    name=f"Inhalt Chunk {idx+1}", 
                    content=chunk.text,  # text ist ein Pflichtfeld
                    display="inline"
                )

                await cl.Message(
                    content=chunk_info_card,
                    elements=[text_element],
                    actions=actions
                ).send()
                

    except Exception as e:
        # Fehler wird abgefangen und formatiert ausgegeben anstatt lautlos zu sterben
        error_trace = traceback.format_exc()
        await cl.Message(
            content=(
                f"❌ **Kritischer Laufzeitfehler in Pipeline:**\n"
                f"`{str(e)}`\n\n"
                f"**Stacktrace:**\n```python\n{error_trace}\n```"
            )
        ).send()


@cl.action_callback("toggle_chunk")
async def on_action(action: cl.Action):
    try:
        user_id = action.payload.get("user_id")
        chunk_id = action.payload.get("chunk_id")
        
        if not chunk_id or not user_id:
            return
        
        is_now_in_basket = await active_presenter.toggle_chunk(user_id, chunk_id)
        
        if is_now_in_basket:
            action.label = "🗑️ Aus Korb entfernen"
            msg_text = f"📥 Chunk `{chunk_id[:8]}...` in den Korb gelegt."
        else:
            action.label = "➕ In Korb legen"
            msg_text = f"❌ Chunk `{chunk_id[:8]}...` aus dem Korb entfernt."
            
        await cl.Message(content=msg_text).send()
        return action.to_dict()
    except Exception as e:
        await cl.Message(content=f"❌ **Korb-Fehler:** {str(e)}").send()
