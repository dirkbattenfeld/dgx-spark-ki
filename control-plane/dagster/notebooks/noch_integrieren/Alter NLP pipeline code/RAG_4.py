# Aus dieser Datei noch die parallele Ausführung des LLM in mehreren Containern übernehmen
# oder mehrere Nodes parallel mit Dagster ausführen und dabei den Entrypoint des Containers in die Node Config mappen

# %%
import os
from pathlib import Path
import time
from datetime import datetime
import re
from queue import Queue, Empty
from threading import Thread
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Mapping
import json
import yaml
import requests
from langchain_core.prompts import PromptTemplate
#from langchain.chains import RetrievalQA
#from langchain.chains.retrieval_qa import RetrievalQA
#from langchain.vectorstores import FAISS
#from langchain.embeddings import HuggingFaceEmbeddings

# %%
# ---------------------------------------------------------------------------
# CONFIG LOADER
# ---------------------------------------------------------------------------
class ConfigLoader:
    def __init__(self, config):
        self.config = config        

    def _load_yaml(self, path: str) -> dict:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    def get(self):
        if isinstance(self.config, dict):
            cfg = self.config
        elif isinstance(self.config, str) and os.path.exists(self.config):
            cfg = self._load_yaml(self.config)        
        else:
            raise ValueError(
                "Config muss entweder ein dict oder ein gültiger Pfad zu einer YAML-Datei sein."
            )  

        # question_mode == file und alten Run wieder aufnehmen? 
        # Dann die geloggte Config laden und
        # Hyperparameter "prompt" und "llm_config" mergen
        if cfg.get("question_mode", "") == "file": 
            run_data = cfg["run_data"]
            new_run = run_data["new_run"]
            if new_run == False:
                run_dir = run_data["run_dir"]
                dataset_input_path = run_data["dataset_input_path"]     
                run_config_file = os.path.join(dataset_input_path, run_dir, "config.yaml")
                if os.path.exists(run_config_file):
                    run_config = self._load_yaml(run_config_file)
                    for key in ["prompt", "llm_config"]:
                        cfg.pop(key, None)
                        if key in run_config:
                            cfg[key] = run_config[key]
                else:
                    raise ValueError(
                        "Config File für alten Run befindet sich nicht in: {run_config_file}"
                    )
        self.complete_config = cfg            
        return self.complete_config


# %%
#####################################
# Local LLaMA LLM Klasse
#####################################
# Minimal-Basisklasse LLM, nur damit LangChain die Instanz akzeptiert
class LLM:
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        raise NotImplementedError()

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {}

    @property
    def _llm_type(self) -> str:
        return "custom_llm"

class LocalLlamaLLM(LLM):
    endpoint: Optional[str] = None

    class Config:
        extra = "allow" #erlaubt in Pydantic dynamische Attribute

    def __init__(self, device: str = "cpu", config: Dict[str, Any] = {}):
        super().__init__()
        # Device-basiertes Endpoint-Mapping
        endpoints = {
            "gpu": "http://172.25.0.10:5001/completion",
            "cpu": "http://172.25.0.11:5000/completion",
            "cpu-1": "http://172.25.0.12:5000/completion",
            "cpu-2": "http://172.25.0.13:5000/completion",
            "cpu-3": "http://172.25.0.14:5000/completion"
        }
    
        endpoints_old = {
            "gpu": "http://llama-gpu:5001/completion",
            "cpu": "http://llama-cpu:5000/completion",
            "cpu-1": "http://llama-cpu-1:5000/completion",
            "cpu-2": "http://llama-cpu-2:5000/completion",
            "cpu-3": "http://llama-cpu-3:5000/completion"
        }
        self.endpoint = endpoints.get(device, endpoints["cpu"])
        # Hyperparameter zentral aus config ziehen
        self.n_predict = config["n_predict"]
        self.temperature = config["temperature"]
        self.top_p = config["top_p"]
        self.top_k = config["top_k"]
        self.repeat_penalty = config["repeat_penalty"]
        self.streaming = config["streaming"]
        
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        response = requests.post(
            self.endpoint,
            json={
                "prompt": prompt,
                "n_predict": self.n_predict,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "repeat_penalty": self.repeat_penalty,
                "streaming": self.streaming
            }
        )
        response.raise_for_status()
        data = response.json()
        return data.get("content", "")

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"endpoint": self.endpoint}

    @property
    def _llm_type(self) -> str:
        return "local_llama"

