@echo off
setlocal enabledelayedexpansion

set REPO_NAME=delivery-marketplace-analytics-engine
set GITHUB_USER=Milad-Shabani
set DESCRIPTION=NOVAFOOD -- end-to-end food-delivery marketplace business analytics, financial planning, demand forecasting ^& optimization case study (synthetic data).

echo ==> Initializing git repository
if not exist ".git" (
  git init
  git branch -M main
)

echo ==> Staging and committing files
git add .
git commit -m "Initial commit: NOVAFOOD business intelligence case study"

echo ==> Creating GitHub repository (if it doesn't already exist)
gh repo view %GITHUB_USER%/%REPO_NAME% >nul 2>&1
if errorlevel 1 (
  gh repo create %GITHUB_USER%/%REPO_NAME% --public --source=. --remote=origin --description "%DESCRIPTION%"
) else (
  git remote add origin https://github.com/%GITHUB_USER%/%REPO_NAME%.git 2>nul
)

echo ==> Pushing to GitHub
git push -u origin main

echo ==> Setting topics
gh repo edit %GITHUB_USER%/%REPO_NAME% --add-topic business-intelligence --add-topic data-analytics --add-topic python --add-topic forecasting --add-topic financial-modeling --add-topic optimization --add-topic portfolio-project

echo ==> Enabling GitHub Pages (served from the 'dashboard' folder via Actions)
gh api -X PUT repos/%GITHUB_USER%/%REPO_NAME%/pages -f build_type=workflow >nul 2>&1

gh repo edit %GITHUB_USER%/%REPO_NAME% --homepage "https://%GITHUB_USER%.github.io/%REPO_NAME%/"

echo ==> Done.
echo Repo:      https://github.com/%GITHUB_USER%/%REPO_NAME%
echo Dashboard: https://%GITHUB_USER%.github.io/%REPO_NAME%/  (after the pages workflow runs)
