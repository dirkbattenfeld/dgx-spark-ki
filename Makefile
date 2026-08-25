.PHONY: help up down gx10

# Standard-Ziel, das ausgeführt wird, wenn man nur 'make' eintippt
.DEFAULT_GOAL := help

# Parameter-Defaults für den GX10
MODE ?= request
STATE ?= present

help: ## Zeigt diese Hilfe an
	@echo "Verfügbare Befehle:"
	@echo "-----------------------------------------------------------------------"
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_-]+:[^:].*##/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "-----------------------------------------------------------------------"
	@echo "Beispiel: make -j up-acer gx10 MODE=request"

# RAG Stack auf aktivem PC (s. active_pc_host in main.yaml) starten
up: ## RAG Stack auf aktivem PC starten (automatischer GUI Start in local_machines.yaml konfigurierbar)
	ansible-playbook -i ansible/inventory.ini ansible/deploy_pc.yaml

down: ## RAG Stack auf aktivem PC stoppen
	ansible-playbook -i ansible/inventory.ini ansible/deploy_pc.yaml -e target_state=absent

# GX10 Remote Steuerung mit den Argumenten: MODE (request, ingestion, kombi) und STATE (present, absent)
gx10: ## GX10 Microservices remote starten/stoppen: make gx10 MODE=[request|ingestion|kombi] STATE=[present|absent]
	ansible-playbook -i ansible/inventory.ini ansible/deploy_gx10.yaml \
		-e target_mode=$(MODE) \
		-e target_state=$(STATE)
