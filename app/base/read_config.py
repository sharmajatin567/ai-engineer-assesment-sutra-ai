import os

import yaml
from dotenv import load_dotenv

CONFIG_PATH = "app/config/config.yaml"


def read_config():
    """Reads config from config.yaml and safe loads for use"""
    load_dotenv(".env")
    for key in ("ANTHROPIC_API_KEY", "TAVILY_API_KEY"):
        if os.environ.get(key) == "":
            del os.environ[key]
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)
