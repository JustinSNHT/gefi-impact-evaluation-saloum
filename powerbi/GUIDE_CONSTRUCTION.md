# Guide de construction du dashboard Power BI — Projet GEFI

## Vue d'ensemble

**Fichier à créer** : `powerbi/GEFI_Dashboard.pbix`
**Sources** : 4 CSV dans `powerbi/data/` (produits par `03_export_dashboard_csv.py`)
**Pages** : 4 pages thématiques
**Audience** : Bailleur et organisation de mise en œuvre du projet GEFI

---

## Étape 0 — Prérequis

1. Lancer `python python/03_export_dashboard_csv.py` pour générer les CSV (si pas déjà fait).
2. Copier les 4 figures depuis `docs/figures/` vers `powerbi/screenshots/` :
   - `love_plot_avant_apres_R.png`
   - `forest_plot_ols_R.png` (ou `forest_plot_eb.png` depuis Python)
3. Ouvrir **Power BI Desktop**.

---

## Étape 1 — Import des données

### 1.1 Connecter les 4 CSV

**Accueil → Obtenir des données → Texte/CSV**

Répéter pour chaque fichier :

| Nom de la table dans Power BI | Fichier CSV |
|---|---|
| `impact_estimates` | `powerbi/data/impact_estimates.csv` |
| `balance_diagnostics` | `powerbi/data/balance_diagnostics.csv` |
| `moyennes_par_groupe` | `powerbi/data/moyennes_par_groupe.csv` |
| `metadata` | `powerbi/data/metadata.csv` |

