.PHONY: help up-ryzon9 up-acer down-ryzon9 down-acer gx10

# Standard-Ziel, das ausgeführt wird, wenn man nur 'make' eintippt
.DEFAULT_GOAL := help

help: ## Zeigt diese Hilfe an
	@echo "Verfügbare Befehle:"
	@echo "-----------------------------------------------------------------------"
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_-]+:[^:].*##/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "-----------------------------------------------------------------------"
	@echo "Beispiel: make -j up-acer gx10 MODE=request"

# 1. RAG Stack auf Ryzon9 AUßER GUI (da VSCode das dort im dev mode macht)
up-ryzon9: ## RAG Stack auf Ryzon9 starten (ohne GUI)
	ansible-playbook -i ansible/inventory.ini ansible/deploy.yaml -e target_host=ryzon9 --skip-tags gui_dev

down-ryzon9: ## RAG Stack auf Ryzon9 stoppen
	ansible-playbook -i ansible/inventory.ini ansible/deploy.yaml -e target_host=ryzon9 -e target_state=absent

# 2. RAG Stack auf Acer INKLUSIVE GUI
up-acer: ## RAG Stack auf Acer starten (inklusive GUI)
	ansible-playbook -i ansible/inventory.ini ansible/deploy.yaml -e target_host=acer

down-acer: ## RAG Stack auf Acer stoppen
	ansible-playbook -i ansible/inventory.ini ansible/deploy.yaml -e target_host=acer -e target_state=absent

# 3. GX10 Remote Steuerung mit den Argumenten: MODE (request, ingestion, kombi) und STATE (present, absent)
MODE ?= request
STATE ?= present

gx10: ## GX10 Microservices remote starten/stoppen: make gx10 MODE=[request|ingestion|kombi] STATE=[present|absent]
	ansible-playbook -i ansible/inventory.ini ansible/deploy_gx10.yaml \
		-e target_mode=$(MODE) \
		-e target_state=$(STATE)
