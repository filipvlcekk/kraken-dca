"""Order object module."""
import csv
import re
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import TypeVar

from krakendca.kraken_client import KrakenClient

T = TypeVar("T", bound="Order")


class Order:
    """
    Kraken order encapsulation.
    """

    date: datetime
    pair: str
    type: str
    order_type: str
    o_flags: str
    pair_price: float
    volume: float
    price: float
    fee: float
    total_price: float
    txid: str
    description: str

    def __init__(
        self,
        date: datetime,
        pair: str,
        type: str,
        order_type: str,
        o_flags: str,
        pair_price: float,
        volume: float,
        price: float,
        fee: float,
        total_price: float,
    ) -> None:
        """
        Initialize the Order object.
        More information on Kraken documentation
        (Add standard order):
        https://www.kraken.com/en-us/features/api

        :param date: Order date as datetime.
        :param pair: Order pair.
        :param type: Buy or sell order.
        :param order_type: Order type.
        :param o_flags: Order additional flags.
        :param volume: Order volume.
        :param price: Order price.
        :param fee: Order fee.
        :param pair_price: Order pair price.
        :param total_price: Total price of the order (order price + fee).
        """
        self.date = date
        self.pair = pair
        self.type = type
        self.order_type = order_type
        self.o_flags = o_flags
        self.pair_price = pair_price
        self.volume = volume
        self.price = price
        self.fee = fee
        self.total_price = total_price

    @classmethod
    def buy_limit_order(
        cls,
        date: datetime,
        pair: str,
        amount: float,
        pair_price: float,
        lot_decimals: int,
        quote_decimals: int,
    ) -> T:
        """
        Create a limit order for specified dca pair and amount.

        :param date: Order date as datetime.
        :param pair: Asset pair.
        :param amount: Amount to buy,
        :param pair_price: Limit order pair price.
        :param lot_decimals: Pair lot decimals.
        :param quote_decimals: Pair quote asset decimals.
        :return: Instance of Order object.
        """
        volume = cls.set_order_volume(amount, pair_price, lot_decimals)
        price = cls.estimate_order_price(volume, pair_price, quote_decimals)
        fee = cls.estimate_order_fee(volume, pair_price, quote_decimals)
        type = "buy"
        order_type = "limit"
        # Pay fee in quote asset.
        o_flags = "fciq"
        total_price = float(
            cls._quantize_quote_value(
                cls._to_decimal(price) + cls._to_decimal(fee),
                quote_decimals,
            )
        )
        return cls(
            date,
            pair,
            type,
            order_type,
            o_flags,
            pair_price,
            volume,
            price,
            fee,
            total_price,
        )

    def send_order(self, ka: KrakenClient) -> None:
        """
        Execute the order by sending it to Kraken API.
        Add the returned TXID and order description to Order object.

        :param ka: krakenAPI object.
        :return: None
        """
        response = ka.create_order(
            self.pair,
            self.type,
            self.order_type,
            self.pair_price,
            self.volume,
            self.o_flags,
        )
        self.txid = response.get("txid")[0]
        self.description = response.get("descr").get("order")

    def save_order_csv(self, orders_filepath: str) -> None:
        """
        Save Order object attributes to orders.csv.

        :return: None
        """
        sanitized_order = {
            key: self._sanitize_csv_value(value)
            for key, value in self.__dict__.items()
        }
        fieldnames = list(sanitized_order)
        try:
            existing_fieldnames = self._read_order_csv_header(
                orders_filepath,
            )
            if existing_fieldnames and existing_fieldnames != fieldnames:
                raise ValueError(
                    "existing order history has unexpected columns"
                )
            write_header = not existing_fieldnames
            mode = "a" if existing_fieldnames else "w"
            with open(orders_filepath, mode, newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                writer.writerow(sanitized_order)
        except (csv.Error, OSError) as e:
            raise ValueError(f"Can't save order history -> {e}")

    @staticmethod
    def set_order_volume(
        amount: float, pair_price: float, lot_decimals: float
    ) -> float:
        """
        Define order volume for specified DCA amount,
        pair price and pair decimals based on Kraken lot decimals.
        Volume is adjusted for 0.026% Kraken taker fees
        to be at the maximum cost of the amount specified
        in the configuration

        :param amount: DCA amount.
        :param pair_price: Pair price.
        :param lot_decimals: Lot decimals as float.
        :return: Fee adjusted order volume as flat.
        """
        try:
            quantize_unit = Decimal("1").scaleb(-lot_decimals)
            order_volume = (
                Order._to_decimal(amount) / Order._to_decimal(pair_price)
            ).quantize(quantize_unit, rounding=ROUND_DOWN)
            # Adjust amount to the 0.26% taker fee on Kraken
            order_volume_fee_adjusted = (
                order_volume / Decimal("1.0026")
            ).quantize(quantize_unit, rounding=ROUND_DOWN)
        except ZeroDivisionError:
            raise ZeroDivisionError(
                "Order set_order_volume -> pair_price must not be 0."
            )
        return float(order_volume_fee_adjusted)

    @staticmethod
    def estimate_order_price(
        volume: float, pair_price: float, quote_decimals: int
    ) -> float:
        """
        Get order price for specified order volume
        and pair price and 0.26% taker fees.
        Rounded to quote asset decimals.

        :param volume: Order volume.
        :param pair_price: Pair price.
        :param quote_decimals: Quote asset decimals as float.
        :return: Adjusted order price as float.
        """
        order_price = Order._to_decimal(volume) * Order._to_decimal(
            pair_price
        )
        return float(Order._quantize_quote_value(order_price, quote_decimals))

    @staticmethod
    def estimate_order_fee(
        volume: float, pair_price: float, quote_decimals: int
    ) -> float:
        """
        Return order fee based on the 0.026%
        fee from kraken on limit maker orders.
        Rounded to quote asset decimals.

        :param volume: Order volume.
        :param pair_price: Pair price.
        :param quote_decimals: Quote asset decimals as float.
        :return: Order fees as float.
        """
        order_price = Order._to_decimal(volume) * Order._to_decimal(
            pair_price
        )
        fees = order_price * Decimal("0.0026")
        return float(Order._quantize_quote_value(fees, quote_decimals))

    @staticmethod
    def _to_decimal(value: float) -> Decimal:
        """Convert numeric values through strings to avoid float artifacts."""
        return Decimal(str(value))

    @staticmethod
    def _quantize_quote_value(value: Decimal, quote_decimals: int) -> Decimal:
        """Quantize quote asset values to the required precision."""
        return value.quantize(Decimal("1").scaleb(-quote_decimals))

    @staticmethod
    def _sanitize_csv_value(value: object) -> object:
        """Prefix formula-like strings to avoid CSV injection."""
        if isinstance(value, str) and re.match(r"^\s*[=+\-@]", value):
            return f"'{value}"
        return value

    @staticmethod
    def _read_order_csv_header(orders_filepath: str) -> list[str]:
        try:
            with open(orders_filepath, newline="") as csv_file:
                return next(csv.reader(csv_file), [])
        except FileNotFoundError:
            return []
