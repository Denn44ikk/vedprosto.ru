from ..providers.openai_compatible import OpenAICompatibleProvider


class CheapGPTProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.aiproductiv.ru/v1",
        timeout: float = 90.0,
        max_retries: int = 3,
    ):
        super().__init__(
            name="cheap_gpt",
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
