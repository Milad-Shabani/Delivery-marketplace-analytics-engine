#!/usr/bin/env bash
# One-click publish for delivery-marketplace-analytics-engine.
# Requires: git, GitHub CLI (gh) authenticated (`gh auth login`).
set -euo pipefail

REPO_NAME="delivery-marketplace-analytics-engine"
GITHUB_USER="Milad-Shabani"
DESCRIPTION="NOVAFOOD — end-to-end food-delivery marketplace business analytics, financial planning, demand forecasting & optimization case study (synthetic data)."

echo "==> Initializing git repository"
if [ ! -d .git ]; then
  git init
  git branch -M main
fi

echo "==> Staging and committing files"
git add .
git commit -m "Initial commit: NOVAFOOD business intelligence case study" || echo "(nothing new to commit)"

echo "==> Creating GitHub repository (if it doesn't already exist)"
if ! gh repo view "${GITHUB_USER}/${REPO_NAME}" >/dev/null 2>&1; then
  gh repo create "${GITHUB_USER}/${REPO_NAME}" --public --source=. --remote=origin --description "${DESCRIPTION}"
else
  git remote add origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git" 2>/dev/null || true
fi

echo "==> Pushing to GitHub"
git push -u origin main

echo "==> Setting topics"
gh repo edit "${GITHUB_USER}/${REPO_NAME}" \
  --add-topic business-intelligence \
  --add-topic data-analytics \
  --add-topic python \
  --add-topic forecasting \
  --add-topic financial-modeling \
  --add-topic optimization \
  --add-topic portfolio-project

echo "==> Enabling GitHub Pages (served from the 'dashboard' folder via Actions)"
gh api -X PUT "repos/${GITHUB_USER}/${REPO_NAME}/pages" \
  -f "build_type=workflow" >/dev/null 2>&1 || \
  echo "(Enable Pages manually: Settings -> Pages -> Source: GitHub Actions, if this call failed)"

gh repo edit "${GITHUB_USER}/${REPO_NAME}" --homepage "https://${GITHUB_USER}.github.io/${REPO_NAME}/"

echo "==> Done."
echo "Repo:      https://github.com/${GITHUB_USER}/${REPO_NAME}"
echo "Dashboard: https://${GITHUB_USER}.github.io/${REPO_NAME}/  (after the pages workflow runs)"
