import logging
from typing import Dict

import yaml


def load_config(config_path: str = "config.yaml") -> Dict:
    """Loads the configuration from the specified YAML file."""
    try:
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
            if not isinstance(config_data, dict):
                print(f"Error: Configuration file {config_path} did not load as a dictionary.")
                exit(1)
            # Convert logging level string to actual level
            log_level_str = config_data.get("logging_level", "INFO").upper()
            config_data["logging_level"] = getattr(logging, log_level_str, logging.INFO)
        return config_data
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML in {config_path}: {e}")
        exit(1)
    except AttributeError:
        print(f"Error: Invalid logging level '{log_level_str}' in config file")
        exit(1)
    except KeyError as e:
        print(f"Error: Missing key in config file: {e}")
        exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while loading config: {e}")
        exit(1)


# Load configuration at the start when this module is imported
config = load_config()

# Example of accessing config values (optional, for clarity)
# print(f"LLM Model from config: {config.get('llm_model')}")
