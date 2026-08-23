#ki/bootstrap/internal/pipe_sentiment.py
#Füllt component_registry mit den Komponenten für die Pipeline ki/pipelines/sentiment

# component_registry mit Pipeline sentiment Komponenten befüllen
from ki.pipelines.sentiment import hfloader, rawtosentimentmapper, simplecleaner, stratifiedsampler, hfautotokenizer, hfautoclassificationhead, classificationevaluator, csvloader, hfsentimentpipeline 