# Hilfsfunktion zum Säubern der Antwort des LLM
def clean_antwort_llm (antwort):
    clean_result = antwort.replace("Answer:", "").strip()
    return clean_result


# %%
#####################################
# Prompt Factory mit Registry
#####################################
class PromptFactory:
    registry = {}

    @classmethod
    def register(cls, key: str):
        def decorator(p_class):
            cls.registry[key] = p_class
            return p_class
        return decorator

    @classmethod
    def build(cls, key: str, config: Dict[str, Any]):
        if key not in cls.registry:
            raise ValueError(f"Prompt type {key} not registered")
        return cls.registry[key](config)

#####################################
# Registry für Prompts
#####################################
@PromptFactory.register("simple")
class SimplePrompt:
    def __init__(self, config: Dict[str, Any]):
        self.template_text = "{question}"
        self.llm_config = config["llm_config"]
        self.llm = LocalLlamaLLM(device=self.llm_config.get("device","cpu"), config=self.llm_config)
        self.prompt_template = PromptTemplate(input_variables=["question"], template=self.template_text)

    def execute(self, question: str) -> str:
        full_prompt = self.prompt_template.format(question=question)
        return self.llm._call(full_prompt)

@PromptFactory.register("context")
class ContextPrompt:
    def __init__(self, config: Dict[str, Any]):
        self.context = config["prompt"]["context"]
        self.template_text = "{context}{question}"
        self.llm_config = config.get("llm_config", {})
        self.llm = LocalLlamaLLM(device=self.llm_config.get("device","cpu"), config=self.llm_config)
        self.prompt_template = PromptTemplate(input_variables=["context","question"], template=self.template_text)

    def execute(self, question: str) -> str:
        full_prompt = self.prompt_template.format(context=self.context, question=question)
        return self.llm._call(full_prompt)

@PromptFactory.register("context_frei")
class ContextPrompt:
    def __init__(self, config: Dict[str, Any]):
        self.context = config["prompt"]["context"]
        self.template_text = config["prompt"]["template_text"]
        self.llm_config = config.get("llm_config", {})
        self.llm = LocalLlamaLLM(device=self.llm_config.get("device","cpu"), config=self.llm_config)
        self.prompt_template = PromptTemplate(input_variables=["context","question"], template=self.template_text)

    def execute(self, question: str) -> str:
        full_prompt = self.prompt_template.format(context=self.context, question=question)
        return self.llm._call(full_prompt)

class RetrievalBase:
    @staticmethod
    def load_vectorstore(path):
        embeddings_name = RetrievalBase._load_metadata(path)
        embedding_model = HuggingFaceEmbeddings(
            model_name=embeddings_name,
            model_kwargs={"device": "cuda"},  #oder cpu, falls keine gpu verfügbar
            encode_kwargs={"normalize_embeddings": True}  # empfohlen für BGE
        )
        vectorstore_path = os.path.join(path, "vectorstore")
        vectorstore = FAISS.load_local(
            vectorstore_path,
            embeddings=embedding_model,
            allow_dangerous_deserialization=True
        )
        return vectorstore, embeddings_name

    @staticmethod
    def _load_metadata(path: str):
        # Pfad zur metadata.json-Datei
        metadata_path = os.path.join(path, "json/metadata.json")
    
        with open(metadata_path, "r", encoding="utf-8") as f:
            loaded_metadata = json.load(f)

        embeddings_name = loaded_metadata["embeddings"]
        return embeddings_name

@PromptFactory.register("retrieval")
class RetrievalPrompt(RetrievalBase):
    def __init__(self, config: Dict[str, Any]):
        self.project_path = config["prompt"]["project_path"]
        self.llm_config = config.get("llm_config", {})
        self.template_text = "Answer the question based on the following documents: {context}. Question: {question}"
        self.llm = LocalLlamaLLM(device=self.llm_config.get("device","cpu"), config=self.llm_config)
        self.prompt_template = PromptTemplate(input_variables=["context","question"], template=self.template_text)
                   
        # Vectorstore laden
        self.vectorstore, self.embeddings_name = RetrievalBase.load_vectorstore(self.project_path)
                
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            retriever=self.vectorstore.as_retriever(),
            chain_type="stuff",
            chain_type_kwargs={"prompt": self.prompt_template}
        )

    def execute(self, question: str) -> str:
        answer = self.qa_chain.run(question)
        return answer


