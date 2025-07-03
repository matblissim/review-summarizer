# 🤖 Review Summarizer AI

Système automatique de résumé d'avis clients utilisant OpenAI et BigQuery.

## 📋 Fonctionnalités

- **Échantillonnage intelligent** : Sélection équilibrée des avis par note
- **Analyse IA** : Résumés automatiques avec OpenAI GPT-4o-mini
- **Stockage BigQuery** : Sauvegarde structurée des résumés
- **Optimisation des coûts** : ~8-12€/mois pour 30 produits

## 🛠️ Installation

1. **Clonez le repository**
```bash
git clone https://github.com/votre-username/review-summarizer.git
cd review-summarizer
```

2. **Installez les dépendances**
```bash
pip install -r requirements.txt
```

3. **Configuration**
   - Créez `openai.txt` avec votre clé API OpenAI
   - Placez votre `service-account-key.json` BigQuery
   - Modifiez `PROJECT_ID` dans `main.py` si nécessaire

## 📊 Structure des données

### Table BigQuery d'entrée
```sql
-- Table source : normalised-417010.reviews.reviews_by_user
SELECT fz_sku, fr_comment, rating, review_date 
FROM reviews_by_user
WHERE fr_comment IS NOT NULL
```

### Table BigQuery de sortie
```sql
-- Table générée : normalised-417010.reviews.product_summaries
CREATE TABLE product_summaries (
  fz_sku STRING,
  summary_date DATE,
  positive_summary STRING,
  negative_summary STRING,
  key_themes ARRAY<STRING>,
  improvement_suggestions STRING,
  -- ... autres champs
)
```

## 🚀 Utilisation

**Exécution manuelle :**
```bash
python main.py
```

**Exemple de résultat :**
```json
{
  "positive_summary": "Les clients apprécient la texture douce et l'efficacité du produit.",
  "negative_summary": "Certains trouvent l'odeur trop forte et le prix élevé.",
  "key_themes": ["texture", "efficacité", "odeur", "prix"],
  "improvement_suggestions": "Réduire l'intensité du parfum",
  "standout_features": ["texture douce", "nettoyage efficace"]
}
```

## 💰 Coûts

- **OpenAI GPT-4o-mini** : ~$0.15/1M tokens entrée, $0.60/1M tokens sortie
- **BigQuery** : Négligeable pour les volumes traités
- **Estimation mensuelle** : 8-12€ pour 30 produits analysés quotidiennement

## 🔧 Configuration

### Variables à modifier dans `main.py`
```python
PROJECT_ID = "votre-projet-gcp"  # Votre projet BigQuery
MODEL_NAME = "gpt-4o-mini"        # Modèle OpenAI
```

### Échantillonnage des avis
- **Période** : 90 derniers jours
- **Maximum** : 40 avis par note par produit (200 total max)
- **Minimum** : 5 avis pour générer un résumé

## 📈 Automatisation

Pour une exécution quotidienne, utilisez :
- **Cloud Functions** + **Cloud Scheduler** (GCP)
- **GitHub Actions** + **Cron**
- **Crontab** (serveur Linux)

## 🔒 Sécurité

- ✅ Fichiers secrets dans `.gitignore`
- ✅ Compte de service avec permissions minimales
- ✅ Clés API stockées localement uniquement

## 🏗️ Architecture

```
BigQuery (avis) → Script Python → OpenAI API → BigQuery (résumés)
```

## 🤝 Contribution

Les contributions sont les bienvenues ! 

1. Fork le projet
2. Créez une branche (`git checkout -b feature/amelioration`)
3. Committez (`git commit -m 'Ajout fonctionnalité'`)
4. Push (`git push origin feature/amelioration`)
5. Ouvrez une Pull Request

## 📝 License

Ce projet est sous licence MIT.

## 🐛 Support

Pour toute question ou problème, ouvrez une issue sur GitHub.