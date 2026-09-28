"""
Dashboard-Modul: Streamlit-Oberflaeche fuer die Investment Report Pipeline.

Liest die bereits geladenen Daten aus SQLite, visualisiert sie interaktiv
und kann die ETL-Pipeline (extractor -> transformer -> database) per
Knopfdruck neu ausführen.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import database
import exporter
import extractor
import transformer

# Symbole, die vorgeschlagen werden, solange die Datenbank noch leer ist
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "SAP.DE", "SIE.DE"]

# Zeitraeume, die yfinance beim Datenabruf akzeptiert
FETCH_PERIODS = ["1mo", "3mo", "6mo", "1y", "2y", "5y"]

# Feste, in fixer Reihenfolge zugewiesene Farben pro Symbol (colorblind-safe
# Kategorial-Palette). Wichtig: die Zuordnung Symbol -> Farbe wird aus ALLEN
# in der Datenbank vorhandenen Symbolen gebildet, nicht aus der aktuellen
# Auswahl - so behaelt z.B. "AAPL" immer dieselbe Farbe, egal was sonst
# gerade ausgewaehlt ist.
CATEGORICAL_PALETTE = [
    "#2a78d6",  # blau
    "#eb6834",  # orange
    "#1baf7a",  # tuerkis
    "#eda100",  # gelb
    "#e87ba4",  # magenta
    "#008300",  # gruen
    "#4a3aa7",  # violett
    "#e34948",  # rot
]


def build_color_map(symbols: list) -> dict:
    """Weist jedem Symbol in fester alphabetischer Reihenfolge eine feste Farbe zu."""
    sorted_symbols = sorted(symbols)
    return {
        symbol: CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)]
        for i, symbol in enumerate(sorted_symbols)
    }


def run_pipeline(symbols: list, period: str, conn) -> None:
    """Fuehrt Extract -> Transform -> Load fuer die gegebenen Symbole aus."""
    raw_df = extractor.extract(symbols, period)
    clean_df = transformer.transform(raw_df)
    database.load(clean_df, conn)


def normalize_symbols(symbols: list) -> list:
    """Bereinigt eine Symbol-Liste: trimmen, Grossschreibung, Duplikate entfernen."""
    cleaned = [str(symbol).strip().upper() for symbol in symbols]
    cleaned = [symbol for symbol in cleaned if symbol]

    # Duplikate entfernen, dabei Reihenfolge beibehalten
    seen = set()
    unique_symbols = []
    for symbol in cleaned:
        if symbol not in seen:
            seen.add(symbol)
            unique_symbols.append(symbol)

    return unique_symbols


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Berechnet pro Symbol current_price / total_return_pct / avg_volatility.

    Spiegelt die Logik von database.fetch_stats(), rechnet aber auf dem
    aktuell im Dashboard gefilterten Ausschnitt (Symbole + Zeitraum), damit
    die KPI-Karten immer zu den angezeigten Charts passen.
    """
    def summarize(group: pd.DataFrame) -> pd.Series:
        first_close = group["close"].iloc[0]
        last_close = group["close"].iloc[-1]
        return pd.Series({
            "current_price": last_close,
            "total_return_pct": (last_close / first_close - 1) * 100,
            "avg_volatility": group["volatility_30"].mean(),
        })

    df_sorted = df.sort_values(["symbol", "date"])
    return df_sorted.groupby("symbol").apply(summarize, include_groups=False).reset_index()


def render_kpi_cards(stats_df: pd.DataFrame) -> None:
    """Zeigt pro Symbol eine KPI-Karte mit aktuellem Kurs, Rendite und Volatilität."""
    symbols = stats_df["symbol"].tolist()

    # In Vierer-Reihen anordnen, damit es bei vielen Symbolen nicht ueberlaeuft
    row_size = 4
    for i in range(0, len(symbols), row_size):
        row_symbols = symbols[i:i + row_size]
        columns = st.columns(len(row_symbols))

        for col, symbol in zip(columns, row_symbols):
            row = stats_df[stats_df["symbol"] == symbol].iloc[0]
            col.metric(
                label=symbol,
                value=f"{row['current_price']:.2f}",
                delta=f"{row['total_return_pct']:+.2f}%",
            )
            volatility_text = (
                f"Ø Volatilität (30T): {row['avg_volatility']:.4f}"
                if pd.notna(row["avg_volatility"])
                else "Ø Volatilität (30T): n/a"
            )
            col.caption(volatility_text)


