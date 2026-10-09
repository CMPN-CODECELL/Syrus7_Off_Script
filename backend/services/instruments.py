"""Canonical instrument allowlist shared by every order entry path."""

INSTRUMENTS = {
    "RELIANCE.NS": "Reliance Industries Ltd",
    "INFY.NS": "Infosys Ltd",
    "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank Ltd",
    "WIPRO.NS": "Wipro Ltd",
    "SBIN.NS": "State Bank of India",
}


def canonical_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if symbol not in INSTRUMENTS:
        raise ValueError(f"Unsupported instrument: {symbol or '(empty)'}. Choose a symbol from the supported NSE instrument list.")
    return symbol
