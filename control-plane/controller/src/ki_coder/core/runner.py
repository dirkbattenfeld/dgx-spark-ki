import time
from openai import OpenAI

class InferenceRunner:
    def __init__(self, config: dict):
        self.client = OpenAI(base_url=config["api_url"], api_key="not-needed")
        self.config = config

    def run(self, system_prompt: str, user_request: str):
        start_time = time.time()
        first_token_time = None
        full_content = []
        token_count = 0
        usage_data = None

        stream = self.client.chat.completions.create(
            model=self.config['model_name'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request}
            ],
            temperature=self.config.get('temperature', 0.1),
            stream=True,
            stream_options={"include_usage": True}
        )

        for chunk in stream:
            if hasattr(chunk, 'usage') and chunk.usage:
                usage_data = chunk.usage
            if chunk.choices and chunk.choices[0].delta.content:
                if first_token_time is None:
                    first_token_time = time.time()
                content = chunk.choices[0].delta.content
                full_content.append(content)
                token_count += 1

        end_time = time.time()
        ttft = (first_token_time - start_time) if first_token_time else 0
        gen_dur = (end_time - first_token_time) if first_token_time else 0.001

        return {
            "response": "".join(full_content),
            "metrics": {
                "ttft_s": round(ttft, 3),
                "total_duration_s": round(end_time - start_time, 3),
                "tps": round(token_count / gen_dur, 2)
            },
            "usage": usage_data.to_dict() if usage_data else {}
        }

