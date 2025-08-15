# fmu-settings-api

[![ci](https://github.com/equinor/fmu-settings-api/actions/workflows/ci.yml/badge.svg)](https://github.com/equinor/fmu-settings-api/actions/workflows/ci.yml)

**fmu-settings-api** is the FastAPI backend for the fmu-settings application.

## Usage

This application is primarily invoked by
[fmu-settings-cli](https://github.com/equinor/fmu-settings-cli) and is meant
to be used together with
[fmu-settings-gui](https://github.com/equinor/fmu-settings-gui). It depends
mostly on [fmu-settings](https://github.com/equinor/fmu-settings) to work with
`.fmu/` configuration directories within the FMU context.

With `fmu-settings-cli` installed, to run the API by itself just

```sh
fmu-settings api
```

An authorization token is required to create a session. When developing you
can print this token to the the terminal with

```sh
fmu-settings api --print-token
```

It's useful to be able to reload while developing.

```sh
fmu-settings api --print-token --reload
```

## API Documentation

The routes have documentation on them. To view them, and work with the API go
to `localhost:8001/docs` (or whatever your port may end up being).

## Configuration

Configuration should largely be handled by the GUI when they are being run
together. When developing you will want to be able to access different
endpoints. You can configure some of these values with `.env` and scripts in
the [scripts/](scripts/) directory.

A [sample.env](sample.env) is included here. To get your own SMDA subscription
key you may go to the internal Equinor API self-service website. Copy
`sample.env` to `.env` and fill in the correct values.

## Access token

Accessing services through this API requires a valid access token. You can
acquire one with the [scripts/get_token.py](scripts/get_token.py) script. This
script will open a small server, authenticate you with SSO, and store your
access token to `.token`. You may then use this as you need.

## Developing

Clone and install into a virtual environment.

```sh
git clone git@github.com:equinor/fmu-settings-api.git
cd fmu-settings-api
# Create or source virtual/Komodo env
pip install -U pip
pip install -e ".[dev]"
# Make a feature branch for your changes
git checkout -b some-feature-branch
```

Run the tests with

```sh
pytest -n auto tests
```

Ensure your changes will pass the various linters before making a pull
request. It is expected that all code will be typed and validated with
mypy.

```sh
ruff check
ruff format --check
mypy src tests
```

See the [contributing document](CONTRIBUTING.md) for more.
