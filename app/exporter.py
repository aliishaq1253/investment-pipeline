"""
Exporter-Modul: Schreibt Kursdaten und Zusammenfassung als Excel-Report.

Kein klassischer ETL-Schritt, sondern der "Report"-Teil der Pipeline,
der die Ergebnisse in ein von Menschen lesbares Format bringt.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "exports"

# Grenzwert, damit sehr lange Inhalte (z.B. viele Nachkommastellen) die
# Spalten nicht ins Unermessliche wachsen lassen
MAX_COLUMN_WIDTH = 40


def export_excel(df: pd.DataFrame, stats_df: pd.DataFrame) -> str:
    """
    Exportiert Kursdaten und Zusammenfassung als Excel-Datei mit zwei Sheets.

    Args:
        df: bereinigte Kursdaten (Ergebnis von transformer.transform())
        stats_df: Zusammenfassung pro Symbol (Ergebnis von database.fetch_stats())

    Returns:
        Pfad zur erzeugten Excel-Datei als String.
    """
    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        # Zeitstempel im Dateinamen, damit alte Reports nicht ueberschrieben werden
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = EXPORT_DIR / f"investment_report_{timestamp}.xlsx"

        print(f"Erstelle Excel-Report: {file_path.name}")

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Kursdaten", index=False)
            stats_df.to_excel(writer, sheet_name="Zusammenfassung", index=False)

            _auto_fit_columns(writer.sheets["Kursdaten"], df)
            _auto_fit_columns(writer.sheets["Zusammenfassung"], stats_df)

        print(f"Report gespeichert unter: {file_path}")
        return str(file_path)

    except Exception as error:
        print(f"Fehler beim Excel-Export: {error}")
        raise


def _auto_fit_columns(worksheet, df: pd.DataFrame) -> None:
    """Passt die Spaltenbreiten eines Worksheets an den Inhalt an."""
    for i, column in enumerate(df.columns, start=1):
        # Laengste Zelle in der Spalte finden (inkl. Header), plus etwas Puffer
        max_content_length = df[column].map(lambda value: len(str(value))).max() if not df.empty else 0
        column_width = max(len(str(column)), int(max_content_length)) + 2
        column_width = min(column_width, MAX_COLUMN_WIDTH)

        column_letter = worksheet.cell(row=1, column=i).column_letter
        worksheet.column_dimensions[column_letter].width = column_width


if __name__ == "__main__":
    # Kleiner manueller Test mit Beispieldaten (ohne echten API-Call / DB-Zugriff)
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

    sample_stats_df = pd.DataFrame({
        "symbol": ["AAPL", "MSFT"],
        "current_price": [103.0, 205.0],
        "total_return_pct": [2.49, 2.24],
        "avg_volatility": [0.001, 0.002],
    })

    exported_path = export_excel(sample_df, sample_stats_df)
    print(f"\nTest abgeschlossen. Datei liegt hier: {exported_path}")