# %%
@dataclass
class PromptItem:
    id: int
    question: str
    answer: Optional[str] = None

class DataHandler:
    def __init__(self, config):
        self.config=config
        self.prompts=[]
        self.question_mode = self.config.get("question_mode", "question_dict")
        if self.question_mode == "question_dict":
            self.question_list = self.config["question_list"]    
        if self.question_mode == "file":
            self.run_data = self.config["run_data"]
            self.dataset_input_path = self.run_data.get("dataset_input_path", "")
            self.dataset_input_file = self.run_data.get("dataset_input_file", "")
            if self.dataset_input_path == "":
                raise ValueError("Pfad zum File mit Prompts fehlt.")    
            if self.dataset_input_file == "":
                raise ValueError("Filename für File mit Prompts fehlt.")
            self.input_filepath = os.path.join(self.dataset_input_path, self.dataset_input_file)
            self.anzahl_prompts = self.run_data["anzahl_prompts"]
            self.new_run = self.run_data["new_run"]
            self.run_dir = self.run_data["run_dir"]
            if self.new_run == False:
                self.run_path = os.path.join(self.dataset_input_path, self.run_dir)
                self.index_file = os.path.join(self.run_path, "index.jsonl")
                
    @staticmethod
    def _newest_file_with_string(directory, substring):
        directory = Path(directory)
        candidates = []
        for file in directory.glob("*"):
            if file.is_file() and substring in file.name:
                candidates.append(file)
        if not candidates:
            return None
        return max(candidates, key=lambda f: f.stat().st_mtime)

    def _fill_promptitems_from_question_list(self, question_list):
        self.prompts = [PromptItem(id=i, question=q)
        for i, q in enumerate(question_list)]    
        return self.prompts
    
    def _fill_promptitems_from_file(self, data, n):
        """
        Füllt eine Queue mit bis zu `n` Prompts aus `data`, die laut index.csv noch nicht bearbeitet wurden.
        return: Queue mit den ausgewählten Einträgen
        """
        count = 0  # Anzahl der hinzuzufügenden Einträge
        
        if self.new_run:
            self.init_new_run()
            start_id = 0
        else:
            # Index lesen
            with open(self.index_file, "r", encoding="utf-8") as f:
                for line in f:
                    pass  # iteriert bis zur letzten Zeile
            if not line.strip():
                raise ValueError("Index-Datei ist leer oder enthält nur Leerzeilen.")
            start_id = json.loads(line)["last_id"] + 1

        # Prompts aus data kopieren
        end_id = min(start_id + n, len(data))
        for i in range(start_id, end_id):
            entry = data[i]
            item = PromptItem(id=i, question=entry["question"])
            self.prompts.append(item)
        return self.prompts
    
    def get_prompts(self):
        if self.question_mode == "question_dict":
            prompts = self._fill_promptitems_from_question_list(self.question_list)
            return prompts
        
        elif self.question_mode == "file":            
            with open(self.input_filepath, "r") as f:
                self.data = json.load(f)
            self.prompts = self._fill_promptitems_from_file(self.data, self.anzahl_prompts)
            return self.prompts
            
        elif question_mode == "API":
            raise NotImplementedError("Option 'API' ist noch nicht implementiert.")
        
        else:
            raise ValueError(f"Unbekannte Option: {question_mode}") 

    def init_new_run(self):
        if self.run_dir == "%AUTO":        
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.run_path = os.path.join(self.dataset_input_path, f"run_{timestamp}")
        else:
            self.run_path = os.path.join(self.dataset_input_path, self.run_dir)
        
        if os.path.exists(self.run_path):
            raise ValueError(
                "Pfad zu neuem Run Directory existiert bereits."
            )     
        else:
            # Run Verzeichnis anlegen
            os.makedirs(self.run_path, exist_ok=False)
            # Config loggen
            config_file = os.path.join(self.run_path, "config.yaml")
            with open(config_file, "w") as f:
                yaml.safe_dump(self.config, f, sort_keys=False)
            # Index anlegen
            self.index_file = os.path.join(self.run_path, "index.jsonl")
            Path(self.index_file).touch(exist_ok=True)
        return

    def save_batch(self):
        # Pfad zur letzten Batch-Datei aus Index holen
        # Falls leere Indexdatei: ""
        index_path = Path(self.index_file)
        if not index_path.exists():
            raise ValueError ("Indexfile defekt oder existiert nicht")
        last_line = ""
        with index_path.open("r", encoding="utf-8") as f:
            for line in f:
                last_line = line
        if not last_line.strip():
            output_path = ""  
        else:  
            try:
                last_entry = json.loads(last_line)
                output_path = last_entry["batch_file"]
            except json.JSONDecodeError:
                raise ValueError ("Indexfile defekt oder existiert nicht")

        # Neuen Output Pfad ermitteln
        if output_path == "":
            output_path = os.path.join(self.run_path, "batch_0000.jsonl")
        else:
            output_path = re.sub(
                r"(\d+)(?=\.jsonl$)",                     
                lambda m: f"{int(m.group(1)) + 1:04d}",  
                str(output_path))
            
        # Prompts in neue Batch Datei schreiben
        with open(output_path, "w", encoding="utf-8") as f:
            for item in self.prompts:
                json_line = json.dumps(item.__dict__, ensure_ascii=False)
                f.write(json_line + "\n")

        # Neuen Eintrag in Index anhängen
        entry = {
            "batch_file": output_path,
            "first_id": self.prompts[0].id,
            "last_id": self.prompts[-1].id
        }
        with open(self.index_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")    

        return  

    def save_batch_failed(self, exception):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.run_path, f"batch_error_{timestamp}.jsonl")
        if self.prompts:
            with open(output_path, "w", encoding="utf-8") as f:
                fehlermeldung = {"Fehler": str(exception)}   
                f.write(json.dumps(fehlermeldung, ensure_ascii=False) + "\n")
                for item in self.prompts:
                    json_line = json.dumps(item.__dict__, ensure_ascii=False)
                    f.write(json_line + "\n")



