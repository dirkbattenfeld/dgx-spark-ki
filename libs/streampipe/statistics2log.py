# libs/streampipe/observability.py
import json
import os
from pathlib import Path
import statistics
from collections import defaultdict

def statistics_from_log(filepath: str):
    """Liest das JSON-Logfile und gibt eine aggregierte Performance-Statistik aus."""
    old_path = Path(filepath)
    trace_path = old_path.with_name(f"{old_path.stem}_trace{old_path.suffix}")
    
    if not os.path.exists(trace_path):
        print(f"⚠️ Keine Statistik möglich: Logdatei '{filepath}' existiert nicht.")
        return

    runtimes = defaultdict(list)
    counts = defaultdict(lambda: {"success": 0, "fail": 0})
    
    # Strukturen zur sauberen Trennung einzelner Durchläufe
    current_run_sum = defaultdict(float)
    seen_steps_in_run = defaultdict(set)
    all_completed_pipeline_runs = []

    # Zeilenweises Einlesen des JSON-Lines-Logfiles
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                if not line.startswith("{"):
                    json_start = line.find("{")
                    if json_start == -1:
                        continue
                    line = line[json_start:]

                data = json.loads(line)
                
                if "step" in data and "duration_s" in data:
                    step_name = data["step"]
                    status = data.get("status", "success")
                    duration = data["duration_s"]
                    doc_id = data.get("doc") or "unknown_run"
                    
                    # 1. Statistik für die Einzel-Steps
                    runtimes[step_name].append(duration)
                    status_key = "success" if status == "success" else "fail"
                    counts[step_name][status_key] += 1
                    
                    # 2. Logik zur Erkennung eines neuen Pipeline-Durchlaufs für dieses Dokument:
                    # Wenn dieser Step in dem aktuellen Durchlauf für dieses Dokument schon registriert wurde,
                    # ist der vorherige Durchlauf abgeschlossen.
                    if step_name in seen_steps_in_run[doc_id]:
                        all_completed_pipeline_runs.append(current_run_sum[doc_id])
                        # Zurücksetzen für den neuen Durchlauf
                        current_run_sum[doc_id] = 0.0
                        seen_steps_in_run[doc_id] = set()
                    
                    current_run_sum[doc_id] += duration
                    seen_steps_in_run[doc_id].add(step_name)
            except Exception:
                continue

    # Auch die letzten, noch offenen Durchläufe am Ende des Logs miterfassen
    for doc_id, total_sum in current_run_sum.items():
        if total_sum > 0.0:
            all_completed_pipeline_runs.append(total_sum)

    if not runtimes:
        print("ℹ️ Keine relevanten Pipeline-Schritte im Logfile gefunden.")
        return

    # Ausgabe der Tabelle im Terminal
    print("\n" + "="*80)
    print("📊 AGGREGIERTE PERFORMANCE-STATISTIK")
    print("="*80)
    print(f"{'Step-Name':<22} | {'Durchläufe (S/F)':<18} | {'Min':<9} | {'Max':<9} | {'AVG':<9}")
    print("-"*80)

    for step_name, times in runtimes.items():
        step_counts = counts[step_name]
        total_runs = step_counts["success"] + step_counts["fail"]
        
        min_time = f"{min(times):.3f}s"
        max_time = f"{max(times):.3f}s"
        avg_time = f"{statistics.mean(times):.3f}s"
        
        runs_str = f"{total_runs} ({step_counts['success']}/{step_counts['fail']})"
        print(f"{step_name:<22} | {runs_str:<18} | {min_time:>9} | {max_time:>9} | {avg_time:>9}")
        
    print("="*80)
    
    # Hier ziehen wir jetzt das echte MIN, MAX, AVG aus der Liste aller getrennten Durchläufe
    if all_completed_pipeline_runs:
        run_min = f"{min(all_completed_pipeline_runs):.3f}s"
        run_max = f"{max(all_completed_pipeline_runs):.3f}s"
        run_avg = f"{statistics.mean(all_completed_pipeline_runs):.3f}s"
        
        print(f"{'gesamt:':<43} | {run_min:>9} | {run_max:>9} | {run_avg:>9}")
        print("="*80 + "\n")