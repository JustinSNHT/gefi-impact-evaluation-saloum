"""
03_export_dashboard_csv.py
==========================
Exporte les agrégats produits par la Phase 2.4 (Python) vers des CSV
encodés en UTF-8 BOM pour Power BI Desktop (Windows).

Colonnes calculées ajoutées à la volée :
  impact_estimates  → ols_lo, ols_hi, significatif, direction, label_outcome
  balance_diagnostics → seuil_avant, couleur_avant
  outcomes_par_groupe → filtrée sur stat = 'mean' uniquement

Usage : python python/03_export_dashboard_csv.py
"""
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
PBI  = ROOT / "powerbi" / "data"
PBI.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Libellés français des outcomes (pour l'affichage Power BI)
# --------------------------------------------------------------------------- #
LABELS = {
    # Q1 — Femmes
    "n04_a_any"               : "Femme propriétaire de terres",
    "n04_b_any"               : "Femme propriétaire de bétail",
    "n04_c_any"               : "Femme propriétaire de biens durables",
    "n04_d_any"               : "Femme propriétaire d'équipements",
    "n11_femme"               : "Femme décide des facteurs de production",
    "n13_femme"               : "Femme décide scolarité enfants",
    "n15_femme"               : "Femme décide santé enfants",
    "n17_femme_pouvoir_revenu": "Femme a pouvoir sur le revenu",
    "score_autonomie_depenses": "Score autonomie dépenses (0-9)",
    # Q2 — Revenus / pêche
    "revenu_total_2023"       : "Revenu total ménage 2023 (FCFA)",
    "n_activites"             : "Nombre d'activités génératrices",
    "pratique_peche"          : "Pratique la pêche",
    "e01"                     : "Production halieutique (kg)",
    "e03"                     : "Quantité vendue (kg)",
    "e05"                     : "Quantité transformée (kg)",
    "e11"                     : "Dispose d'un contrat de vente",
    "e16"                     : "Diversification depuis 2021",
    "e18_1"                   : "Pratique le séchage",
    "e18_2"                   : "Pratique le fumage",
    # Q3 — Soudure / dépenses
    "mois_soudure_2023"       : "Mois de soudure 2023",
    "depense_totale"          : "Dépenses totales ménage (FCFA)",
    "n_categories_depense"    : "Nb catégories de dépenses",
    # Q4 — Environnement
    "k01_1"                   : "Diversification des activités",
    "k01_2"                   : "Nouvelles méthodes de pêche",
    "k01_3"                   : "Gestion des déchets",
    "k04"                     : "Zones protégées dans la localité",
    "score_adaptation"        : "Score d'adaptation climatique (0-3)",
}

# Codes question courts
QUESTION_COURT = {
    "Q1 — Autonomisation des femmes" : "Q1 — Femmes",
    "Q2 — Revenus / pêche"           : "Q2 — Revenus",
    "Q3 — Soudure / dépenses"        : "Q3 — Sécurité alim.",
    "Q4 — Environnement"             : "Q4 — Environnement",
}

# --------------------------------------------------------------------------- #
# 1. impact_estimates.csv
# --------------------------------------------------------------------------- #
est = pd.read_parquet(PROC / "agg_impact_estimates.parquet")

# Colonnes calculées
est["ols_lo"]          = est["ols_est"] - 1.96 * est["ols_se"]
est["ols_hi"]          = est["ols_est"] + 1.96 * est["ols_se"]
est["significatif"]    = (np.abs(est["ols_est"]) > 1.96 * est["ols_se"]).astype(int)
est["direction"]       = np.where(
    est["significatif"] == 0, "Non sig.",
    np.where(est["ols_est"] > 0, "Positif sig.", "Négatif sig.")
)
est["question_court"]  = est["question"].map(QUESTION_COURT).fillna(est["question"])
est["label_outcome"]   = est["outcome"].map(LABELS).fillna(est["outcome"])
est["effet_pct"]       = (est["ols_est"] / est["mean_C"].replace(0, np.nan) * 100).round(1)

# Ordre des colonnes pour Power BI
col_order = [
    "question", "question_court", "outcome", "label_outcome",
    "n_obs", "mean_C", "mean_T",
    "naive_est", "naive_se",
    "ols_est", "ols_se", "ols_lo", "ols_hi",
    "eb_est",  "eb_se",
    "aipw_est", "aipw_se",
    "significatif", "direction", "effet_pct",
]
est = est[[c for c in col_order if c in est.columns]]
est.to_csv(PBI / "impact_estimates.csv", index=False, encoding="utf-8-sig",
           sep=";", decimal=",")
print(f"✓ impact_estimates.csv — {len(est)} outcomes, {len(est.columns)} colonnes")

# --------------------------------------------------------------------------- #
# 2. balance_diagnostics.csv
# --------------------------------------------------------------------------- #
bal = pd.read_parquet(PROC / "agg_balance_diagnostics.parquet")

# Catégories de déséquilibre pour la visualisation
def categorie_smd(s):
    a = abs(s)
    if a >= 0.25: return "Préoccupant (≥0.25)"
    if a >= 0.10: return "Modéré (0.10-0.25)"
    return "Équilibré (<0.10)"

bal["categorie_avant"]   = bal["smd_avant"].apply(categorie_smd)
bal["smd_avant_abs"]     = bal["smd_avant"].abs().round(4)
bal["smd_apres_abs"]     = bal["smd_apres"].abs().round(10)
bal["gain_equilibre"]    = (bal["smd_avant_abs"] - bal["smd_apres_abs"]).round(4)

bal.to_csv(PBI / "balance_diagnostics.csv", index=False, encoding="utf-8-sig",
           sep=";", decimal=",")
print(f"✓ balance_diagnostics.csv — {len(bal)} covariables")

# --------------------------------------------------------------------------- #
# 3. moyennes_par_groupe.csv  (stat = 'mean' uniquement)
# --------------------------------------------------------------------------- #
grp = pd.read_parquet(PROC / "agg_outcomes_par_groupe.parquet")
# Garder uniquement les moyennes
if "stat" in grp.columns:
    grp = grp[grp["stat"] == "mean"].drop(columns="stat")
grp["label_variable"] = grp["variable"].map(LABELS).fillna(grp["variable"])
grp["diff_brute"]     = (grp["traités"] - grp["contrôle"]).round(4)
grp.to_csv(PBI / "moyennes_par_groupe.csv", index=False, encoding="utf-8-sig",
           sep=";", decimal=",")
print(f"✓ moyennes_par_groupe.csv — {len(grp)} variables")

# --------------------------------------------------------------------------- #
# 4. Fichier de métadonnées du projet (textes pour Power BI)
# --------------------------------------------------------------------------- #
meta = pd.DataFrame([
    {"cle": "projet",      "valeur": "GEFI — Gouvernance économique féminine"},
    {"cle": "zone",        "valeur": "Delta du Saloum, Sénégal"},
    {"cle": "traites",     "valeur": "Dionewar, Niodior, Falia"},
    {"cle": "controle",    "valeur": "Djirnda, Moundé"},
    {"cle": "n_traites",   "valeur": "344"},
    {"cle": "n_controle",  "valeur": "341"},
    {"cle": "estimateur",  "valeur": "MCO ajusté (Plan B — EB non retenu)"},
    {"cle": "logiciel",    "valeur": "Python 3.12 + R 4.x"},
    {"cle": "mise_a_jour", "valeur": pd.Timestamp.today().strftime("%d/%m/%Y")},
])
meta.to_csv(PBI / "metadata.csv", index=False, encoding="utf-8-sig",
            sep=";", decimal=",")
print(f"✓ metadata.csv — {len(meta)} entrées")

print(f"\nTous les fichiers dans : {PBI}")
print("Prochaine étape : importer dans Power BI Desktop via Accueil → Obtenir des données → Texte/CSV")
