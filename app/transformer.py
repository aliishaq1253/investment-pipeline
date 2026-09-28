"""
Transformer-Modul: Bereinigt Rohdaten und berechnet Kennzahlen.

Teil der ETL-Pipeline (Transform-Schritt).
"""

import numpy as np
import pandas as pd

PRICE_COLUMNS = ["open", "high", "low", "close"]


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bereinigt die Rohdaten und berechnet zusätzliche Kennzahlen pro Symbol.

    Schritte:
        1. Zeitzone aus dem date-Feld entfernen
        2. Sanity Checks: fehlende Werte, negative Kurse, Duplikate entfernen
        3. Kennzahlen berechnen: daily_return, ma_30, volatility_30

    Args:
        df: Rohdaten wie sie extractor.extract() liefert
            (Spalten: date, symbol, open, high, low, close, volume)

    Returns:
        Bereinigter DataFrame inkl. neuer Kennzahlen-Spalten.
    """
    print(f"Starte Transformation: {len(df)} Datensaetze vor Bereinigung.")

    df = df.copy()

    # 1) Zeitzone entfernen, damit Datumswerte vergleichbar/speicherbar sind
    #    (z.B. SQLite kann mit tz-aware Timestamps nicht sauber umgehen).
    #    utc=True ist noetig, weil US-Symbole (America/New_York) und
    #    z.B. deutsche Symbole (Europe/Berlin) unterschiedliche Zeitzonen
    #    haben - nach dem Zusammenfuehren mehrerer Symbole via pd.concat()
    #    landet die date-Spalte dann als object-Spalte mit gemischten
    #    Zeitzonen, was pd.to_datetime() ohne utc=True nicht auflösen kann.
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)

    # 2) Sanity Checks
    df = _remove_missing_values(df)
    df = _remove_negative_prices(df)
    df = _remove_duplicates(df)

    # Für stabile Rolling-Berechnungen (ma_30, volatility_30) muss die
    # Reihenfolge pro Symbol chronologisch sein.
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    # 3) Kennzahlen berechnen, jeweils gruppiert nach Symbol
    df = _add_daily_return(df)
    df = _add_moving_average(df)
    df = _add_volatility(df)

    print(f"Transformation abgeschlossen: {len(df)} Datensaetze nach Bereinigung.")
    return df


def _remove_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Prüft auf fehlende Werte in den relevanten Spalten und entfernt betroffene Zeilen."""
    relevant_columns = ["date", "symbol"] + PRICE_COLUMNS + ["volume"]
    missing_mask = df[relevant_columns].isna().any(axis=1)
    missing_count = int(missing_mask.sum())

    if missing_count > 0:
        print(f"  Sanity Check - Fehlende Werte: {missing_count} Zeile(n) werden entfernt.")
        df = df[~missing_mask]
    else:
        print("  Sanity Check - Fehlende Werte: keine gefunden.")

    return df


def _remove_negative_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Prüft auf negative bzw. null Kurswerte und entfernt betroffene Zeilen."""
    negative_mask = (df[PRICE_COLUMNS] <= 0).any(axis=1)
    negative_count = int(negative_mask.sum())

    if negative_count > 0:
        print(f"  Sanity Check - Negative/Null-Kurse: {negative_count} Zeile(n) werden entfernt.")
        df = df[~negative_mask]
    else:
        print("  Sanity Check - Negative/Null-Kurse: keine gefunden.")

    return df


def _remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Prüft auf doppelte (date, symbol)-Kombinationen und entfernt sie."""
    duplicate_mask = df.duplicated(subset=["date", "symbol"])
    duplicate_count = int(duplicate_mask.sum())

    if duplicate_count > 0:
        print(f"  Sanity Check - Duplikate: {duplicate_count} Zeile(n) werden entfernt.")
        df = df[~duplicate_mask]
    else:
        print("  Sanity Check - Duplikate: keine gefunden.")

    return df


def _add_daily_return(df: pd.DataFrame) -> pd.DataFrame:
    """Tägliche prozentuale Kursveränderung des Schlusskurses, pro Symbol berechnet."""
    df["daily_return"] = df.groupby("symbol")["close"].pct_change()
    return df


def _add_moving_average(df: pd.DataFrame) -> pd.DataFrame:
    """30-Tage gleitender Durchschnitt des Schlusskurses, pro Symbol berechnet."""
    df["ma_30"] = (
        df.groupby("symbol")["close"]
        .transform(lambda close: close.rolling(window=30, min_periods=1).mean())
    )
    return df


def _add_volatility(df: pd.DataFrame) -> pd.DataFrame:
    """30-Tage rollende Standardabweichung der täglichen Rendite, pro Symbol berechnet."""
    df["volatility_30"] = (
        df.groupby("symbol")["daily_return"]
        .transform(lambda ret: ret.rolling(window=30, min_periods=1).std())
    )
    return df


if __name__ == "__main__":
    # Kleiner manueller Test mit Beispieldaten (ohne echten API-Call)
    sample_dates = pd.date_range("2026-01-01", periods=10, freq="D", tz="America/New_York")

    sample_df = pd.DataFrame({
        "date": list(sample_dates) * 2,
        "symbol": ["AAPL"] * 10 + ["MSFT"] * 10,
        "open": np.linspace(100, 109, 10).tolist() + np.linspace(200, 209, 10).tolist(),
        "high": np.linspace(101, 110, 10).tolist() + np.linspace(201, 210, 10).tolist(),
        "low": np.linspace(99, 108, 10).tolist() + np.linspace(199, 208, 10).tolist(),
        "close": np.linspace(100, 110, 10).tolist() + np.linspace(200, 210, 10).tolist(),
        "volume": [1_000_000] * 20,
    })

    # Absichtlich ein paar "kaputte" Zeilen einbauen, um die Sanity Checks zu testen
    sample_df.loc[2, "close"] = np.nan          # fehlender Wert
    sample_df.loc[5, "open"] = -50              # negativer Kurs
    sample_df = pd.concat([sample_df, sample_df.iloc[[0]]], ignore_index=True)  # Duplikat

    result = transform(sample_df)
    print(result.head(10))
    print(result.dtypes)
