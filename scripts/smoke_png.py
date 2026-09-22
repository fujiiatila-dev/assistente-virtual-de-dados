"""Exercise the real Kaleido/Chromium export without writing an image to disk."""

from __future__ import annotations

import sys

import plotly.graph_objects as go
from dotenv import load_dotenv

from data_assistant.visualization import ImageExportError, figure_to_png


def main() -> int:
    load_dotenv()
    figure = go.Figure(data=[go.Bar(x=["verificação"], y=[1])])
    try:
        payload = figure_to_png(figure)
    except ImageExportError as exc:
        print(f"Falha no smoke check PNG: {exc}", file=sys.stderr)
        return 1
    print(f"PNG válido gerado em memória ({len(payload)} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
