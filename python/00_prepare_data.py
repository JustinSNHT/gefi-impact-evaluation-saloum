"""
00_prepare_data.py
==================
Pipeline de préparation des données GEFI pour l'évaluation d'impact.

Stratégie : extraire ~40 variables analytiques depuis les 14 988 colonnes brutes,
selon la fiche de sélection validée (docs/fiche_selection_variables.md).
Construire un dataset propre, anonymisé, prêt pour entropy balancing.

Étapes :
  1. Chargement du fichier brut (avec cache parquet local pour vitesse)
  2. Chargement du codebook XLSForm (labels variables + modalités)
  3. Anonymisation (hash téléphone, drop noms/PII)
  4. Construction de la variable de traitement (a05 -> traitement)
  5. Identification du chef de ménage dans le roster B et extraction de ses
     caractéristiques (covariables pré-déterminées)
  6. Extraction des outcomes par question (Q1 à Q4)
  7. Décodage des variables catégorielles
  8. Écriture du dataset analytique en parquet

Entrées :
  - data/raw/GEFI_household_survey.xlsx
  - data/raw/Questionnaire_menage_GEFI.xlsx (codebook)

Sorties :
  - data/processed/menages_analyse.parquet  (1 ligne = 1 ménage)
  - data/processed/dictionnaire_variables.csv
  - data/_scratch/_raw_cache.parquet  (cache local, gitignored)

Usage : python python/00_prepare_data.py
"""
import os
import hashlib
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

warnings.filterwarnings('ignore', category=UserWarning)

# ============================================================================
# Configuration
# ============================================================================
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
SCRATCH = ROOT / "data" / "_scratch"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")
SALT = os.getenv("ANON_SALT", "")
if not SALT:
    raise RuntimeError("ANON_SALT introuvable dans .env")

# Définition des îles traitées et contrôle (document GEFI_Introduction.docx)
TREATED_VILLAGES = {"Dionewar", "Niodior", "Falia"}
CONTROL_VILLAGES = {"Djirnda", "Moundé", "Mounde"}

MAX_ROSTER = 30
MAX_FEMMES_18PLUS = 15
MAX_ACTIVITES = 20
MAX_F2_CAT = 25


# ============================================================================
# Helpers
# ============================================================================
def log(msg: str) -> None:
    print(f"[prep] {msg}")


def find_file(pattern: str) -> Path:
    matches = sorted(RAW.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"Aucun fichier {pattern!r} dans {RAW}. "
            f"Fichiers présents : {[p.name for p in RAW.iterdir()]}"
        )
    return matches[0]


def hash_id(s):
    if s is None or pd.isna(s):
        return None
    return hashlib.sha256(f"{SALT}|{s}".encode()).hexdigest()[:12]


def norm_phone(s):
    if pd.isna(s):
        return None
    s = ''.join(ch for ch in str(s) if ch.isdigit())
    if len(s) == 12 and s.startswith('221'):
        s = s[3:]
    return s if len(s) >= 7 else None


# ============================================================================
# Étape 1 — Codebook
# ============================================================================
def load_codebook(path: Path):
    log("Chargement du codebook...")
    sv = pd.read_excel(path, sheet_name='survey')
    ch = pd.read_excel(path, sheet_name='choices')

    var_labels = dict(zip(sv['name'].astype(str), sv['label'].fillna('').astype(str)))
    var_types = dict(zip(sv['name'].astype(str), sv['type'].fillna('').astype(str)))

    choice_maps = {}
    for ln, grp in ch.dropna(subset=['list_name', 'value']).groupby('list_name'):
        d = {}
        for _, r in grp.iterrows():
            v, lbl = r['value'], r['label']
            d[v] = lbl
            try:
                d[int(v)] = lbl
                d[float(v)] = lbl
                d[str(int(v))] = lbl
            except (ValueError, TypeError):
                pass
        choice_maps[str(ln)] = d

    log(f"  {len(var_labels)} variables, {len(choice_maps)} listes de modalités")
    return var_labels, var_types, choice_maps


def decode(value, choice_map: dict):
    if pd.isna(value):
        return value
    return choice_map.get(value, value)


# ============================================================================
# Étape 2 — Lecture des données (avec cache parquet)
# ============================================================================
def load_data(path: Path, force_reload: bool = False) -> pd.DataFrame:
    cache = SCRATCH / "_raw_cache.parquet"
    if cache.exists() and not force_reload:
        log(f"Lecture depuis cache : {cache.relative_to(ROOT)}")
        return pd.read_parquet(cache)

    log("Lecture du fichier brut (peut prendre 3-5 min sur 14 988 colonnes)...")
    df = pd.read_excel(path, sheet_name='Sheet1', engine='openpyxl')
    log(f"  Lu : {df.shape[0]} lignes × {df.shape[1]} colonnes")
    log("  Sauvegarde du cache pour les prochaines exécutions...")
    df.to_parquet(cache, index=False)
    return df


