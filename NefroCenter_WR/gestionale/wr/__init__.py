"""NefroCenter WR · Work Resources.

Portale centrale per presenze, persone e processi HR delle strutture NefroCenter.
Il pacchetto contiene solo logica applicativa: nessun dato aziendale, nessuna
credenziale e nessun servizio esterno attivo per impostazione predefinita.
"""

import sys
from pathlib import Path

# Librerie incluse nel pacchetto (waitress, xlsxwriter, segno): nessuna installazione richiesta.
_VENDOR = Path(__file__).resolve().parent.parent / 'vendor'
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

PRODUCT = 'NefroCenter WR'
SUBTITLE = 'Work Resources'
VERSION = '1.0.0'
SCHEMA_VERSION = 1
