# 01_analysis.R
# =============================================================================
# Réplication R de la Phase 2.4 — évaluation d'impact GEFI.
#
# Pipeline :
#   1. Chargement du dataset analytique (produit par Python)
#   2. Diagnostics d'équilibre avant pondération (Love plot)
#   3. Entropy balancing via WeightIt::weightit(method = "ebal")
#   4. Diagnostics post-pondération + ESS (réplique le constat Python)
#   5. Batterie d'estimateurs sur les 4 questions analytiques
#   6. Export des résultats en parquet et CSV
#
# Plan B adopté (cf. Phase 2.4) : OLS est l'estimateur principal, AIPW en
# robustesse, EB conservé comme diagnostic (échec attendu).
# =============================================================================
setwd("C:/Users/DELL/OneDrive/Documents/portfolio-raw-data/GEFI/gefi-impact-evaluation-saloum")


suppressPackageStartupMessages({
  library(arrow)
  library(tidyverse)
  library(WeightIt)
  library(cobalt)
  library(sandwich)
  library(lmtest)
  library(here)
})


# =============================================================================
# 1. Données
# =============================================================================
df <- read_parquet(here("data", "processed", "menages_analyse.parquet"))
cat("Données chargées :", nrow(df), "ménages,", ncol(df), "variables\n")

# Conversion en facteurs pour les catégorielles
df <- df %>%
  mutate(
    traitement_lab = factor(traitement, levels = c(0, 1),
                            labels = c("Contrôle", "Traités")),
    sexe_chef   = factor(sexe_chef),
    matri_chef  = factor(matri_chef),
    ethnie_chef = factor(ethnie_chef),
    educ_chef   = factor(educ_chef)
  )

COVARS <- c("taille_menage", "age_chef", "dependency_ratio",
            "sexe_chef", "matri_chef", "ethnie_chef", "educ_chef")

# Échantillon complet sur covariables
df_ana <- df %>% drop_na(all_of(COVARS))
cat("Échantillon analytique :", nrow(df_ana), "ménages",
    "(T =", sum(df_ana$traitement == 1),
    ", C =", sum(df_ana$traitement == 0), ")\n\n")

formule_traitement <- as.formula(paste("traitement ~", paste(COVARS, collapse = " + ")))

# =============================================================================
# 2. Équilibre AVANT pondération
# =============================================================================
cat("=== Équilibre avant pondération (SMD) ===\n")
bal_avant <- bal.tab(formule_traitement, data = df_ana, estimand = "ATT",
                     thresholds = c(m = 0.1))
print(bal_avant, disp.bal.tab = FALSE)

# =============================================================================
# 3. Entropy balancing via WeightIt
# =============================================================================
cat("\n=== Entropy balancing (WeightIt) ===\n")
eb_fit <- weightit(formule_traitement, data = df_ana,
                   method = "ebal", estimand = "ATT")

cat("Convergence  :", !is.null(eb_fit$weights), "\n")
summary(eb_fit)  # ESS + distribution des poids

# Diagnostics manuels pour cohérence avec Python
w_c <- eb_fit$weights[df_ana$traitement == 0]
ess <- sum(w_c)^2 / sum(w_c^2)
n_c <- length(w_c)
cat(sprintf("\nESS contrôle : %.1f sur %d (%.1f%%)\n",
            ess, n_c, 100 * ess / n_c))
cat(sprintf("Ratio max/min poids : %.1f\n",
            max(w_c) / max(min(w_c[w_c > 0]), 1e-12)))

# =============================================================================
# 4. Équilibre APRÈS pondération
# =============================================================================
cat("\n=== Équilibre après entropy balancing ===\n")
bal_apres <- bal.tab(eb_fit, un = TRUE, thresholds = c(m = 0.1))
print(bal_apres, disp.bal.tab = FALSE)

# =============================================================================
# 5. Batterie d'estimateurs
# =============================================================================
cat("\n=== Estimation par batterie d'estimateurs ===\n")

OUTCOMES <- list(
  Q1_Femmes = c("n04_a_any", "n04_b_any", "n04_c_any", "n04_d_any",
                "n11_femme", "n13_femme", "n15_femme",
                "n17_femme_pouvoir_revenu", "score_autonomie_depenses"),
  Q2_Revenus_Peche = c("revenu_total_2023", "n_activites", "pratique_peche",
                       "e01", "e03", "e05", "e11", "e16", "e18_1", "e18_2"),
  Q3_Soudure_Depenses = c("mois_soudure_2023", "depense_totale",
                          "n_categories_depense"),
  Q4_Environnement = c("k01_1", "k01_2", "k01_3", "k04", "score_adaptation")
)

