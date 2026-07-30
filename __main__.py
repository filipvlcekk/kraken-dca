import logging
import os

from krakendca.config import Config
from krakendca.kraken_client import KrakenClient
from krakendca.krakendca import KrakenDCA

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s:%(name)s: %(message)s",
        level=logging.INFO,
    )
    # Get parameters from configuration file.
    current_directory: str = os.path.dirname(os.path.realpath(__file__))
    config_file: str = current_directory + "/config.yaml"
    config: Config = Config(config_file)
    # Initialize the Kraken REST client.
    ka: KrakenClient = KrakenClient(
        config.api_public_key,
        config.api_private_key,
    )
    # Initialize KrakenDCA and handle the DCA based on configuration.
    kdca: KrakenDCA = KrakenDCA(config, ka)
    kdca.initialize_pairs_dca()
    kdca.handle_pairs_dca()