# %%
#####################################
# Worker Klasse
#####################################
class Worker:
    def __init__(self, worker_id: int, prompt_type: str, config: Dict[str, Any], question_queue: Queue, verbose: bool, error_flag):
        self.worker_id = worker_id
        self.prompt_obj = PromptFactory.build(prompt_type, config)
        self.queue = question_queue
        self.verbose = verbose
        self.error_flag = error_flag

    def run(self):
        print(f"[Worker-{self.worker_id}] gestartet")
        while True:
            if self.error_flag["flag"]:
                break  # Abbrechen, wenn ein anderer Worker einen Fehler hatte
                
            try:
                item = self.queue.get(timeout=2)
            except Empty:
                print(f"[Worker-{self.worker_id}] keine Aufgaben mehr")
                break

            try:
                start = time.time()
                item.answer = clean_antwort_llm(self.prompt_obj.execute(item.question))
                dauer = time.time() - start
                if self.verbose: print(f"[Worker-{self.worker_id}] Prompt {item.id} fertig in {dauer:.2f}s")
            except Exception as e:
                print(f"[Worker-{self.worker_id}] Fehler: {e}")
                self.error_flag["flag"] = True
                self.error_flag["exception"] = e
                break
            finally:
                self.queue.task_done()

#####################################
# Pipeline Klasse
#####################################
class Pipeline:
    def __init__(self, config):      
        config_loader = ConfigLoader(config)
        self.config = config_loader.get()
        self.verbose = self.config.get("verbose", True) or self.config.get("question_mode", "") == "question_dict" 
        self.devices = self.config.get("devices", ["gpu"])
        self.prompt_type = self.config["prompt"]["prompt_type"]
        self.question_mode = self.config.get("question_mode", "")
        if self.question_mode == "file":
            self.run_data = self.config["run_data"]
            self.new_run = self.run_data["new_run"]
        self.datahandler = DataHandler(self.config)
        self.prompts = self.datahandler.get_prompts()
        self.queue = Queue()
        for item in self.prompts: self.queue.put(item)
        self.workers = []

    def run(self):
        error_flag = {"flag": False, "exception": None}
        
        for wid, device in enumerate(self.devices):
            worker_config = self.config.copy()
            worker_config["llm_config"]["device"] = device
            worker_obj = Worker(
                worker_id=wid,
                prompt_type=self.prompt_type,
                config=worker_config,
                question_queue=self.queue,
                verbose=self.verbose,
                error_flag = error_flag 
            )
            t = Thread(target=worker_obj.run)
            t.start()
            self.workers.append(t)

        for t in self.workers:
            t.join()
      
        if self.question_mode == "file":
            if error_flag["flag"]:
                self.datahandler.save_batch_failed(error_flag['exception'])
            else:    
                self.datahandler.save_batch()
        
        if self.verbose:
            for p in self.prompts:
                print("\nQuestion: ", p.question)
                print("Answer:   ", p.answer)
                print("-----------------------")


