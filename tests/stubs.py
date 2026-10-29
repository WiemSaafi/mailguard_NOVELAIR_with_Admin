"""
stubs.py — réglages des tests (à importer AVANT mailguard_core).

Les tests utilisent les VRAIS modèles du dossier modeles_mailguard/.
Deux options seulement, pour pouvoir tester hors ligne :

  Base de données : une base JETABLE dans le dossier temporaire (jamais mailguard.db).

  MAILGUARD_INTERNET=0  (posé ici par défaut)
      Le signal 2 n'interroge ni RDAP ni crt.sh : il devient muet (vaut 0).
      Les résultats sont donc reproductibles d'un lancement à l'autre.

  MAILGUARD_FAUX_E5=1   (facultatif)
      Remplace l'encodeur multilingual-e5 (1,1 Go) par un vecteur aléatoire,
      pour tester l'application sur une machine sans le modèle. Le signal 4
      n'a alors AUCUN sens : à utiliser seulement pour vérifier que les pages
      s'affichent, jamais pour mesurer la qualité.
"""

import os
import sys

sys.path.insert(0, os.environ.get("MAILGUARD_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MAILGUARD_INTERNET", "0")

# Les tests n'écrivent JAMAIS dans la vraie base mailguard.db : par défaut, ils
# utilisent une base jetable, recréée à chaque lancement.
if not os.environ.get("MAILGUARD_DATABASE_URL"):
    import tempfile
    _base_test = os.path.join(tempfile.gettempdir(), f"mailguard_tests_{os.getpid()}.db")
    if os.path.exists(_base_test):
        os.remove(_base_test)
    os.environ["MAILGUARD_DATABASE_URL"] = "sqlite:///" + _base_test.replace("\\", "/")

if os.environ.get("MAILGUARD_FAUX_E5") == "1":
    import torch
    import mailguard

    _init = mailguard.MailGuard.__init__

    def _init_faux_e5(self, *args, **kwargs):
        _init(self, *args, **kwargs)

        class _Sortie:
            def __init__(self, ids):
                self.last_hidden_state = torch.randn(ids.shape[0], ids.shape[1], 768)

        self.e5 = lambda **b: _Sortie(b["input_ids"])

    mailguard.MailGuard.__init__ = _init_faux_e5
