# install_packages.R
# =============================================================================
# Installation des dépendances R pour la réplication GEFI.
# À exécuter une seule fois, avant 01_analysis.R et 02_figures.R.
# =============================================================================

packages <- c(
  # Data
  "tidyverse",     # dplyr, ggplot2, tidyr, readr, purrr
  "arrow",         # lecture des fichiers parquet produits par Python
  "here",          # gestion robuste des chemins

  # Inférence causale
  "WeightIt",      # entropy balancing, IPW, etc.
  "cobalt",        # diagnostics d'équilibre + love plots
  "MatchIt",       # alternatives d'appariement (référence)

  # Inférence et estimation
  "sandwich",      # variance-covariance robuste (HC3)
  "lmtest",        # tests sur modèles linéaires avec SE robustes
  "marginaleffects",  # comparaisons et effets marginaux

  # Mise en forme
  "broom",         # tidiers pour modèles
  "modelsummary",  # tableaux de régression
  "patchwork",     # composition de plots
  "scales"         # mise en forme axes
)

new <- packages[!packages %in% installed.packages()[, "Package"]]
if (length(new)) {
  cat("Installation de", length(new), "paquet(s) :\n")
  cat("  ", paste(new, collapse = ", "), "\n")
  install.packages(new, repos = "https://cloud.r-project.org")
} else {
  cat("Tous les paquets sont déjà installés.\n")
}

# Vérification
for (p in packages) {
  ok <- requireNamespace(p, quietly = TRUE)
  cat(sprintf("  [%s] %s\n", ifelse(ok, "OK", "MANQUANT"), p))
}
