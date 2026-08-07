# 🐙 Kraken-DCA
![Docker Pulls](https://img.shields.io/docker/pulls/futurbroke/kraken-dca)
![main-unit-testing workflow](https://github.com/adocquin/kraken-dca/actions/workflows/main-unit-testing.yaml/badge.svg)
[![Coverage Status](https://coveralls.io/repos/github/adocquin/kraken-dca/badge.svg)](https://coveralls.io/github/adocquin/kraken-dca)
![Python Version](https://img.shields.io/badge/python-3.12-blue)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
![GitHub](https://img.shields.io/github/license/adocquin/kraken-dca)

**Automate Dollar Cost Averaging on Kraken exchange**

## Table of Contents
1. ➤ [About the project](#-about-the-project)
2. ➤ [Orders](#-orders)
    - [What are the order settings ?](#what-are-the-order-settings-?)
    - [How are price, volume and fee computed ?](#how-are-price,-volume-and-fee-computed-?)
    - [How is order history saved ?](#how-is-order-history-saved-?)
3. ➤ [Configuration](#-configuration)
4. ➤ [Run with Docker](#-run-with-docker)
5. ➤ [Run without Docker](#-run-without-docker)
      - [Launch Kraken-DCA](#launch-kraken-dca)
      - [Automate DCA through cron](#automate-dca-through-cron)
6. ➤ [License](#-license)
7. ➤ [How to contribute](#-how-to-contribute)

# 🔍 About the project

Kraken-DCA is a python program to automate pairs
[Dollar Cost Averaging](https://www.investopedia.com/terms/d/dollarcostaveraging.asp)
on as many pairs as you want on [Kraken](https://kraken.com) exchange.<br>
At every launch, if no DCA pair order was already passed for each pair and delay in 
configuration file, it will create a buy limit order at current pair ask price for the specified amount.

Order history is saved in CSV format.

The program will need a Kraken public and private API key with permissions to:
- Consult funds
- View open orders & transactions
- View closed orders & transactions
- Create and modify orders

API keys can be created from the [API page](https://www.kraken.com/u/security/api) of your Kraken account.

# 📒 Orders
The pair and the amount to buy need to be specified in the configuration file.

## What are the order settings ?
A buy limit taker order is created by the program at its execution, 0.26% fee are assumed.<br>
Orders are created only if no one were created during the current day for the specified pair and are immediately 
executed.<br>
Pair quote asset are used to pay Kraken fee.

## How are price, volume and fee computed ?
**Limit price**: The pair ask price at the moment of the program execution.

**Volume**: The order volume is the amount*price truncated down to the pair lot decimals, then adjusted to volume/1.0026
truncated down the pair lot decimals.<br>
By adjusting the volume, the total price of the order with fee included doesn't exceed the configuration amount.<br>

**Order price**: The order price is estimated as volume*pair_ask_price rounded to the quote asset decimals.

**Fee**: Fee are included in the specified amount by adjusting down the order volume.
0.26% taker fee are assumed and are estimated as the order_price*0.0026 round to the quote asset decimals.

Kraken documentation:
- [Kraken API documentation](https://www.kraken.com/en-us/features/api)
- [Are internal calculations made in float point or with a fixed number of decimals? Are the values always rounded?](https://support.kraken.com/hc/en-us/articles/201988998-Are-internal-calculations-made-in-float-point-or-with-a-fixed-number-of-decimals-Are-the-values-always-rounded-)
- [Assets info](https://api.kraken.com/0/public/Assets)
- [Tradable asset paird](https://api.kraken.com/0/public/AssetPairs)

## How is order history saved ?

Order history is saved in CSV format with following information per order:
- **date**: Order date.
- **pair**: Order pair, the configured DCA pair.
- **type**: Buy or sell order, *buy* in this case.
- **order_type**: Order type, *limit* in this case.
- **o_flags**: Order additional flag, *fciq* in this case to pay fee in pair quote asset.
- **pair_price**: Limit order pair price. Pair ask price at the moment of the DCA.
- **volume**: Order volume.
- **price**: Order price in pair quote asset.
- **fee**: Order fee in pair quote asset.
- **total_price**: price + fee
- **txid**: TXID of the order.
- **description**: Description of the order from Kraken.

Order history is by default saved in *orders.csv* in Kraken-DCA base directory, 
the output file can be changed through docker image execution as described below.

# 🔨 Configuration
Configuration is done through a yaml file. In Docker web UI mode the container can
start without an existing `config.yaml`; the web UI enters setup mode and lets you
create one. For local or legacy CLI usage, copy *config-sample.yaml* to
*config.yaml* and adjust it to your requirements.

```yaml
# Kraken's API public and private keys.
# You can omit this section when KRAKEN_API_PUBLIC_KEY and
# KRAKEN_API_PRIVATE_KEY are supplied through the environment.
api:
  public_key: "KRAKEN_API_PUBLIC_KEY"
  private_key: "KRAKEN_API_PRIVATE_KEY"

# DCA pairs configuration. You can add as many pairs as you want.
# pair: Name of the pair (list of available pairs: https://api.kraken.com/0/public/AssetPairs)
# amount: Amount of the order in quote asset.
# schedule.enabled: Enables or disables web scheduler execution for this pair.
# schedule.cron: Five-field Unix cron expression.
# schedule.timezone: IANA timezone used to evaluate the cron expression.
# min_order_interval_minutes: Safety interval for cron/manual runs.
# delay: Legacy CLI/cron fallback in days. Web cron schedules take precedence.
dca_pairs:
  - pair: "XETHZEUR"
    amount: 15
    schedule:
      enabled: true
      cron: "0 9 * * *"
      timezone: "Europe/Prague"
    min_order_interval_minutes: 30
    limit_factor: 0.985
    max_price: 2900.10
  - pair: "XXBTZEUR"
    amount: 20
    schedule:
      enabled: false
    delay: 3
    ignore_differing_orders: True
  - pair: "XLTCZEUR"
    delay: 7
    amount: 10
```
- In api, public_key and private_key correspond to your Kraken API key information.
- In web mode, use the searchable pair field to select a Kraken asset pair. The UI stores Kraken's canonical pair key such as `XXBTZEUR` while showing friendly values such as `XBT/EUR` and `XBTEUR`.
- When editing YAML manually, prefer Kraken's canonical `AssetPairs` key for `pair` values, for example `XXBTZEUR` for Bitcoin/EUR. The runner also accepts common Kraken aliases such as `XBTEUR`, `XBT/EUR`, and `BTC/EUR`.
- Amount is the amount of quote asset to sell to buy base asset.
- `schedule:` configures the Docker web scheduler for a pair. `schedule.cron` must be a five-field Unix cron expression and `schedule.timezone` should be an IANA timezone such as `Europe/Prague` or `UTC`.
- `min_order_interval_minutes` prevents cron/manual runs from submitting too frequently for the same pair. The default is 30 minutes.
- Use `schedule.enabled: false` to keep a pair in the config without scheduling it.
- The legacy `delay` value is still supported for the old CLI/cron mode and acts as a fallback when no enabled web schedule is present.
- Set a `limit_factor` if you want to place the buy order that is different from the
  current market price (up to 5 digits).<br>
  E.g., `limit_factor: 0.95` would set the limit price 5% below the market price.
- Set a `max_price` if you want to define a maximum price in quote pair to create a
  limit buy order (after using `limit_factor` if defined).
- Set `ignore_differing_orders` to `True` to ignore orders within the time delay that
  differ more than 1% in the desired amount. This allows to have manually set limit
  orders while still DCAing.

More information on 
[Kraken API official documentation](https://support.kraken.com/hc/en-us/articles/360000920306-Ticker-pairs).

# 🐳 Run with Docker
You can download the image directly from [Docker Hub](https://hub.docker.com/) using:
```sh
docker pull futurbroke/kraken-dca:latest
```
The default Docker runtime runs the web UI and scheduler in one container on port
8080. The container runs as an unprivileged user (`uid 10001`, `gid 10001`) and
requires `WEB_UI_PASSWORD` for browser login.

Create writable files on the host if you want persistent config and order history:
```sh
touch config.yaml
touch orders.csv
chown 10001:10001 config.yaml
chown 10001:10001 orders.csv
```
To start the Docker web UI use:
```sh
docker run -p 8080:8080 \
  -v CONFIGURATION_FILE_PATH:/app/config.yaml \
  -v ORDERS_FILE_PATH:/app/orders.csv \
  -e WEB_UI_PASSWORD=change-me \
  -e TZ=UTC \
  --name kraken-dca \
  --restart=on-failure \
  futurbroke/kraken-dca
```
- **CONFIGURATION_FILE_PATH**: writable `config.yaml` filepath (e.g., *~/dev/config.yaml*). Web UI mode writes this file, so do not mount it read-only.
- **ORDERS_FILE_PATH**: writable `orders.csv` order history filepath (e.g., *~/dev/orders.csv*).
- **WEB_UI_PASSWORD**: Required password for the browser UI.
- **WEB_UI_SESSION_SECRET**: Optional signing secret for sessions. If omitted, `WEB_UI_PASSWORD` is used.
- **WEB_UI_COOKIE_SECURE**: Optional. Set to `true` when serving the UI through HTTPS.
- **TZ**: Recommended timezone for deterministic cron scheduling and logs.

Prefer supplying Kraken credentials through a mounted `config.yaml` that is generated from your secret store or environment outside the repository, rather than committing secrets into version control.

Manual run actions execute one configured pair immediately through the same safety
checks as scheduled jobs. A save through the web UI writes the full config and
triggers a scheduler reload; if the reload fails, the UI reports the error and the
old active scheduler state is kept.

For legacy CLI/cron mode only, you can mount `config.yaml` read-only and run your
own external cron. That read-only guidance does not apply to Docker web UI mode,
because the web UI must be able to persist configuration changes.

To see container logs:
```sh
docker logs kraken-dca
```
To stop and delete the container:
```sh
docker kill kraken-dca
docker rm kraken-dca
```

# 🐍 Run without Docker
You must specify your configuration in a *config.yaml* file in the *Kraken-DCA* root folder.
## Launch Kraken-DCA
Kraken-DCA is tested with Python 3.12. A simple local setup is:
```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
For local development and test runs, install the additional pinned test
dependencies:
```sh
python -m pip install -r requirements-dev.txt
```
You can then launch the program from the folder where you downloaded the repository folder using:
```sh
python kraken-dca
```
Or inside Kraken-DCA base directory using:
```sh
python __main__.py
```
## Automate DCA through cron
You can automate the execution by using cron on unix systems.
To execute the program every hour (it will only buy if no DCA pair order was done the current day) run in a shell:
```sh
crontab -e
```
And add:
```
0 * * * * cd PROGRAM_ROOT_FOLDER && $(which python3) kraken-dca >> OUTPUT_FILE 2>&1
```
- **PROGRAM_ROOT_FOLDER**: Folder where you downloaded the repository (e.g., *~/dev*).<br>
- **OUTPUT_FILE**: Program outputs log file (e.g., *~/cron.log*).<br>

Program outputs will be available in your output file, order history in *orders.csv* in Kraken-DCA base directory.

To deactivate the cron job remove the line using again:
```sh
crontab -e
```

More crontab execution frequency options: https://crontab.guru/

# 📔 License
Kraken-DCA  is distributed under the terms of the GNU General Public License v3.0. A
complete version of the license is available in the 
[LICENSE.md](https://github.com/FuturBroke/kraken-dca/blob/main/README.md) in
this repository. Any contribution made to this project will be licensed under
the GNU General Public License v3.0.

# 🙋‍♀️ How to contribute
Thanks for your interest in contributing to the project. You can contribute freely by 
creating an issue, fork or create a pull request. Before issuing a pull request, make 
sure the changes did not break any existing functionality and are fully covered with
unit tests by running this command in the base directory:
```sh
python -m pip install -r requirements-dev.txt
pytest -vv --cov
```
