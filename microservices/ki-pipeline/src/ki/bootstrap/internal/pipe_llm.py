#ki/bootstrap/internal/pipe_llm.py
#Füllt component_registry mit den Komponenten für die Pipeline ki/pipelines/llm

# Promptfactory befüllen mit prompts
from ki.promptfactory.prompts import bootstrap

# component_registry mit Pipeline LLM Komponenten befüllen
from ki.pipelines.llm import QuestionLoader, QuestionSelector, QuestionSelectorDB, HeadPromptLlm, NLIModelEvaluator, PostgresWriter, PostgresNLIReport
