"""Configuration module."""
import os

from krakendca.config_store import (
    ConfigValidationError,
    get_cli_dca_pairs,
    load_config,
    validate_config,
)
from yaml.scanner import ScannerError

CONFIG_ERROR_MSG: str = "Configuration file incorrectly formatted"


class Config:
    """
    Configuration object based on configuration file.
    """

    api_public_key: str
    api_private_key: str
    dca_pairs: list

    def __init__(self, config_file: str) -> None:
        """
        Read the configuration file and initialize the Config object.

        :param config_file: Configuration file path as string.
        :return: None
        """
        try:
            config = validate_config(load_config(config_file))
            api_config = config.get("api") or {}
            self.api_public_key = api_config.get("public_key")
            if self.api_public_key is None:
                self.api_public_key = os.getenv("KRAKEN_API_PUBLIC_KEY")
            self.api_private_key = api_config.get("private_key")
            if self.api_private_key is None:
                self.api_private_key = os.getenv("KRAKEN_API_PRIVATE_KEY")
            self.dca_pairs = get_cli_dca_pairs(config)
        except EnvironmentError:
            raise FileNotFoundError("Configuration file not found.")
        except ScannerError as e:
            raise ScannerError(CONFIG_ERROR_MSG + f": {e}")
        except ConfigValidationError as e:
            raise ValueError(CONFIG_ERROR_MSG + f": {e}")
