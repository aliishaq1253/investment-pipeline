"""
Extractor-Modul: Lädt historische Aktienkursdaten von Yahoo Finance (yfinance).

Teil der ETL-Pipeline (Extract-Schritt).
"""

import pandas as pd
import yfinance as yf

# Spalten, wie sie yfinance liefert -> unsere einheitlichen Spaltennamen
COLUMN_MAPPING = {
    "Date": "date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


def extract(symbols: list, period: str) -> pd.DataFrame:
    """
    Lädt historische Kursdaten für eine Liste von Aktien-Symbolen.

    Args:
        symbols: Liste von Ticker-Symbolen, z.B. ["AAPL", "MSFT", "SAP.DE"]
        period: Zeitraum für den Daten geladen werden, z.B. "1y", "6mo", "5d"

    Returns:
        DataFrame mit den Spalten: date, symbol, open, high, low, close, volume
    """
    print(f"Starte Extraktion fuer {len(symbols)} Symbol(e): {symbols} (Zeitraum: {period})")

    all_data = []

    for symbol in symbols:
        try:
            print(f"  -> Lade Daten fuer {symbol} ...")

            ticker = yf.Ticker(symbol)
            history = ticker.history(period=period)

            if history.empty:
                print(f"  Warnung: Keine Daten fuer {symbol} gefunden.")
                continue

            # Index (Datum) als eigene Spalte herausloesen
            history = history.reset_index()

            # Nur die Spalten behalten, die wir brauchen, und umbenennen
            history = history.rename(columns=COLUMN_MAPPING)
            history = history[["date", "open", "high", "low", "close", "volume"]]

            # Symbol-Spalte hinzufuegen, damit man beim Zusammenfuehren
            # mehrerer Aktien noch weiss, welche Zeile zu welcher Aktie gehoert
            history["symbol"] = symbol

            all_data.append(history)
            print(f"  {len(history)} Datensaetze fuer {symbol} geladen.")

        except Exception as error:
            print(f"  Fehler beim Laden von {symbol}: {error}")
            continue

    if not all_data:
        print("Keine Daten geladen. Gebe leeren DataFrame zurueck.")
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])

    # Alle einzelnen DataFrames zu einem zusammenfassen
    result = pd.concat(all_data, ignore_index=True)
    result = result[["date", "symbol", "open", "high", "low", "close", "volume"]]

    print(f"Extraktion abgeschlossen: {len(result)} Datensaetze insgesamt.")
    return result


if __name__ == "__main__":
    # Kleiner manueller Test
    test_symbols = ["AAPL", "MSFT", "SAP.DE", "SIE.DE"]
    df = extract(test_symbols, period="1mo")
    print(df.head())
    print(df.dtypes)
