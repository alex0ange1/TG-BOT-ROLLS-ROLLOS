import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
	BOT_TOKEN: str = os.getenv("BOT_TOKEN")
	MOONSHOT_API_KEY: str = os.getenv("MOONSHOT_API_KEY")


config = Config()