# ---- Fonction d'estimation pour un outcome -------------------------------
estimate_outcome <- function(outcome, data, eb_weights) {

  # Sous-échantillon avec outcome observé
  d <- data %>% filter(!is.na(.data[[outcome]]))
  w_sub <- eb_weights[!is.na(data[[outcome]])]

  n_obs <- nrow(d)
  if (n_obs < 50) return(NULL)

  mean_T <- mean(d[[outcome]][d$traitement == 1])
  mean_C <- mean(d[[outcome]][d$traitement == 0])

  # --- Naive : différence brute
  f_naive <- as.formula(paste(outcome, "~ traitement"))
  m_naive <- lm(f_naive, data = d)
  t_naive <- coeftest(m_naive, vcov = vcovHC(m_naive, type = "HC3"))
  naive_est <- t_naive["traitement", "Estimate"]
  naive_se  <- t_naive["traitement", "Std. Error"]

  # --- OLS ajusté : principal sous plan B
  f_ols <- as.formula(paste(outcome, "~ traitement +",
                            paste(COVARS, collapse = " + ")))
  m_ols <- lm(f_ols, data = d)
  t_ols <- coeftest(m_ols, vcov = vcovHC(m_ols, type = "HC3"))
  ols_est <- t_ols["traitement", "Estimate"]
  ols_se  <- t_ols["traitement", "Std. Error"]

  # --- EB : pour diagnostic (échec attendu)
  m_eb <- lm(f_naive, data = d, weights = w_sub)
  t_eb <- coeftest(m_eb, vcov = vcovHC(m_eb, type = "HC3"))
  eb_est <- t_eb["traitement", "Estimate"]
  eb_se  <- t_eb["traitement", "Std. Error"]

  # --- AIPW manuel : doublement robuste
  ps_fit  <- glm(formule_traitement, data = d, family = binomial())
  ps      <- pmin(pmax(predict(ps_fit, type = "response"), 0.02), 0.98)
  m1 <- lm(reformulate(COVARS, outcome), data = d[d$traitement == 1, ])
  m0 <- lm(reformulate(COVARS, outcome), data = d[d$traitement == 0, ])
  mu1 <- predict(m1, newdata = d)
  mu0 <- predict(m0, newdata = d)
  Y   <- d[[outcome]]
  T_  <- d$traitement
  aipw_pointwise <- mu1 - mu0 + T_ * (Y - mu1) / ps -
                    (1 - T_) * (Y - mu0) / (1 - ps)
  aipw_est <- mean(aipw_pointwise)
  aipw_se  <- sd(aipw_pointwise) / sqrt(n_obs)

  tibble(
    outcome = outcome, n_obs = n_obs,
    mean_C = mean_C, mean_T = mean_T,
    naive_est = naive_est, naive_se = naive_se,
    ols_est = ols_est,     ols_se = ols_se,
    eb_est = eb_est,       eb_se = eb_se,
    aipw_est = aipw_est,   aipw_se = aipw_se,
    sd_pooled = sqrt((var(Y[T_ == 1]) + var(Y[T_ == 0])) / 2)
  )
}

# Boucle sur questions et outcomes
all_results <- map_dfr(names(OUTCOMES), function(q) {
  cat(sprintf("\n--- %s ---\n", q))
  map_dfr(OUTCOMES[[q]], function(o) {
    res <- estimate_outcome(o, df_ana, eb_fit$weights)
    if (!is.null(res)) {
      res$question <- q
      cat(sprintf("  %-30s  OLS = %+9.4f (SE=%.4f) | EB = %+9.4f\n",
                  o, res$ols_est, res$ols_se, res$eb_est))
    }
    res
  })
})

# Mise en évidence des effets standardisés (OLS, estimateur principal)
all_results <- all_results %>%
  mutate(
    ols_std    = ols_est / sd_pooled,
    ols_std_se = ols_se  / sd_pooled,
    ols_lo     = ols_est - 1.96 * ols_se,
    ols_hi     = ols_est + 1.96 * ols_se
  )

# =============================================================================
# 6. Export des agrégats (pour comparaison croisée avec Python)
# =============================================================================
PROC <- here("data", "processed")

all_results %>%
  select(question, outcome, n_obs, mean_C, mean_T,
         naive_est, naive_se, ols_est, ols_se, ols_std, ols_std_se,
         ols_lo, ols_hi, eb_est, eb_se, aipw_est, aipw_se) %>%
  write_parquet(file.path(PROC, "agg_impact_estimates_R.parquet"))

# SMD avant/après pour comparaison
smd_R <- tibble(
  covariable = rownames(bal_avant$Balance),
  smd_avant  = bal_avant$Balance$Diff.Un,
  smd_apres  = bal_apres$Balance$Diff.Adj
) %>%
  filter(!is.na(smd_avant))
write_parquet(smd_R, file.path(PROC, "agg_balance_diagnostics_R.parquet"))

# Conserver le fit EB et les balances pour le script 02_figures.R
saveRDS(list(eb_fit = eb_fit,
             bal_avant = bal_avant,
             bal_apres = bal_apres,
             results = all_results,
             smd = smd_R),
        file.path(PROC, "_R_objects.rds"))

cat("\n\n=== FIN — fichiers produits dans data/processed/ ===\n")
cat("  agg_impact_estimates_R.parquet (", nrow(all_results), "outcomes )\n")
cat("  agg_balance_diagnostics_R.parquet (", nrow(smd_R), "covariables )\n")
cat("  _R_objects.rds (objets pour 02_figures.R)\n")