À chaque import : dans la fenêtre d'aperçu, vérifier que :
- Le séparateur est bien **Virgule**
- La ligne d'en-tête est détectée (ligne 1)
- Cliquer **Charger** (pas Transformer pour l'instant)

### 1.2 Transformer `balance_diagnostics` dans Power Query

Pour créer le love plot, on a besoin d'un format **long** (une ligne = une covariable × une période).

**Accueil → Transformer les données → Éditeur Power Query**

Dans la table `balance_diagnostics` :
1. Sélectionner les colonnes `smd_avant` et `smd_apres`
2. Clic droit → **Dépivoter les colonnes**
3. Renommer la colonne `Attribut` en `periode`
4. Renommer la colonne `Valeur` en `smd`
5. Dans `periode`, remplacer :
   - `smd_avant` → `Avant pondération`
   - `smd_apres` → `Après EB`
6. Ajouter une colonne personnalisée : `smd_abs = Number.Abs([smd])`

Cliquer **Fermer et appliquer**.

---

## Étape 2 — Modèle de données

**Vue Modèle** (icône à gauche)

Les 4 tables sont **indépendantes** — aucune relation à créer. Vérifier qu'aucune relation automatique n'a été détectée et supprimée si nécessaire.

Types de données à vérifier :
- `impact_estimates` : `ols_est`, `ols_se`, `ols_lo`, `ols_hi`, `mean_C`, `mean_T` → **Nombre décimal**
- `impact_estimates` : `significatif` → **Nombre entier**
- `balance_diagnostics` : `smd`, `smd_abs` → **Nombre décimal**

---

## Étape 3 — Mesures DAX

**Vue Rapport → Sélectionner la table `impact_estimates` → Nouvelle mesure**

Créer les 7 mesures suivantes :

### Mesure 1 — Nombre d'outcomes significatifs
```dax
Nb_Outcomes_Sig =
COUNTROWS(
    FILTER(impact_estimates, impact_estimates[significatif] = 1)
)
```

### Mesure 2 — Nombre total d'outcomes
```dax
Nb_Outcomes_Total =
COUNTROWS(impact_estimates)
```

### Mesure 3 — Part des outcomes significatifs (%)
```dax
Pct_Significatif =
DIVIDE([Nb_Outcomes_Sig], [Nb_Outcomes_Total]) * 100
```

### Mesure 4 — Couleur du point (pour mise en forme conditionnelle)
```dax
Couleur_Direction =
SWITCH(
    SELECTEDVALUE(impact_estimates[direction]),
    "Positif sig.",  "#2ca02c",
    "Négatif sig.",  "#d62728",
    "#7f7f7f"
)
```

### Mesure 5 — Déséquilibre maximum avant pondération
```dax
SMD_Max_Avant =
MAXX(
    FILTER(balance_diagnostics, balance_diagnostics[periode] = "Avant pondération"),
    balance_diagnostics[smd_abs]
)
```

### Mesure 6 — Effet OLS formaté avec IC
```dax
Effet_Formate =
VAR est = SELECTEDVALUE(impact_estimates[ols_est])
VAR lo  = SELECTEDVALUE(impact_estimates[ols_lo])
VAR hi  = SELECTEDVALUE(impact_estimates[ols_hi])
RETURN
    FORMAT(est, "+0.000;-0.000;0.000") &
    " [" & FORMAT(lo, "0.000") & "; " & FORMAT(hi, "0.000") & "]"
```

### Mesure 7 — Label KPI par question (pour les cartes)
```dax
KPI_Q1 =
VAR eff = CALCULATE(
    AVERAGE(impact_estimates[ols_est]),
    impact_estimates[question_court] = "Q1 — Femmes",
    impact_estimates[significatif] = 1
)
RETURN IF(ISBLANK(eff), "—", FORMAT(eff, "+0.000;-0.000"))
```
*Dupliquer pour Q2, Q3, Q4 en changeant le filtre `question_court`.*

---

## Étape 4 — Thème et palette

**Vue Rapport → Afficher → Thèmes → Personnaliser le thème actuel**

Couleurs principales :
- Arrière-plan : `#FFFFFF`
- En-tête de page : `#264653` (bleu-vert foncé)
- Q1 — Femmes : `#E76F51`
- Q2 — Revenus : `#2A9D8F`
- Q3 — Sécurité alim. : `#F4A261`
- Q4 — Environnement : `#264653`
- Positif significatif : `#2ca02c`
- Négatif significatif : `#d62728`
- Non significatif : `#7f7f7f`

---

## Étape 5 — Page 1 : Vue d'ensemble

**Renommer la page** : double-clic sur l'onglet → `Vue d'ensemble`

### Visual 1 — Titre de page (Zone de texte)
- **Insertion → Zone de texte**
- Texte : `Évaluation d'impact GEFI — Delta du Saloum`
- Police : 18pt, gras, couleur `#264653`
- Sous-texte : `Estimateur principal : MCO ajusté · Période : Endline 2023`
- Police sous-texte : 11pt, couleur `#7f7f7f`

### Visual 2 — Cartes KPI (4 cartes côte à côte)

**Insertion → Carte** × 4

**Carte Q1 — Autonomisation des femmes**
- Champs → Valeur : mesure `KPI_Q1`
- Étiquette : `Outcomes positifs sig. (Q1)`
- Titre de la carte : `Q1 — Autonomisation`
- Couleur titre : `#E76F51`
- Taille : 150 × 80 px

**Carte Q2 — Revenus / pêche**
- Valeur : `KPI_Q2`
- Titre : `Q2 — Revenus`
- Couleur titre : `#2A9D8F`

**Carte Q3 — Sécurité alimentaire**
- Valeur : `KPI_Q3`
- Titre : `Q3 — Sécurité alim.`
- Couleur titre : `#F4A261`

**Carte Q4 — Environnement**
- Valeur : `KPI_Q4`
- Titre : `Q4 — Environnement`
- Couleur titre : `#264653`

### Visual 3 — Carte statistiques globales (Zone de texte ou Carte)

**Insertion → Carte**
- Valeur : mesure `Nb_Outcomes_Sig`
- Étiquette de données : `Outcomes significatifs`

**Insertion → Carte**
- Valeur : mesure `Pct_Significatif`
- Format : `0.0 %`
- Étiquette : `Part des outcomes significatifs`

### Visual 4 — Graphique à barres horizontal : top outcomes

**Visualisations → Graphique à barres groupées**

Configuration :
- Axe Y : `label_outcome` (depuis `impact_estimates`)
- Axe X : `ols_est`
- Petites multiples / Légende : `question_court`
- Trier par : `ols_est` décroissant
- Filtrer pour ne garder que `significatif = 1`

Mise en forme :
- **Format → Barres de données → Couleurs personnalisées** : utiliser la mesure `Couleur_Direction`
- Ligne de référence à 0 : **Format → Ligne de référence → Ajouter une ligne** → Valeur = 0, couleur = noir, tirets

### Visual 5 — Segment (slicer) question

**Visualisations → Segment**
- Champ : `question_court`
- Style : Liste (tuiles)
- Sélection multiple activée

---

## Étape 6 — Page 2 : Équilibre des groupes

**Ajouter une page** → Renommer : `Équilibre des groupes`

### Visual 1 — Zone de texte explicative

Texte :
> *Les groupes traitement et contrôle présentent un déséquilibre démographique important avant pondération (SMD max ≈ 0,87 sur la taille des ménages). L'entropy balancing atteint mathématiquement l'équilibre (SMD_après ≈ 0) mais au prix d'un effectif de pondération très faible (ESS < 20 %). L'estimateur principal retenu est le MCO ajusté sur covariables (Plan B).*

Police : 10pt, couleur `#264653`, fond `#F8F8F8`

### Visual 2 — Love plot (image)

**Insertion → Image**
- Source : `powerbi/screenshots/love_plot_avant_apres_R.png`
- Taille : 500 × 320 px
- Titre : `Équilibre avant / après entropy balancing`

### Visual 3 — Graphique à barres : SMD avant/après

**Visualisations → Graphique à barres groupées**
Source : table `balance_diagnostics` (format long après Power Query)

Configuration :
- Axe Y : `variable` (trier par `smd_abs` décroissant, filtré sur `periode = "Avant pondération"`)
- Axe X : `smd`
- Légende : `periode`
- Couleurs : `Avant pondération` = `#d62728`, `Après EB` = `#1f77b4`

Lignes de référence :
- Ligne à 0 : noir, continue
- Ligne à 0,10 : orange, tirets, étiquette `Seuil acceptable`
- Ligne à -0,10 : orange, tirets
- Ligne à 0,25 : rouge, tirets, étiquette `Seuil critique`
- Ligne à -0,25 : rouge, tirets

Formatage :
- Titre : `Différence de moyennes standardisée (SMD) — Avant et après pondération`
- Activation des étiquettes de données pour la série "Avant pondération" uniquement

### Visual 4 — Tableau SMD détaillé

**Visualisations → Table**
Source : `balance_diagnostics` (format long **non** utilisé ici — revenir à la table originale importée si les deux versions coexistent, ou filtrer sur `periode = "Avant pondération"`)

Colonnes :
1. `variable` → Renommer en `Covariable`
2. `smd_avant` → Renommer en `SMD avant` → Format : `0.000`
3. `smd_apres` → Renommer en `SMD après` → Format : `0.0000000`
4. `categorie_avant` → Renommer en `Catégorie`

**Mise en forme conditionnelle sur `SMD avant`** :
- Format → Couleur de l'arrière-plan → Mise en forme conditionnelle → Règles
  - ≥ 0,25 : fond `#FFCCCC` (rouge clair)
  - entre 0,10 et 0,25 : fond `#FFE6CC` (orange clair)
  - < 0,10 : fond `#CCFFCC` (vert clair)

---

## Étape 7 — Page 3 : Résultats par question

**Ajouter une page** → Renommer : `Résultats par question`

### Visual 1 — Segment question

**Visualisations → Segment**
- Champ : `question_court`
- Style : Tuiles (horizontal)
- Position : haut de page, pleine largeur

### Visual 2 — Forest plot (image embeddée)

**Insertion → Image**
- Source : `powerbi/screenshots/forest_plot_ols_R.png`
- Taille : 480 × 500 px
- Activer **Interaction avec les segments** : Non (l'image est statique)
- Titre : `Impact estimé (MCO ajusté) — IC 95 %`

### Visual 3 — Graphique à barres avec barres d'erreur

**Visualisations → Graphique en courbes et histogramme groupé**

OU utiliser le **Graphique à barres groupées** natif + barres d'erreur :

Configuration barres :
- Axe Y : `label_outcome`
- Axe X (valeurs) : `ols_est`
- Légende : `direction`
- Palettes manuelles : "Positif sig." = `#2ca02c`, "Négatif sig." = `#d62728`, "Non sig." = `#7f7f7f`

**Ajouter les barres d'erreur** :
- Format → Barres d'erreur → Activer
- Type : Champ personnalisé
  - Limite supérieure : `ols_hi`
  - Limite inférieure : `ols_lo`
- Couleur barres d'erreur : `#333333`
- Épaisseur : 1,5 px

Ligne de référence :
- Format → Ligne de référence → Valeur = 0, couleur = `#000000`, style = continue

Trier :
- Les outcomes par `ols_est` décroissant

Filtres :
- Ce visuel filtre automatiquement quand le slicer `question_court` est activé

### Visual 4 — Tableau de synthèse des estimations

**Visualisations → Table**

Colonnes :
1. `label_outcome` → `Outcome`
2. `n_obs` → `N obs.`
3. `mean_C` → `Moy. Contrôle` → Format : `0.000`
4. `mean_T` → `Moy. Traités` → Format : `0.000`
5. `ols_est` → `Effet OLS` → Format : `+0.000;-0.000`
6. `ols_se` → `SE` → Format : `0.000`
7. Mesure `Effet_Formate` → `OLS [IC 95 %]`
8. `direction` → `Significatif`

**Mise en forme conditionnelle sur `Effet OLS`** :
- Dégradé de couleur : rouge (valeurs négatives) → blanc (0) → vert (valeurs positives)
- Point médian : 0

Tri par défaut : `ols_est` décroissant.

---

## Étape 8 — Page 4 : Données et méthodes

**Ajouter une page** → Renommer : `Données et méthodes`

### Visual 1 — Tableau complet des 4 estimateurs

**Visualisations → Table**
Source : `impact_estimates`

Colonnes :
1. `question_court` → `Question`
2. `label_outcome` → `Outcome`
3. `n_obs` → `N`
4. `naive_est` → `Naïf`
5. `ols_est` → `OLS ★` (étoile pour indiquer estimateur principal)
6. `ols_se` → `SE (OLS)`
7. `aipw_est` → `AIPW`
8. `eb_est` → `EB (diag.)`
9. `direction` → `Résultat`

*Note : les colonnes EB et AIPW sont fournies pour la transparence méthodologique.*

Regrouper par `question_court` : Visualisations → Format → Total → Sous-total de lignes → Activer

### Visual 2 — Note méthodologique (Zone de texte)

```
NOTES MÉTHODOLOGIQUES

Estimateur principal (Plan B)
Les groupes traités (Dionewar, Niodior, Falia) et contrôle (Djirnda, Moundé) présentent
un déséquilibre structurel important (SMD max = 0,87 sur taille du ménage). L'entropy
balancing converge mathématiquement mais produit un effectif pondéré très faible
(ESS < 20 %), rendant les estimations EB peu fiables. Le MCO ajusté sur covariables
pré-déterminées est retenu comme estimateur principal ; l'AIPW est fourni en robustesse.

Limites de l'inférence
Avec 5 grappes (îles) seulement, l'inférence statistique reste indicative. Les SE sont
calculés avec correction HC3 (hétéroscédasticité). Les seuils de significativité à 5 %
(|t| > 1,96) sont approximatifs dans ce contexte.

Sources
Enquête ménage GEFI, CRDES, Sénégal. Analyse : Python 3.12 + R 4.x.
```

### Visual 3 — Table de métadonnées

**Visualisations → Table**
Source : `metadata`

Colonnes : `cle` → `Paramètre`, `valeur` → `Valeur`

---

## Étape 9 — Navigation entre pages

**Insertion → Boutons → Vierge** (créer 4 boutons sur chaque page)

Pour chaque bouton :
- Format → Action → Type = **Navigation dans la page**
- Destination = nom de la page cible
- Style : rectangle arrondi, fond `#264653`, texte blanc, 12pt
- Libellés : `Vue d'ensemble` / `Équilibre` / `Résultats` / `Méthodes`

---

## Étape 10 — Export et commit

### Sauvegarder le fichier
- **Fichier → Enregistrer sous** → `powerbi/GEFI_Dashboard.pbix`

### Captures d'écran pour GitHub
Pour chaque page, prendre une capture (Windows : `Win + Maj + S`) et enregistrer dans `powerbi/screenshots/` :
- `screenshot_page1_vue_ensemble.png`
- `screenshot_page2_equilibre.png`
- `screenshot_page3_resultats.png`
- `screenshot_page4_methodes.png`

### Commit
```bash
# Le .pbix ne doit PAS être commité (taille + données)
echo 'powerbi/*.pbix' >> .gitignore
echo 'powerbi/*.pbix.bak' >> .gitignore

# Commiter les CSV, les figures et les screenshots
git add powerbi/data/ powerbi/screenshots/ powerbi/GUIDE_CONSTRUCTION.md
git add python/03_export_dashboard_csv.py
git commit -m "Phase 2.6: Power BI dashboard — 4 pages, OLS as principal estimator"
git push
```

---

## Référence rapide des visuels par page

| Page | Visual principal | Source | Type Power BI |
|---|---|---|---|
| Vue d'ensemble | Barres OLS top outcomes | `impact_estimates` | Graphique barres groupées |
| Équilibre | Love plot image + barres SMD | PNG + `balance_diagnostics` | Image + Barres groupées |
| Résultats | Forest plot image + barres d'erreur | PNG + `impact_estimates` | Image + Barres + Erreur |
| Méthodes | Table 4 estimateurs | `impact_estimates` | Table |