# ============================================================================
# Étape 3 — Traitement
# ============================================================================
def add_treatment(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    village_norm = df['a05'].astype(str).str.strip()
    df['village'] = village_norm
    df['traitement'] = np.where(
        village_norm.isin(TREATED_VILLAGES), 1,
        np.where(village_norm.isin(CONTROL_VILLAGES), 0, np.nan)
    )
    log(f"  Traitement : {int((df['traitement']==1).sum())} traités, "
        f"{int((df['traitement']==0).sum())} contrôle, "
        f"{int(df['traitement'].isna().sum())} non classés")
    return df


# ============================================================================
# Étape 4 — Chef de ménage et covariables
# ============================================================================
def find_chef_slot(row, liste_a_choices: dict):
    """Retourne le slot du roster où b06 = 'Chef de ménage'."""
    n = int(row.get('b00') or 0)
    n = max(n, 1)
    for slot in range(1, min(n + 1, MAX_ROSTER + 1)):
        col = f'b06_{slot}'
        if col not in row.index:
            continue
        val = row.get(col)
        label = liste_a_choices.get(val, val)
        if isinstance(label, str) and 'chef' in label.lower():
            return slot
    return None


def extract_chef_covariates(df: pd.DataFrame, choice_maps: dict) -> pd.DataFrame:
    log("Identification du chef de ménage et extraction des covariables...")
    liste_a = choice_maps.get('liste_a', {})

    rows = []
    for _, hh in df.iterrows():
        slot = find_chef_slot(hh, liste_a)
        rec = {'caseid': hh.get('caseid'),
               'taille_menage': pd.to_numeric(hh.get('b00'), errors='coerce')}

        if slot is not None:
            rec['sexe_chef'] = decode(hh.get(f'b03_{slot}'), choice_maps.get('sexe', {}))
            rec['matri_chef'] = decode(hh.get(f'b04_{slot}'), choice_maps.get('liste_b', {}))
            rec['age_chef'] = pd.to_numeric(hh.get(f'b05_{slot}'), errors='coerce')
            rec['ethnie_chef'] = decode(hh.get(f'b07_{slot}'), choice_maps.get('ethnie', {}))
            rec['educ_chef'] = decode(hh.get(f'b08_{slot}'), choice_maps.get('liste_c', {}))
        else:
            rec.update({'sexe_chef': None, 'matri_chef': None,
                        'age_chef': None, 'ethnie_chef': None, 'educ_chef': None})

        # Ratio de dépendance depuis le roster
        n = int(hh.get('b00') or 0)
        n = min(n, MAX_ROSTER)
        ages = []
        for s in range(1, n + 1):
            a = pd.to_numeric(hh.get(f'b05_{s}'), errors='coerce')
            if pd.notna(a):
                ages.append(a)
        if ages:
            young = sum(1 for a in ages if a < 15)
            old = sum(1 for a in ages if a >= 65)
            working = sum(1 for a in ages if 15 <= a < 65)
            rec['dependency_ratio'] = (young + old) / working if working > 0 else np.nan
            rec['nb_membres_observes'] = len(ages)
        else:
            rec['dependency_ratio'] = np.nan
            rec['nb_membres_observes'] = 0

        rows.append(rec)

    out = pd.DataFrame(rows)
    log(f"  Chef trouvé pour {out['sexe_chef'].notna().sum()} / {len(out)} ménages")
    return out


# ============================================================================
# Étape 5 — Q1 : autonomisation des femmes
# ============================================================================
def extract_q1_women_empowerment(df: pd.DataFrame, choice_maps: dict) -> pd.DataFrame:
    """La Section N est un repeat sur les femmes 18+ ; on agrège au niveau ménage :
      - n04_a-d  -> 'au moins une femme'
      - n11/13/15 -> 'au moins une femme décide'
      - n17       -> 'au moins une femme'
      - score n19 -> moyenne sur les femmes (somme des 9 binaires / femme,
                     puis moyenne sur les femmes 18+ du ménage)
    """
    log("Extraction des outcomes Q1 (autonomisation des femmes)...")
    yesno = choice_maps.get('yesno', {})
    decision = choice_maps.get('decision', {})

    def is_femme_decide(val):
        lbl = decision.get(val, val)
        if not isinstance(lbl, str):
            return False
        l = lbl.lower()
        return any(p in l for p in ['femme', 'épouse', 'epouse', 'conjointe', 'mère', 'mere'])

    def is_oui(val):
        lbl = yesno.get(val, val) if pd.notna(val) else val
        return isinstance(lbl, str) and lbl.lower() in ('oui', 'yes')

    rows = []
    for _, hh in df.iterrows():
        rec = {'caseid': hh.get('caseid')}

        # n04_a-d : au moins une femme propriétaire
        for letter in ['a', 'b', 'c', 'd']:
            any_yes, n_obs = False, 0
            for w in range(1, MAX_FEMMES_18PLUS + 1):
                col = f'n04_{letter}_{w}'
                if col not in hh.index:
                    continue
                v = hh.get(col)
                if pd.isna(v):
                    continue
                n_obs += 1
                if is_oui(v):
                    any_yes = True
                    break
            rec[f'n04_{letter}_any'] = int(any_yes) if n_obs > 0 else np.nan

        # n11, n13, n15 : au moins une femme décide
        for var in ['n11', 'n13', 'n15']:
            any_femme, n_obs = False, 0
            for w in range(1, MAX_FEMMES_18PLUS + 1):
                col = f'{var}_{w}'
                if col not in hh.index:
                    continue
                v = hh.get(col)
                if pd.isna(v):
                    continue
                n_obs += 1
                if is_femme_decide(v):
                    any_femme = True
                    break
            rec[f'{var}_femme'] = int(any_femme) if n_obs > 0 else np.nan

        # n17 : pouvoir sur le revenu
        any_pouvoir, n_obs = False, 0
        for w in range(1, MAX_FEMMES_18PLUS + 1):
            col = f'n17_{w}'
            if col not in hh.index:
                continue
            v = hh.get(col)
            if pd.isna(v):
                continue
            n_obs += 1
            if is_oui(v):
                any_pouvoir = True
                break
        rec['n17_femme_pouvoir_revenu'] = int(any_pouvoir) if n_obs > 0 else np.nan

        # Score d'autonomie sur les dépenses
        scores_par_femme = []
        for w in range(1, MAX_FEMMES_18PLUS + 1):
            score_w, n_obs_w = 0, 0
            for letter in 'abcdefghi':
                col = f'n19_{letter}_{w}'
                if col not in hh.index:
                    continue
                v = hh.get(col)
                if pd.isna(v):
                    continue
                n_obs_w += 1
                if is_oui(v):
                    score_w += 1
            if n_obs_w >= 5:
                scores_par_femme.append(score_w)
        rec['score_autonomie_depenses'] = (np.mean(scores_par_femme)
                                            if scores_par_femme else np.nan)
        rec['nb_femmes_repondantes'] = len(scores_par_femme)

        rows.append(rec)

    return pd.DataFrame(rows)


# ============================================================================
# Étape 6 — Q2 : revenus et pêche
# ============================================================================
def extract_q2_income_fishing(df: pd.DataFrame, choice_maps: dict) -> pd.DataFrame:
    log("Extraction des outcomes Q2 (revenus / pêche)...")
    yesno = choice_maps.get('yesno', {})

    def to_bin(val):
        lbl = yesno.get(val, val) if pd.notna(val) else val
        if isinstance(lbl, str):
            if lbl.lower() in ('oui', 'yes'):
                return 1
            if lbl.lower() in ('non', 'no'):
                return 0
        return np.nan

    rows = []
    for _, hh in df.iterrows():
        rec = {'caseid': hh.get('caseid')}

        # Revenu total 2023 (somme sur activités déclarées)
        revenus = []
        for k in range(1, MAX_ACTIVITES + 1):
            v = pd.to_numeric(hh.get(f'd00_2023_{k}'), errors='coerce')
            if pd.notna(v):
                revenus.append(v)
        rec['revenu_total_2023'] = sum(revenus) if revenus else np.nan
        rec['n_activites'] = len(revenus)

        # Pêche
        rec['pratique_peche'] = to_bin(hh.get('e00'))
        for var in ['e01_2023', 'e02_2023', 'e03_2023', 'e04_2023', 'e05_2023']:
            rec[var.replace('_2023', '')] = pd.to_numeric(hh.get(var), errors='coerce')
        for var in ['e11', 'e16', 'e18_1', 'e18_2']:
            rec[var] = to_bin(hh.get(var))

        rows.append(rec)

    return pd.DataFrame(rows)


# ============================================================================
# Étape 7 — Q3 : sécurité alimentaire / dépenses / logement
# ============================================================================
def extract_q3_food_security(df: pd.DataFrame, choice_maps: dict) -> pd.DataFrame:
    log("Extraction des outcomes Q3 (soudure / dépenses / logement)...")
    rows = []
    for _, hh in df.iterrows():
        rec = {'caseid': hh.get('caseid')}
        rec['mois_soudure_2023'] = pd.to_numeric(hh.get('g1_2023'), errors='coerce')
        rec['materiau_toit'] = decode(hh.get('h1'), choice_maps.get('materiaux', {}))

        montants = []
        for k in range(1, MAX_F2_CAT + 1):
            v = pd.to_numeric(hh.get(f'f2_montant_{k}'), errors='coerce')
            if pd.notna(v):
                montants.append(v)
        rec['depense_totale'] = sum(montants) if montants else np.nan
        rec['n_categories_depense'] = len(montants)

        rows.append(rec)
    return pd.DataFrame(rows)


# ============================================================================
# Étape 8 — Q4 : environnement
# ============================================================================
def extract_q4_environment(df: pd.DataFrame, choice_maps: dict) -> pd.DataFrame:
    log("Extraction des outcomes Q4 (environnement)...")
    yesno = choice_maps.get('yesno', {})

    def to_bin(val):
        lbl = yesno.get(val, val) if pd.notna(val) else val
        if isinstance(lbl, str):
            if lbl.lower() in ('oui', 'yes'):
                return 1
            if lbl.lower() in ('non', 'no'):
                return 0
        return np.nan

    rows = []
    for _, hh in df.iterrows():
        rec = {'caseid': hh.get('caseid')}
        for var in ['k01_1', 'k01_2', 'k01_3', 'k04']:
            rec[var] = to_bin(hh.get(var))
        comps = [rec['k01_1'], rec['k01_2'], rec['k01_3']]
        rec['score_adaptation'] = sum(comps) if all(pd.notna(c) for c in comps) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


# ============================================================================
# Étape 9 — Dictionnaire
# ============================================================================
def build_dictionary() -> pd.DataFrame:
    mapping = [
        ('hh_id', 'Identifiant ménage anonymisé (SHA-256 salé)', 'a00 / a07'),
        ('village', "Village d'enquête", 'a05'),
        ('traitement', '1 = îles traitées, 0 = contrôle', 'a05'),
        ('taille_menage', 'Nombre de membres du ménage', 'b00'),
        ('sexe_chef', 'Sexe du chef de ménage', 'b03 chef'),
        ('matri_chef', 'Situation matrimoniale du chef', 'b04 chef'),
        ('age_chef', 'Âge du chef de ménage', 'b05 chef'),
        ('ethnie_chef', 'Ethnie du chef', 'b07 chef'),
        ('educ_chef', "Niveau d'éducation du chef", 'b08 chef'),
        ('dependency_ratio', '(0-14 + 65+) / 15-64', 'calculé sur b05'),
        ('n04_a_any', 'Au moins une femme propriétaire de terres', 'n04_a'),
        ('n04_b_any', 'Au moins une femme propriétaire de bétail', 'n04_b'),
        ('n04_c_any', 'Au moins une femme propriétaire de biens durables', 'n04_c'),
        ('n04_d_any', "Au moins une femme propriétaire d'autres équipements", 'n04_d'),
        ('n11_femme', 'Au moins une femme décide des facteurs de production', 'n11'),
        ('n13_femme', "Au moins une femme décide pour l'école des enfants", 'n13'),
        ('n15_femme', 'Au moins une femme décide pour la santé des enfants', 'n15'),
        ('n17_femme_pouvoir_revenu', 'Au moins une femme a pouvoir sur le revenu', 'n17'),
        ('score_autonomie_depenses', "Moyenne du score d'autonomie (0-9) sur les femmes 18+", 'n19_a-i'),
        ('nb_femmes_repondantes', 'Nombre de femmes 18+ ayant répondu', 'Section N'),
        ('revenu_total_2023', 'Revenu total 2023 (somme sur activités)', 'd00_2023_*'),
        ('n_activites', "Nombre d'activités génératrices de revenu", 'Section D'),
        ('pratique_peche', 'Le ménage pratique la pêche', 'e00'),
        ('e01', 'Production halieutique totale 2023 (kg)', 'e01_2023'),
        ('e02', 'Quantité autoconsommée 2023 (kg)', 'e02_2023'),
        ('e03', 'Quantité vendue 2023 (kg)', 'e03_2023'),
        ('e04', 'Quantité perdue 2023 (kg)', 'e04_2023'),
        ('e05', 'Quantité transformée 2023 (kg)', 'e05_2023'),
        ('e11', "Dispose d'un contrat de vente", 'e11'),
        ('e16', 'Diversification depuis 2021', 'e16'),
        ('e18_1', 'Pratique du séchage', 'e18_1'),
        ('e18_2', 'Pratique du fumage', 'e18_2'),
        ('mois_soudure_2023', 'Nombre de mois de soudure en 2023', 'g1_2023'),
        ('materiau_toit', 'Matériau du toit du logement', 'h1'),
        ('depense_totale', 'Dépense totale (somme catégories F2)', 'f2_montant_*'),
        ('n_categories_depense', 'Nombre de catégories de dépenses', 'Section F2'),
        ('k01_1', 'Adaptation : diversification', 'k01_1'),
        ('k01_2', 'Adaptation : méthodes nouvelles de pêche', 'k01_2'),
        ('k01_3', 'Adaptation : traitement des déchets', 'k01_3'),
        ('k04', 'Présence de zones protégées', 'k04'),
        ('score_adaptation', "Score d'adaptation (0-3)", 'k01_1+k01_2+k01_3'),
    ]
    return pd.DataFrame(mapping, columns=['variable', 'label', 'source_brut'])


# ============================================================================
# Main
# ============================================================================
def main():
    log("=== DÉBUT PIPELINE PRÉPARATION GEFI ===")

    f_data = find_file("GEFI_household_survey.xlsx")
    f_book = find_file("Questionnaire_menage_GEFI.xlsx")

    var_labels, var_types, choice_maps = load_codebook(f_book)
    df = load_data(f_data)

    log("Anonymisation des identifiants...")
    df['_phone_norm'] = df.get('a07', pd.Series(index=df.index)).apply(norm_phone)
    df['_id_source'] = df['_phone_norm'].fillna(df.get('a00', pd.Series(index=df.index)).astype(str))
    df['hh_id'] = df['_id_source'].apply(hash_id)

    df = add_treatment(df)

    cov = extract_chef_covariates(df, choice_maps)
    cov['hh_id'] = df['hh_id'].values
    q1 = extract_q1_women_empowerment(df, choice_maps)
    q1['hh_id'] = df['hh_id'].values
    q2 = extract_q2_income_fishing(df, choice_maps)
    q2['hh_id'] = df['hh_id'].values
    q3 = extract_q3_food_security(df, choice_maps)
    q3['hh_id'] = df['hh_id'].values
    q4 = extract_q4_environment(df, choice_maps)
    q4['hh_id'] = df['hh_id'].values

    log("Assemblage du dataset analytique...")
    base = df[['hh_id', 'village', 'traitement']].copy()
    out = (base
           .merge(cov.drop(columns=['caseid'], errors='ignore'), on='hh_id', how='left')
           .merge(q1.drop(columns=['caseid'], errors='ignore'), on='hh_id', how='left')
           .merge(q2.drop(columns=['caseid'], errors='ignore'), on='hh_id', how='left')
           .merge(q3.drop(columns=['caseid'], errors='ignore'), on='hh_id', how='left')
           .merge(q4.drop(columns=['caseid'], errors='ignore'), on='hh_id', how='left'))

    n_before = len(out)
    out = out.drop_duplicates(subset='hh_id', keep='first').reset_index(drop=True)
    if n_before != len(out):
        log(f"  Dédoublonnage : {n_before} → {len(out)} ménages")

    for c in out.columns:
        if out[c].dtype == 'object':
            out[c] = out[c].astype('string')

    out_path = OUT / "menages_analyse.parquet"
    out.to_parquet(out_path, index=False)
    log(f"  ✓ {out_path.relative_to(ROOT)} : {len(out)} ménages × {out.shape[1]} variables")

    dico = build_dictionary()
    dico_path = OUT / "dictionnaire_variables.csv"
    dico.to_csv(dico_path, index=False, encoding='utf-8')
    log(f"  ✓ {dico_path.relative_to(ROOT)} : {len(dico)} variables documentées")

    log("=== FIN PIPELINE ===")
    log(f"Ménages traités  : {int((out['traitement']==1).sum())}")
    log(f"Ménages contrôle : {int((out['traitement']==0).sum())}")
    log(f"Non classés      : {int(out['traitement'].isna().sum())}")


if __name__ == "__main__":
    main()