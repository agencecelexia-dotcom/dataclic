#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Point d'entrée WSGI. C'est ce fichier que Vercel détecte et sert.

    ./app.py                      serveur de développement sur http://127.0.0.1:5000
    RADAR_MOT_DE_PASSE=... ./app.py

La logique est dans radar/web.py ; ce fichier ne fait qu'exposer `app`.
"""

import os

from radar.web import app  # noqa: F401  (Vercel importe ce symbole)

if __name__ == "__main__":
    app.run(host=os.environ.get("HOTE", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5000")),
            debug=bool(os.environ.get("RADAR_DEBUG")))
