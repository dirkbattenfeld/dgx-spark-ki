import sqlite3
import json
from typing import Optional, List, Dict, Any
from rag_gui.core.base import StateRepository
import os

class SQLiteRepository(StateRepository):
    def __init__(self, db_path: str = "/tmp/dev_state.db", clear_on_start: bool = False):
        self.db_path = db_path
        if clear_on_start and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass
        self._init_db()


    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, active_session_id TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, user_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(user_id))")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    user_query TEXT,
                    llm_answer TEXT,
                    prompt_query TEXT,
                    prompt_llm TEXT,
                    chat_settings TEXT,
                    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # ERWEITERT: turn_chunks speichert nun alle Metadaten und Scores direkt ab
            conn.execute("""
                CREATE TABLE IF NOT EXISTS turn_chunks (
                    turn_id TEXT, 
                    chunk_id TEXT, 
                    chunk_text TEXT,
                    source_path TEXT,
                    headings TEXT,
                    qdrant_score REAL,
                    reranker_score REAL,
                    raw_json TEXT,
                    PRIMARY KEY (turn_id, chunk_id), 
                    FOREIGN KEY (turn_id) REFERENCES turns(turn_id)
                )
            """)
            conn.execute("CREATE TABLE IF NOT EXISTS basket (user_id TEXT, chunk_id TEXT, PRIMARY KEY (user_id, chunk_id), FOREIGN KEY (user_id) REFERENCES users(user_id))")
            conn.commit()
                
    
    async def set_active_session(self, user_id: str, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # KORREKTUR: 'ON CONFLICT DO UPDATE' modifiziert die Zeile in-place,
            # ohne sie zu löschen. Das verhindert Foreign-Key-Abstürze bei bestehenden Usern!
            conn.execute("""
                INSERT INTO users (user_id, active_session_id) 
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET active_session_id = excluded.active_session_id
            """, (user_id, session_id))
            
            # Session eintragen, falls sie noch fehlt
            conn.execute("INSERT OR IGNORE INTO sessions (session_id, user_id) VALUES (?, ?)", (session_id, user_id))
            conn.commit()
            
    async def get_active_session(self, user_id: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT active_session_id FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    
    async def add_turn(
        self,
        turn_id: str,
        session_id: str,
        user_query: str,
        prompt_query: str,
        prompt_llm: str,
        chat_settings: Dict,
        llm_answer: str,
        chunks_data: List[Dict[str, Any]]
        ):
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("INSERT INTO turns (turn_id, session_id, user_query, prompt_query, prompt_llm, chat_settings, llm_answer) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                         (turn_id, session_id, user_query, prompt_query, prompt_llm, json.dumps(chat_settings), llm_answer))
            
            # ÄNDERUNG: Iteration über bereits flache Pydantic-Dicts (kein tiefes Parsen mehr nötig!)
            for c in chunks_data:
                c_id = c.get("id")
                if not c_id:
                    continue
                    
                # headings ist im Pydantic-Modell bereits ein flacher String
                headings_str = c.get("headings") or ""

                conn.execute("""
                    INSERT OR IGNORE INTO turn_chunks 
                    (turn_id, chunk_id, chunk_text, source_path, headings, qdrant_score, reranker_score, raw_json) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    turn_id, 
                    c_id, 
                    c.get("text", ""), 
                    c.get("source_path", "Unbekannter Pfad"),
                    headings_str,
                    c.get("qdrant_score", 0.0),
                    c.get("reranker_score", 0.0),
                    json.dumps(c) # ÄNDERUNG: Speichert das flache, standardisierte Pydantic-JSON
                ))
            conn.commit()
            

    async def toggle_basket(self, user_id: str, chunk_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM basket WHERE user_id = ? AND chunk_id = ?", (user_id, chunk_id))
            if cursor.fetchone():
                conn.execute("DELETE FROM basket WHERE user_id = ? AND chunk_id = ?", (user_id, chunk_id))
                return False
            conn.execute("INSERT INTO basket (user_id, chunk_id) VALUES (?, ?)", (user_id, chunk_id))
            return True


    async def get_basket(self, user_id: str) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT chunk_id FROM basket WHERE user_id = ?", (user_id,))
            return [row[0] for row in cursor.fetchall()]
        
        
    async def get_turns_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Holt alle Turns einer Session inklusive aller gespeicherten Chunk-Details aus SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute("""
                SELECT turn_id, user_query, prompt_query, prompt_llm, chat_settings, llm_answer 
                FROM turns WHERE session_id = ? ORDER BY created_at ASC
            """, (session_id,))
            
            turns = []
            for row in cursor.fetchall():
                turn_id = row["turn_id"]
                
                c_cursor = conn.execute("""
                    SELECT raw_json FROM turn_chunks WHERE turn_id = ?
                """, (turn_id,))
                
                db_rows = c_cursor.fetchall()
                
                chunks_list = []
                for row_dict in db_rows: 
                    # ÄNDERUNG: Da raw_json ab jetzt garantiert existiert, laden wir es direkt.
                    # Der komplexe, fehleranfällige Fallback-Zweig wurde restlos gelöscht.
                    if row_dict["raw_json"]:
                        try:
                            chunk_dict = json.loads(row_dict["raw_json"])
                            chunks_list.append(chunk_dict)
                        except Exception as e:
                            print(f"❌ Kritisches DB-Fehlverhalten: raw_json für Turn {turn_id} beschädigt: {e}")
                
                try:
                    settings_dict = json.loads(row["chat_settings"]) if row["chat_settings"] else {}
                except Exception:
                    settings_dict = {}
                
                turns.append({
                    "turn_id": turn_id,
                    "user_query": row["user_query"],
                    "prompt_query": row["prompt_query"],
                    "prompt_llm": row["prompt_llm"],
                    "chat_settings": settings_dict,
                    "answer": row["llm_answer"], # ÄNDERUNG: Stellt sicher, dass das Feld 'answer' mitgegeben wird
                    "chunks": chunks_list # Enthält die flachen, parse-bereiten Dicts für den Orchestrator
                })
            return turns
        
    
    async def clear_basket(self, user_id: str):
        """Löscht alle Einträge im Korb für den spezifischen Benutzer."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM basket WHERE user_id = ?", (user_id,))
            conn.commit()
            print(f"🗄️ DB: Basket für User '{user_id}' in Tabelle 'basket' geleert.")
    
    
    async def get_basket_chunk_texts(self, user_id: str) -> List[str]:
        """
        Holt direkt die Texte aller im Basket liegenden Chunks per SQL-Join.
        Nutzt MAX(tc.rowid) bzw. eine Subquery, um den aktuellsten Textstand zu sichern,
        falls ein Chunk über mehrere Turns hinweg gefunden wurde.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Subquery stellt sicher, dass wir bei Duplikaten pro chunk_id den Turn mit der höchsten ID erwischen
            cursor = conn.execute("""
                SELECT tc.chunk_text 
                FROM basket b
                INNER JOIN turn_chunks tc ON b.chunk_id = tc.chunk_id
                WHERE b.user_id = ?
                  AND tc.turn_id = (
                      SELECT MAX(inner_tc.turn_id) 
                      FROM turn_chunks inner_tc 
                      WHERE inner_tc.chunk_id = tc.chunk_id
                  )
                GROUP BY tc.chunk_id
            """, (user_id,))
            
            return [row[0] for row in cursor.fetchall() if row[0]]
                
                
    async def get_basket_chunk_texts_alt(self, user_id: str) -> List[str]:
        """
        Holt direkt die Texte aller im Basket liegenden Chunks per SQL-Join.
        Nutzt MAX(turn_id) im Group By, falls ein Chunk in mehreren Turns vorkommt,
        um den aktuellsten Textstand zu sichern.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT tc.chunk_text 
                FROM basket b
                INNER JOIN turn_chunks tc ON b.chunk_id = tc.chunk_id
                WHERE b.user_id = ?
                GROUP BY tc.chunk_id
            """, (user_id,))
            
            # Gibt eine flache Liste der Texte zurück
            return [row[0] for row in cursor.fetchall() if row[0]]


