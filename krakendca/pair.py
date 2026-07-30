"""Pair object module."""
import re
from typing import TypeVar

from krakenapi import KrakenApi

from .utils import find_nested_dictionary

T = TypeVar("T", bound="Pair")


class Pair:
    """
    Kraken pair encapsulation.
    """

    name: str
    alt_name: str
    base: str
    quote: str
    pair_decimals: int
    lot_decimals: int
    quote_decimals: int
    order_min: float

    def __init__(
        self,
        name: str,
        alt_name: str,
        base: str,
        quote: str,
        pair_decimals: int,
        lot_decimals: int,
        quote_decimals: int,
        order_min: float,
    ) -> None:
        """
        Initialize the Pair object.

        :param name:  Pair name.
        :param alt_name: Pair alternative name.
        :param base: Pair base asset.
        :param quote: Pair quote asset.
        :param pair_decimals: Pair decimals.
        :param lot_decimals: Pair lot decimals.
        :param quote_decimals: Pair quote asset decimals.
        :param order_min: Pair minimum order size.
        """
        self.name = name
        self.alt_name = alt_name
        self.base = base
        self.quote = quote
        self.pair_decimals = pair_decimals
        self.lot_decimals = lot_decimals
        self.quote_decimals = quote_decimals
        self.order_min = order_min

    @classmethod
    def get_pair_from_kraken(
        cls, ka: KrakenApi, asset_pairs: dict, pair: str
    ) -> T:
        """
        Initialize the Pair object using KrakenAPI and provided pair.

        :param ka: KrakenApi object.
        :param asset_pairs: Dictionary of available pairs on Kraken
        got through the API.
        :param pair: Pair to dollar cost average as string.
        :return: Instanced Pair object.
        """
        pair_name = cls.resolve_pair_name(asset_pairs, pair)
        pair_information = cls.get_pair_information(asset_pairs, pair_name)
        alt_name = pair_information.get("altname")
        base = pair_information.get("base")
        quote = pair_information.get("quote")
        pair_decimals = pair_information.get("pair_decimals")
        lot_decimals = pair_information.get("lot_decimals")
        order_min = float(pair_information.get("ordermin"))
        quote_information = cls.get_asset_information(ka, quote)
        quote_decimals = quote_information.get("decimals")
        return cls(
            pair_name,
            alt_name,
            base,
            quote,
            pair_decimals,
            lot_decimals,
            quote_decimals,
            order_min,
        )

    @staticmethod
    def get_pair_information(asset_pairs: dict, pair: str) -> dict:
        """
        Return pair information from Kraken API.

        :param asset_pairs: Dictionary of available pairs on Kraken
        got through the API.
        :param pair: Pair to find.
        :return: Dict of pair information.
        """
        pair_name = Pair.resolve_pair_name(asset_pairs, pair)
        pair_information = find_nested_dictionary(asset_pairs, pair_name)
        if not pair_information:
            available_pairs = [pair for pair in asset_pairs]
            raise ValueError(
                f"{pair} pair not available on Kraken. "
                f"Available pairs: {available_pairs}."
            )
        return pair_information

    @staticmethod
    def resolve_pair_name(asset_pairs: dict, pair: str) -> str:
        """
        Resolve user-facing Kraken pair aliases to the canonical pair key.

        :param asset_pairs: Kraken AssetPairs dictionary.
        :param pair: Pair key, altname, wsname, or common BTC alias.
        :return: Canonical Kraken pair key, for example XXBTZEUR.
        """
        query_variants = Pair._identifier_variants(pair)
        for pair_name, pair_information in asset_pairs.items():
            identifiers = Pair._pair_identifier_variants(
                pair_name,
                pair_information,
            )
            if query_variants & identifiers:
                return pair_name

        available_pairs = [pair for pair in asset_pairs]
        raise ValueError(
            f"{pair} pair not available on Kraken. "
            f"Available pairs: {available_pairs}."
        )

    @staticmethod
    def search_asset_pairs(
        asset_pairs: dict,
        query: str = "",
        limit: int = 25,
    ) -> list[dict]:
        """
        Return compact Kraken pair suggestions matching a query.

        :param asset_pairs: Kraken AssetPairs dictionary.
        :param query: User search input.
        :param limit: Maximum number of suggestions.
        :return: List of compact pair suggestion dictionaries.
        """
        normalized_queries = Pair._identifier_variants(query)
        suggestions = []

        for pair_name, pair_information in asset_pairs.items():
            identifiers = Pair._pair_identifier_variants(
                pair_name,
                pair_information,
            )
            if normalized_queries and not Pair._matches_any_query(
                identifiers,
                normalized_queries,
            ):
                continue

            suggestions.append(
                {
                    "pair": pair_name,
                    "altname": pair_information.get("altname"),
                    "wsname": pair_information.get("wsname"),
                    "base": pair_information.get("base"),
                    "quote": pair_information.get("quote"),
                }
            )
            if len(suggestions) >= limit:
                break

        return suggestions

    @staticmethod
    def _pair_identifier_variants(pair_name: str, pair_information: dict) -> set:
        identifiers = set()
        for value in (
            pair_name,
            pair_information.get("altname"),
            pair_information.get("wsname"),
        ):
            identifiers.update(Pair._identifier_variants(value))
        return identifiers

    @staticmethod
    def _identifier_variants(value: object) -> set:
        if not isinstance(value, str):
            return set()

        normalized = value.strip().upper()
        if not normalized:
            return set()

        btc_alias = normalized.replace("BTC", "XBT")
        variants = {normalized, btc_alias}
        for variant in list(variants):
            variants.add(re.sub(r"[^A-Z0-9.]", "", variant))
        return variants

    @staticmethod
    def _matches_any_query(identifiers: set, queries: set) -> bool:
        for query in queries:
            for identifier in identifiers:
                if query in identifier:
                    return True
        return False

    @staticmethod
    def get_asset_information(ka: KrakenApi, asset: str) -> dict:
        """
        Return asset information from Kraken API.

        :param ka: KrakenAPI object.
        :param asset: Asset to find.
        :return: Dict of asset information.
        """
        assets = ka.get_assets()
        asset_information = find_nested_dictionary(assets, asset)
        if not asset_information:
            available_assets = [asset for asset in assets]
            raise ValueError(
                f"{asset} asset not available on Kraken. "
                f"Available assets: {available_assets}."
            )
        return asset_information

    @staticmethod
    def get_pair_ask_price(ka: KrakenApi, pair_name: str) -> float:
        """
        Get pair ask price from Kraken ticker.

        :param ka: KrakenApi object.
        :param pair_name: Pair name to find ask price.
        :return: Current pair ask price.
        """
        pair_ticker_information = ka.get_pair_ticker(pair_name)
        try:
            pair_information = pair_ticker_information[pair_name]
            ask_prices = pair_information["a"]
            if not isinstance(ask_prices, list) or not ask_prices:
                raise TypeError
            return float(ask_prices[0])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"Malformed Kraken ticker response for {pair_name}"
            )
