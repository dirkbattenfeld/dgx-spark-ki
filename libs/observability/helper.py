# libs/observability/helper.py

def format_dict_tree(data, indent=0, max_len=50) -> str:
    """Erzeugt eine Baumstruktur-Textrepräsentation eines Dicts oder einer Liste für Logger."""
    lines = []
    prefix = "  " * indent

    # Top-Level List-Handling
    if isinstance(data, list):
        count = len(data)
        lines.append(f"{prefix}list({count} item{'s' if count != 1 else ''})")
        if data:
            lines.append(f"{prefix}└── [item schema]:")
            lines.append(format_dict_tree(data[0], indent + 1, max_len=max_len))
        return "\n".join(lines)

    # Standard Dict-Handling
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}├── {key}:")
                lines.append(format_dict_tree(value, indent + 1, max_len=max_len))
            elif isinstance(value, list):
                count = len(value)
                lines.append(f"{prefix}├── {key}: list({count} item{'s' if count != 1 else ''})")
                if value:
                    lines.append(f"{prefix}  └── [item schema]:")
                    lines.append(format_dict_tree(value[0], indent + 2, max_len=max_len))
            elif isinstance(value, str):
                # Echte Zeilenumbrüche maskieren, damit der Baum nicht bricht
                clean_value = value.replace("\r", "\\r").replace("\n", "\\n")
                length = len(clean_value)
                
                if length <= max_len:
                    lines.append(f"{prefix}├── {key}: \"{clean_value}\"")
                else:
                    truncated = clean_value[:max_len]
                    lines.append(f"{prefix}├── {key}: \"{truncated}...\" | (len={len(value)})")
            elif isinstance(value, (int, float, bool)) or value is None:
                lines.append(f"{prefix}├── {key}: {value}")
            else:
                lines.append(f"{prefix}├── {key}: {type(value).__name__}")

    return "\n".join(lines)