def render_price_chart(df: pd.DataFrame, color_map: dict) -> None:
    """Kursverlauf: Schlusskurs (durchgezogen) + MA_30 (gestrichelt), ein Symbol pro Farbe."""
    fig = go.Figure()

    for symbol, group in df.sort_values("date").groupby("symbol"):
        color = color_map[symbol]

        fig.add_trace(go.Scatter(
            x=group["date"], y=group["close"],
            mode="lines", name=symbol,
            line=dict(color=color, width=2),
            legendgroup=symbol,
        ))
        fig.add_trace(go.Scatter(
            x=group["date"], y=group["ma_30"],
            mode="lines", name=f"{symbol} (MA 30)",
            line=dict(color=color, width=2, dash="dash"),
            legendgroup=symbol,
            showlegend=False,  # Farbe identifiziert das Symbol bereits ueber die Close-Linie
        ))

    fig.update_layout(
        title="Kursverlauf: Schlusskurs & 30-Tage Moving Average",
        xaxis_title="Datum",
        yaxis_title="Preis",
        legend_title="Symbol",
        hovermode="x unified",
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption("Durchgezogene Linie: Schlusskurs · gestrichelte Linie: 30-Tage Moving Average (MA 30)")


def render_return_chart(df: pd.DataFrame, color_map: dict) -> None:
    """Tägliche prozentuale Rendite als Balkendiagramm, ein Symbol pro Farbe."""
    fig = go.Figure()

    for symbol, group in df.sort_values("date").groupby("symbol"):
        fig.add_trace(go.Bar(
            x=group["date"], y=group["daily_return"] * 100,
            name=symbol,
            marker_color=color_map[symbol],
        ))

    fig.update_layout(
        title="Tägliche Rendite",
        xaxis_title="Datum",
        yaxis_title="Tägliche Rendite (%)",
        barmode="group",
        legend_title="Symbol",
        hovermode="x unified",
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="Investment Report Pipeline", layout="wide")

    conn = database.get_connection()
    try:
        database.init_db(conn)
        df_all = database.fetch_all(conn)

        available_symbols = sorted(df_all["symbol"].unique()) if not df_all.empty else DEFAULT_SYMBOLS
        color_map = build_color_map(available_symbols)

        # --- Sidebar ---------------------------------------------------
        st.sidebar.header("Einstellungen")

        selected_symbols = st.sidebar.multiselect(
            "Aktien-Symbole",
            options=available_symbols,
            default=available_symbols,
            accept_new_options=True,
            help="Steuert sowohl die Ansicht als auch den Datenabruf. Neues Symbol "
                 "(z.B. NVDA) direkt eintippen und mit Enter hinzufuegen.",
        )
        selected_symbols = normalize_symbols(selected_symbols)

        date_range = None
        if not df_all.empty:
            min_date = df_all["date"].min().date()
            max_date = df_all["date"].max().date()
            date_range = st.sidebar.date_input(
                "Zeitraum (Ansicht)",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )

        st.sidebar.markdown("---")
        st.sidebar.subheader("Pipeline neu ausführen")

        fetch_period = st.sidebar.selectbox(
            "Zeitraum für Datenabruf (Yahoo Finance)",
            options=FETCH_PERIODS,
            index=FETCH_PERIODS.index("1y"),
        )

        if st.sidebar.button("Daten aktualisieren"):
            symbols_to_fetch = selected_symbols if selected_symbols else DEFAULT_SYMBOLS

            with st.spinner("Führe ETL-Pipeline aus (Extract -> Transform -> Load) ..."):
                run_pipeline(symbols_to_fetch, fetch_period, conn)
            st.sidebar.success("Pipeline erfolgreich ausgeführt!")
            st.rerun()

        # --- Hauptbereich ------------------------------------------------
        st.title("Investment Report Pipeline")

        if df_all.empty:
            st.info(
                "Es sind noch keine Daten in der Datenbank vorhanden. "
                "Bitte zuerst links in der Sidebar auf 'Daten aktualisieren' klicken, "
                "um die ETL-Pipeline auszuführen."
            )
            return

        filtered_df = df_all[df_all["symbol"].isin(selected_symbols)] if selected_symbols else df_all.iloc[0:0]

        if date_range and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df["date"].dt.date >= start_date) & (filtered_df["date"].dt.date <= end_date)
            ]

        if filtered_df.empty:
            st.warning("Keine Daten für die aktuelle Auswahl. Bitte Symbole oder Zeitraum anpassen.")
            return

        stats_df = compute_stats(filtered_df)

        st.subheader("Kennzahlen")
        render_kpi_cards(stats_df)

        st.subheader("Kursverlauf")
        render_price_chart(filtered_df, color_map)

        st.subheader("Tägliche Rendite")
        render_return_chart(filtered_df, color_map)

        st.subheader("Rohdaten")
        st.dataframe(filtered_df, use_container_width=True)

        st.subheader("Export")
        if st.button("Als Excel exportieren"):
            with st.spinner("Erstelle Excel-Report ..."):
                export_path = exporter.export_excel(filtered_df, stats_df)

            with open(export_path, "rb") as file:
                st.download_button(
                    label="Excel-Datei herunterladen",
                    data=file.read(),
                    file_name=Path(export_path).name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            st.success(f"Report erstellt: {export_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
