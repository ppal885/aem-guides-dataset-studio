# ─────────────────────────────────────────────────────────────────────────────
# GIT SETUP — Run these commands in your terminal
# from: C:\Users\prashantp\Videos\aem-guides-dataset-studio
# ─────────────────────────────────────────────────────────────────────────────


# ── STEP 1: Create the repo on GitHub ────────────────────────────────────────
# Go to https://github.com/new and create:
#   Name:        aem-guides-dataset-studio
#   Description: Generate spec-compliant DITA from Jira issues using AI, RAG and MCP
#   Visibility:  Public
#   DO NOT initialize with README (we already have one)
# Then come back here.


# ── STEP 2: Copy these files into your project root ──────────────────────────
# From the Claude output, copy:
#   README.md        → project root
#   .gitignore       → project root
#   .env.example     → project root
#   requirements.txt → project root
#   setup.bat        → project root
#   setup.sh         → project root


# ── STEP 3: Create placeholder directories (git needs at least one file) ──────
mkdir output\dita
echo. > output\dita\.gitkeep
mkdir output\packages
echo. > output\packages\.gitkeep
mkdir dita_examples
echo. > dita_examples\.gitkeep
mkdir models
echo. > models\.gitkeep


# ── STEP 4: Initialize git and push ──────────────────────────────────────────

cd C:\Users\prashantp\Videos\aem-guides-dataset-studio

# Initialize git
git init

# Set your identity (if not already set globally)
git config user.name "Prashant P"
git config user.email "your@email.com"

# Add remote — replace YOUR_GITHUB_USERNAME
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/aem-guides-dataset-studio.git

# Stage everything
git add .

# Check what's being committed (make sure .env is NOT listed)
git status

# If .env appears in the list, remove it immediately:
# git rm --cached .env

# First commit
git commit -m "feat: initial commit — AEM Guides Dataset Studio with MCP server

- MCP server with 20+ tools for Jira→DITA generation
- RAG pipeline: Experience League + DITA 1.2/1.3 spec PDFs
- DITA knowledge graph for element nesting rules
- Fine-tuned sentence-transformers embeddings
- Expert DITA examples from DITAWriter repos
- DITA validation, enrichment, quality scoring
- Jira similarity search with embedding support
- Full Jira→DITA analysis pipeline
- Setup scripts for Windows and Mac/Linux"

# Push
git branch -M main
git push -u origin main


# ── STEP 5: Add a GitHub description + topics ─────────────────────────────────
# After pushing, go to your GitHub repo page and:
# 1. Add description: "Generate spec-compliant DITA from Jira issues using AI, RAG and MCP"
# 2. Add topics (tags): dita, aem, jira, mcp, rag, cursor, dita-xml, content-management,
#                       adobe-experience-manager, technical-writing, python


# ── FUTURE: Pushing updates ───────────────────────────────────────────────────
git add .
git commit -m "feat: add validate_and_fix_dita tool"
git push
