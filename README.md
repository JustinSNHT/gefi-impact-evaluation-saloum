# GEFI Impact Evaluation — Saloum Delta, Senegal

Cross-sectional impact evaluation of the GEFI project (*Gouvernance Économique Féminine dans la transformation des produits halieutiques*), implemented in three islands of the Saloum Delta. GEFI targets women's economic governance in fisheries processing, biodiversity preservation, and climate adaptation. This repository contains the full analysis pipeline — Python, R, and a Power BI dashboard — built as part of a data science portfolio in applied development economics.

## Design and data

GEFI operated in Dionewar, Niodior, and Falia (344 households) starting in 2020–21. The comparison group covers the adjacent islands of Djirnda and Moundé (341 households). The evaluation relies on a single endline household survey (n = 685) with no baseline, which limits identification to a treatment-control comparison under the assumption of pre-intervention comparability.

That assumption is imperfect. The two communes differ structurally: treated households are substantially larger (SMD = 0.87), headed by older individuals (SMD = 0.37), and have a higher share of widowed household heads (SMD = 0.56 on *veuf/veuve*) — a pattern consistent with higher male mortality in maritime communities and pre-existing demographic differences between the communes. These differences motivate covariate adjustment; they also bound what causal identification can deliver here.

## Findings

Results from OLS-adjusted estimation; AIPW provided as robustness check. All estimates are treatment-control differences at endline; they should be read as indicative rather than causal given the design.

**Women's empowerment** — The clearest gains are in decision-making: women in treated households are significantly more likely to report deciding on children's schooling (+25 pp) and healthcare (+26 pp), and on the use of household income (+18 pp). Ownership of productive assets shows positive but imprecise effects. Against this, the autonomy-over-expenditures score (0–9 composite) is *lower* in treated households (−1.47 points). The most plausible reading is that GEFI shifted decisions toward women's groups and collective governance at the expense of individual household-level spending autonomy — a known dynamic in group-based interventions in the Sahel.

**Income and fisheries** — Treated households report substantially higher total household income in 2023 (+3.1M FCFA, OLS). Quantities sold (+1,650 kg) and transformed (+555 kg) are positive, consistent with GEFI's processing objective. Formal sales contracts are, however, *less* common in treated islands (−0.49), which may reflect a substitution toward collective marketing through the women's groups rather than individual contracting.

**Food security** — Treated households report 0.49 fewer months of lean season on average, alongside higher total expenditure (+610K FCFA). The directional consistency between income, expenditure, and lean season reduction is the most internally coherent result set in the evaluation.

**Environmental adaptation** — The strongest and most consistent effects are here: adoption of new fishing methods (+27 pp), waste management practices (+25 pp), and activity diversification (+18 pp); composite adaptation score +0.69 on a 0–3 scale. These are GEFI's most operationally explicit objectives and the results reflect them.

## Methodology

**Estimation strategy.** The analysis uses three estimators: naive treatment-control difference, OLS adjusted on pre-determined household and head-of-household characteristics, and augmented IPW (AIPW, doubly robust). *OLS is the principal estimator.* Entropy balancing (EB, Hainmueller 2012) was implemented from scratch in Python via `scipy.optimize` and cross-validated in R via `WeightIt`, but was not retained: the covariate imbalance is severe enough that the EB optimum collapses to a near-degenerate solution (effective sample size < 20% of the control group, weights concentrated on one to two households). Proceeding with EB estimates would have produced technically valid but empirically meaningless counterfactuals. This diagnostic is documented in `python/02_analysis.ipynb` and is itself an analytic finding.

**Covariates.** Household size, household head age, sex, education, marital status, and ethnicity, plus a dependency ratio computed from the full household roster. These are the only variables plausibly pre-determined with respect to the 2020–21 project start. All other survey variables measured at endline are potential outcomes; using them as controls would introduce post-treatment bias.

**Inference.** With treatment assigned at the island level and only five islands, cluster-robust inference at the island level is unreliable (too few clusters for asymptotic approximations). Standard errors are heteroskedasticity-robust (HC3). Results flagged as significant at the 5% level should be read with this caveat in mind — they are best understood as characterising effect magnitude rather than providing formal hypothesis tests.

## Repository structure

```
gefi-impact-evaluation-saloum/
├── data/
│   ├── raw/              ← survey data, gitignored (PII)
│   └── processed/        ← aggregated outputs committed here
├── python/
│   ├── 00_prepare_data.py          ← extracts ~40 variables from 14,988-column raw file
│   ├── 01_eda.ipynb                ← sample description, pre-weighting love plot
│   ├── 02_analysis.ipynb           ← entropy balancing diagnostic + estimation battery
│   └── 03_export_dashboard_csv.py  ← Power BI data export
├── r/
│   ├── install_packages.R
│   ├── 01_analysis.R               ← WeightIt/cobalt replication, cross-validates Python
│   └── 02_figures.R                ← love plot, forest plot
├── powerbi/
│   ├── data/                       ← CSV exports for Power BI (UTF-8 BOM, ; separator)
│   ├── screenshots/                ← dashboard captures for README
│   └── GUIDE_CONSTRUCTION.md
└── docs/
    ├── fiche_selection_variables.md
    └── figures/
```

## Reproducing the analysis

```bash
# 1. Set up the environment
cd gefi-impact-evaluation-saloum
python -m venv .venv && source .venv/Scripts/activate  # Windows Git Bash
pip install -r python/requirements.txt
python -m ipykernel install --user --name=gefi-impact-evaluation-saloum \
       --display-name="Python (GEFI)"

# 2. Add .env with the anonymisation salt
echo 'ANON_SALT=your-salt-here' > .env

# 3. Place raw survey files in data/raw/ then run
python python/00_prepare_data.py
jupyter notebook python/01_eda.ipynb
jupyter notebook python/02_analysis.ipynb
python python/03_export_dashboard_csv.py

# 4. R replication (from RStudio or terminal)
Rscript r/install_packages.R
Rscript r/01_analysis.R
Rscript r/02_figures.R
```

The raw survey data (`GEFI_household_survey.xlsx`, ~69MB) is not versioned due to PII — the file contains household head names and phone numbers. The processed aggregates committed in `data/processed/` allow the downstream analysis (R estimation, Power BI) to run without the raw file.

## Limitations

The design cannot support strong causal claims. Three structural constraints bind:

First, the absence of a baseline means the identifying assumption — that treated and control communities would have evolved similarly without GEFI — cannot be verified. The demographic evidence suggests it may not hold.

Second, treatment selection operated at the commune level, not the household level. Village-level confounders (market access, state of the fisheries resource, pre-existing women's group activity) are not addressed by household-level covariate adjustment and cannot be absorbed with only five clusters.

Third, the survey was conducted several years into project implementation, so some variables typically used as pre-treatment controls (household size, asset holdings) may themselves reflect programme effects. The analysis restricts the covariate set to variables most plausibly unaffected by a 2020–21 intervention (head-of-household demographics), at the cost of a narrower adjustment.

Given these constraints, the results are better read as an end-line characterisation of the two populations with covariate-adjusted comparisons, rather than as impact estimates in the experimental sense.

## Author

**Justin Chery** — Associate Researcher & Evaluation Specialist, Centre de Recherche pour le Développement Économique et Social (CRDES), Dakar, Senegal. PhD candidate in Economics, Université Gaston Berger.

[GitHub](https://github.com/JustinSNHT)

## Licence

Survey data: not redistributed (property of CRDES; contact the author for access queries).
