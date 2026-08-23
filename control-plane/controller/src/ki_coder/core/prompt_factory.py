class PromptBuilder:
    def __init__(self, revision_system_prompt: str = None):
        self.revision_system_prompt = revision_system_prompt or "Du bist ein Experte für Code-Korrekturen. Behebe die gemeldeten Fehler im vorliegenden Code."

    def build(self, req_item: dict, base_system_prompt: str, context: str = "") -> tuple[str, str]:
        """Gibt (system_prompt, user_prompt) zurück."""
        errors = req_item.get("validation_errors", [])
        last_code = req_item.get("response", "")

        # Falls Fehler existieren -> Revisions-Modus
        if errors and last_code:
            sys_p = self.revision_system_prompt
            user_p = (
                f"KORREKTUR-AUFTRAG:\n"
                f"Im vorherigen Versuch wurden Fehler gefunden.\n\n"
                f"FEHLERBERICHT:\n{chr(10).join(errors)}\n\n"
                f"VORHERIGER CODE:\n{last_code}\n\n"
                f"Bitte korrigiere den Code basierend auf dem Fehlerbericht."
            )
        else:
            # Initialer Modus
            sys_p = f"{context}\n{base_system_prompt}" if context else base_system_prompt
            user_p = req_item['request']

        return sys_p, user_p

