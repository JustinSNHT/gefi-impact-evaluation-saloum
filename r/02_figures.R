# 02_figures.R
# =============================================================================
# Figures de l'évaluation GEFI :
#   - Love plot avant / après entropy balancing (via cobalt)
#   - Forest plot des effets OLS standardisés par question (Plan B)
#
# Dépend de 01_analysis.R (lit _R_objects.rds).
# =============================================================================

suppressPackageStartupMessages({
  library(tidyverse)
  library(cobalt)
  library(patchwork)
  library(scales)
  library(here)
})

# Chargement
objs <- readRDS(here("data", "processed", "_R_objects.rds"))
results   <- objs$results
bal_avant <- objs$bal_avant
bal_apres <- objs$bal_apres
eb_fit    <- objs$eb_fit

FIG <- here("docs", "figures")
dir.create(FIG, showWarnings = FALSE, recursive = TRUE)

# =============================================================================
# 1. Love plot avant / après (cobalt)
# =============================================================================
# Renommer pour la lisibilité
rename_vars <- function(name) {
  name |>
    str_replace("taille_menage", "Taille du ménage") |>
    str_replace("age_chef", "Âge du chef") |>
    str_replace("dependency_ratio", "Ratio de dépendance") |>
    str_replace("sexe_chef_", "Sexe chef : ") |>
    str_replace("matri_chef_", "Matri. : ") |>
    str_replace("ethnie_chef_", "Ethnie : ") |>
    str_replace("educ_chef_", "Éduc. : ")
}

p_love <- love.plot(eb_fit,
                    thresholds = c(m = 0.1),
                    var.order = "unadjusted",
                    abs = FALSE,
                    line = TRUE,
                    drop.distance = TRUE,
                    title = "Équilibre des covariables — avant et après entropy balancing",
                    sample.names = c("Avant pondération", "Après EB"),
                    colors = c("grey50", "#1f77b4"),
                    shapes = c(16, 16),
                    var.names = setNames(rename_vars(names(bal_avant$Balance$Diff.Un)),
                                          rownames(bal_avant$Balance))) +
  theme_minimal(base_size = 11) +
  theme(legend.position = "bottom",
        plot.title = element_text(face = "bold"))

ggsave(file.path(FIG, "love_plot_avant_apres_R.png"),
       p_love, width = 10, height = 6, dpi = 150)
cat("✓ docs/figures/love_plot_avant_apres_R.png\n")

# =============================================================================
# 2. Forest plot — effets OLS standardisés
# =============================================================================
# Préparer les données : ordonner par effet, colorier selon significativité
df_forest <- results %>%
  mutate(
    sig = case_when(
      ols_est > 0 & abs(ols_est) > 1.96 * ols_se ~ "Positif sig.",
      ols_est < 0 & abs(ols_est) > 1.96 * ols_se ~ "Négatif sig.",
      TRUE                                        ~ "Non sig."
    ),
    lo_std = ols_lo / sd_pooled,
    hi_std = ols_hi / sd_pooled,
    question_lab = factor(question,
                          levels = c("Q1_Femmes",
                                     "Q2_Revenus_Peche",
                                     "Q3_Soudure_Depenses",
                                     "Q4_Environnement"),
                          labels = c("Q1 — Autonomisation",
                                     "Q2 — Revenus / pêche",
                                     "Q3 — Soudure / dépenses",
                                     "Q4 — Environnement"))
  ) %>%
  group_by(question_lab) %>%
  arrange(question_lab, ols_std) %>%
  mutate(outcome_ord = factor(outcome, levels = outcome)) %>%
  ungroup()

p_forest <- ggplot(df_forest, aes(x = ols_std, y = outcome_ord,
                                   color = sig)) +
  geom_vline(xintercept = 0, color = "black", linewidth = 0.4) +
  geom_errorbarh(aes(xmin = lo_std, xmax = hi_std), height = 0,
                 alpha = 0.4, linewidth = 0.6) +
  geom_point(size = 2.5) +
  scale_color_manual(values = c("Positif sig." = "#d62728",
                                "Négatif sig." = "#2ca02c",
                                "Non sig."     = "grey50")) +
  facet_wrap(~ question_lab, ncol = 1, scales = "free_y") +
  labs(x = "Effet standardisé (OLS ajusté) — IC 95 %",
       y = NULL,
       color = NULL,
       title = "Impact estimé du projet GEFI",
       subtitle = "Estimateur principal : MCO ajusté sur covariables pré-déterminées (Plan B)") +
  theme_minimal(base_size = 11) +
  theme(legend.position = "bottom",
        strip.text = element_text(face = "bold", hjust = 0),
        plot.title = element_text(face = "bold"),
        plot.subtitle = element_text(color = "grey40"))

ggsave(file.path(FIG, "forest_plot_ols_R.png"),
       p_forest, width = 9, height = 10, dpi = 150)
cat("✓ docs/figures/forest_plot_ols_R.png\n")

# =============================================================================
# 3. Figure complémentaire : comparaison Python ↔ R
# =============================================================================
# Compare les estimations OLS de R avec celles de Python (croisement validation)
py_path <- here("data", "processed", "agg_impact_estimates.parquet")
if (file.exists(py_path)) {
  py_est <- arrow::read_parquet(py_path) %>%
    select(outcome, ols_py = ols_est)

  comp <- results %>%
    select(outcome, ols_R = ols_est) %>%
    inner_join(py_est, by = "outcome")

  p_comp <- ggplot(comp, aes(x = ols_py, y = ols_R)) +
    geom_abline(slope = 1, intercept = 0, color = "grey50",
                linetype = "dashed") +
    geom_point(size = 2.2, color = "#1f77b4", alpha = 0.8) +
    geom_text(aes(label = outcome), size = 2.5, vjust = -0.6,
              color = "grey40") +
    labs(x = "Estimation OLS (Python)",
         y = "Estimation OLS (R)",
         title = "Validation croisée Python ↔ R",
         subtitle = "Chaque point = un outcome. Sur la diagonale = réplique parfaite.") +
    theme_minimal(base_size = 11) +
    theme(plot.title = element_text(face = "bold"),
          plot.subtitle = element_text(color = "grey40"))

  ggsave(file.path(FIG, "validation_python_R.png"),
         p_comp, width = 8, height = 7, dpi = 150)
  cat("✓ docs/figures/validation_python_R.png\n")
}

cat("\n=== Fin des figures ===\n")
