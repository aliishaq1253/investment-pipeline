"""
Database-Modul: Speichert und liest Investment-Daten in/aus SQLite.

Teil der ETL-Pipeline (Load-Schritt).
"""

import sqlite3
from pathlib import Path

import pandas as pd

# Pfad relativ zum Projekt-Root bestimmen (unabhaengig vom aktuellen Arbeitsverzeichnis),
# damit es egal ist, von wo aus das Skript gestartet wird.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "investments.db"

TABLE_NAME = "investments"


def get_connection() -> sqlite3.Connection:
    """Öffnet eine SQLite-Verbindung zur Investment-Datenbank und gibt sie zurück."""
    # Sicherstellen, dass der data/-Ordner existiert, bevor SQLite die Datei anlegt
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Erstellt die Tabelle 'investments', falls sie noch nicht existiert."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            daily_return REAL,
            ma_30 REAL,
            volatility_30 REAL,
            PRIMARY KEY (date, symbol)
        )
    """)
    conn.commit()
    print(f"Tabelle '{TABLE_NAME}' ist bereit.")


def load(df: pd.DataFrame, conn: sqlite3.Connection) -> None:
    """
    Speichert den DataFrame in der Datenbank.

    if_exists='replace' loescht die bestehende Tabelle und schreibt die
    komplett neuen Daten - passend fuer eine Pipeline, die bei jedem Lauf
    einen frischen, vollstaendigen Datenstand erzeugt.
    """
    try:
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
        print(f"{len(df)} Datensaetze in '{TABLE_NAME}' gespeichert.")
    except Exception as error:
        print(f"Fehler beim Speichern in die Datenbank: {error}")
        raise


def fetch_all(conn: sqlite3.Connection) -> pd.DataFrame:
    """Liest alle Daten aus der Tabelle 'investments'."""
    query = f"SELECT * FROM {TABLE_NAME} ORDER BY symbol, date"
    df = pd.read_sql(query, conn, parse_dates=["date"])
    return df


def fetch_by_symbol(conn: sqlite3.Connection, symbol: str) -> pd.DataFrame:
    """Liest alle Daten fuer ein bestimmtes Symbol."""
    query = f"SELECT * FROM {TABLE_NAME} WHERE symbol = ? ORDER BY date"
    # Parametrisierte Query (? statt String-Formatierung), um SQL-Injection zu vermeiden
    df = pd.read_sql(query, conn, params=(symbol,), parse_dates=["date"])
    return df


def fetch_stats(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Berechnet pro Symbol eine kurze Zusammenfassung:
        - current_price: letzter bekannter Schlusskurs
        - total_return_pct: Gesamtrendite ueber den geladenen Zeitraum in %
        - avg_volatility: durchschnittliche 30-Tage-Volatilitaet
    """
    df = fetch_all(conn)

    if df.empty:
        print("Keine Daten in der Datenbank fuer fetch_stats().")
        return pd.DataFrame(columns=["symbol", "current_price", "total_return_pct", "avg_volatility"])

    def summarize(group: pd.DataFrame) -> pd.Series:
        first_close = group["close"].iloc[0]
        last_close = group["close"].iloc[-1]
        total_return_pct = (last_close / first_close - 1) * 100

        return pd.Series({
            "current_price": last_close,
            "total_return_pct": total_return_pct,
            "avg_volatility": group["volatility_30"].mean(),
        })

    # Sortierung ist wichtig, damit "erster" und "letzter" Kurs zeitlich stimmen
    df = df.sort_values(["symbol", "date"])
    stats = df.groupby("symbol").apply(summarize, include_groups=False).reset_index()

    return stats


if __name__ == "__main__":
    # Kleiner manueller Test mit Beispieldaten (ohne echten API-Call)
    sample_df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"]),
        "symbol": ["AAPL", "AAPL", "MSFT", "MSFT"],
        "open": [100.0, 101.0, 200.0, 202.0],
        "high": [101.0, 102.0, 201.0, 203.0],
        "low": [99.0, 100.0, 199.0, 201.0],
        "close": [100.5, 103.0, 200.5, 205.0],
        "volume": [1_000_000, 1_100_000, 900_000, 950_000],
        "daily_return": [None, 0.0249, None, 0.0224],
        "ma_30": [100.5, 101.75, 200.5, 202.75],
        "volatility_30": [None, 0.001, None, 0.002],
    })

    connection = get_connection()
    init_db(connection)
    load(sample_df, connection)

    print("\n--- fetch_all ---")
    print(fetch_all(connection))

    print("\n--- fetch_by_symbol('AAPL') ---")
    print(fetch_by_symbol(connection, "AAPL"))

    print("\n--- fetch_stats ---")
    print(fetch_stats(connection))

    connection.close()