# %%
#####################################
# Main Beispiel
#####################################
if __name__ == "__main__":
    central_config = {
        "devices": ["gpu", "cpu", "cpu-1", "cpu-2", "cpu-3"],
        "verbose": True,
        "prompt": {
            "prompt_type": "simple",   # simple, context, template, retrieval
            # Für Prompt mit Kontext:
            "context": "Answer the following question short without offering options!",
            # Für Prompt 'template' mit mehreren Variablen
            "template_text": "Answer the following question based on the context provided: Context: {context}. Question: {question}",
            # Für Retrieval Prompt: Pfad zum Projektverzeichnis
            "project_path": "/notebooks/data/journal/Sandel_part"
        },
        
        "llm_config": {
            "device": "gpu",        # Wird für Übergabe an Worker geändert 
            "n_predict": 4096,
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 1,
            "repeat_penalty": 1.0,
            "streaming": False
        },
        "question_mode": "question_dict", #"question_dict", #"file" / "API"

        "run_data": {
            "new_run": True,
            "run_dir": "%AUTO",  # "%AUTO" für automatische Namensvergabe
            "dataset_input_path": "/notebooks/notebooks_eval/TruthfulQA",
            "dataset_input_file": "TruthfulQA_formatted.json",
            "anzahl_prompts": 2
        },

        "question_list1": [
        "What is the capital of France?",
        "Who wrote 'Pride and Prejudice'?",
        "Who was the first Muslim president of the USA?",
        "Who was the first muslim president of the USA?",
        "What is the difference between a Muslim president of the USA and a muslim president of the USA?"
        ], 
        "question_list2": ["What are Sandels main arguments for integrating political philosophy into economics?"],
        "question_list3": ["Summerize the article from Sandel!"],
        "question_list": ["What is the world's prettiest bird?"]
    }

    config = central_config
    #config = central_config
    pipeline = Pipeline(config=config)
    pipeline.run()


# %%
# Aus maingui.py das Wechseln der gguf übernehmen
# Batch Dateien aggregieren und Metrik anwenden, auswerten im Vergleich verschiedener Runs 
# Nutzung in FastAPI
# maingui.py anpassen

# %%
def restart_container(container_name: str = "llama-cpu"):
    client = docker.DockerClient(base_url="unix://var/run/docker.sock")
    try:
        container = client.containers.get(container_name)
        container.restart()
        return f"Container '{container_name}' wurde erfolgreich neu gestartet."
    except Exception as e:
        return f"Fehler beim Neustarten des Containers: {str(e)}"

def finde_gguf_modelle(verzeichnis: str) -> list[str]:
    """
    Liest alle Dateien mit der Endung .gguf im angegebenen Verzeichnis
    und gibt eine sortierte Liste der Dateinamen (ohne Pfad) zurück.
    """
    if not os.path.isdir(verzeichnis):
        return []

    ausschluss = {"llm_modell.gguf", "llm_modell_de.gguf"}
    dateien = [
        f for f in os.listdir(verzeichnis)
        if f.endswith(".gguf") and f not in ausschluss
    ]
    return sorted(dateien)

print(os.getcwd())
print(os.listdir("/"))

model_dir = "/models"

print(os.listdir("/models"))
print(finde_gguf_modelle(model_dir))

def setze_symlink(model_dir, ziel_name, ziel_modell):
    ziel_pfad = os.path.join(model_dir, ziel_name)
    quell_pfad = os.path.join(model_dir, ziel_modell)
    if os.path.islink(ziel_pfad) or os.path.exists(ziel_pfad):
        os.remove(ziel_pfad)
    os.symlink(quell_pfad, ziel_pfad)


# Pfad zu deinen Modellen

#setze_symlink(model_dir, "llm_modell.gguf", modell_gpu)
#restart_container("llama-gpu")
