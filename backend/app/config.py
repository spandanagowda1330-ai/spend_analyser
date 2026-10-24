from pydantic_settings import BaseSettings, SettingsConfigDict

CURRENCY_SYMBOLS = {
    "USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$",
    "CAD": "C$", "SGD": "S$", "AED": "AED ",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    currency: str = "USD"   # set CURRENCY=INR in .env for rupees

    @property
    def currency_symbol(self) -> str:
        code = self.currency.strip().upper()
        return CURRENCY_SYMBOLS.get(code, code + " ")


settings = Settings()
