import openai
from google.cloud import bigquery
import json
import os
from datetime import datetime, date
import logging

# Configuration du compte de service BigQuery
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account-key.json"

# Configuration - MODIFIEZ CES VALEURS SELON VOS BESOINS
PROJECT_ID = "normalised-417010"  # Votre projet BigQuery
MODEL_NAME = "gpt-4o-mini"        # Modèle OpenAI à utiliser

# Lecture de la clé OpenAI depuis le fichier
with open("openai.txt", "r") as f:
    OPENAI_API_KEY = f.read().strip()

# Initialisation des clients
client = openai.OpenAI(api_key=OPENAI_API_KEY)
bq_client = bigquery.Client(project=PROJECT_ID)

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_products_from_file(filename="products.txt"):
    """
    Charge la liste des produits depuis un fichier texte
    """
    products = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Ignorer les lignes vides et les commentaires
                if line and not line.startswith('#'):
                    products.append(line)
        
        logger.info(f"📋 {len(products)} produit(s) chargé(s) depuis {filename}")
        return products
    
    except FileNotFoundError:
        logger.warning(f"⚠️ Fichier {filename} non trouvé, utilisation du produit par défaut")
        return ["RES-STICKNETTOYANTVISAGE-50G"]
    except Exception as e:
        logger.error(f"❌ Erreur lors du chargement de {filename}: {e}")
        return ["RES-STICKNETTOYANTVISAGE-50G"]

def get_reviews_data(product_sku=None):
    """
    Récupère les données d'avis échantillonnées depuis BigQuery avec échantillonnage proportionnel (25%)
    """
    query = """
    WITH recent_reviews AS (
      SELECT 
        fz_sku,
        fr_comment,
        rating,
        review_date
      FROM `normalised-417010.reviews.reviews_by_user`
      WHERE fr_comment IS NOT NULL 
        AND review_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
        {}
    ),
    rating_distribution AS (
      SELECT 
        fz_sku,
        rating,
        COUNT(*) as count_per_rating,
        COUNT(*) OVER (PARTITION BY fz_sku) as total_reviews
      FROM recent_reviews
      GROUP BY fz_sku, rating
    ),
    proportional_sample AS (
      SELECT 
        r.fz_sku,
        r.fr_comment,
        r.rating,
        r.review_date,
        -- Échantillonnage proportionnel : 25% des avis, répartis selon la distribution réelle
        ROW_NUMBER() OVER (
          PARTITION BY r.fz_sku, r.rating 
          ORDER BY r.review_date DESC
        ) as rn,
        -- Calculer combien d'avis prendre par note (25% du total, proportionnel)
        GREATEST(1, CAST(ROUND(rd.count_per_rating * 0.25) AS INT64)) as max_per_rating
      FROM recent_reviews r
      JOIN rating_distribution rd ON r.fz_sku = rd.fz_sku AND r.rating = rd.rating
    )
    SELECT 
      fz_sku,
      STRING_AGG(fr_comment, ' | ' ORDER BY review_date DESC) as all_comments,
      AVG(rating) as avg_rating,
      COUNT(*) as total_reviews,
      MIN(review_date) as period_start,
      MAX(review_date) as period_end
    FROM proportional_sample
    WHERE rn <= max_per_rating
    GROUP BY fz_sku
    HAVING COUNT(*) >= 5
    """
    
    # Ajouter le filtre produit si spécifié
    product_filter = f"AND fz_sku='{product_sku}'" if product_sku else ""
    final_query = query.format(product_filter)
    
    logger.info(f"Exécution de la requête BigQuery...")
    query_job = bq_client.query(final_query)
    results = query_job.result()
    
    return [dict(row) for row in results]

def generate_summary_prompt(comments, avg_rating, total_reviews):
    """
    Génère le prompt pour OpenAI
    """
    # Limiter la taille des commentaires
    max_chars = 2000
    if len(comments) > max_chars:
        comments = comments[:max_chars] + "..."
    
    prompt = f"""Analyse ces {total_reviews} avis clients.

AVIS:
{comments}

Génère un résumé au format JSON avec cette structure exacte:
{{
  "global_analysis": "Analyse globale du produit en 3-4 phrases - vue d'ensemble de la satisfaction client et positionnement général basé uniquement sur les retours clients, sans mentionner de notes numériques",
  "positive_summary": "Résumé des points positifs en 2-3 phrases",
  "negative_summary": "Résumé des points négatifs en 2-3 phrases",
  "key_themes": ["thème1", "thème2", "thème3"],
  "sentiment_distribution": {{
    "très_positif": nombre_estimé_avis_5_étoiles,
    "positif": nombre_estimé_avis_4_étoiles,
    "neutre": nombre_estimé_avis_3_étoiles,
    "négatif": nombre_estimé_avis_2_étoiles,
    "très_négatif": nombre_estimé_avis_1_étoile
  }},
  "improvement_suggestions": "Suggestions d'amélioration basées sur les critiques",
  "standout_features": ["caractéristique1", "caractéristique2"]
}}

Réponds uniquement avec le JSON valide."""
    
    return prompt

def analyze_reviews_with_ai(comments, avg_rating, total_reviews):
    """
    Utilise OpenAI pour analyser les avis
    """
    prompt = generate_summary_prompt(comments, avg_rating, total_reviews)
    
    logger.info(f"Envoi à OpenAI... (prompt: {len(prompt)} caractères)")
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Tu es un expert en analyse de satisfaction client. Réponds toujours en JSON valide."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        response_text = response.choices[0].message.content.strip()
        logger.info(f"Réponse reçue: {len(response_text)} caractères")
        
        # Parse la réponse JSON
        analysis = json.loads(response_text)
        
        # Calcul du coût approximatif
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        # Prix GPT-4o-mini: $0.15/1M input, $0.60/1M output
        cost = (prompt_tokens * 0.15 + completion_tokens * 0.60) / 1_000_000
        
        logger.info(f"Coût de cette requête: ~{cost:.4f}€")
        
        return analysis, cost
        
    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON: {e}")
        logger.error(f"Réponse brute: {response_text[:200]}...")
        return None, 0
    except Exception as e:
        logger.error(f"Erreur lors de l'appel OpenAI: {e}")
        return None, 0

def save_summary_to_bigquery(product_data, analysis, cost):
    """
    Sauvegarde le résumé dans BigQuery
    """
    table_id = "normalised-417010.reviews.product_summaries"
    
    row_to_insert = {
        "fz_sku": product_data['fz_sku'],
        "summary_date": date.today().isoformat(),
        "total_reviews_analyzed": product_data['total_reviews'],
        "avg_rating": float(product_data['avg_rating']),
        "review_period_start": product_data['period_start'].isoformat(),
        "review_period_end": product_data['period_end'].isoformat(),
        "global_analysis": analysis.get('global_analysis', 'N/A'),
        "positive_summary": analysis['positive_summary'],
        "negative_summary": analysis['negative_summary'],
        "key_themes": analysis['key_themes'],
        "sentiment_distribution": json.dumps(analysis['sentiment_distribution']),
        "improvement_suggestions": analysis['improvement_suggestions'],
        "standout_features": analysis['standout_features'],
        "created_at": datetime.now().isoformat(),
        "model_version": MODEL_NAME,
        "processing_cost_euros": cost
    }
    
    logger.info("Sauvegarde dans BigQuery...")
    logger.info(f"Données à insérer: {json.dumps(row_to_insert, indent=2, default=str)}")
    
    try:
        table = bq_client.get_table(table_id)
        logger.info(f"Table trouvée: {table.table_id}")
        
        errors = bq_client.insert_rows_json(table, [row_to_insert])
        
        if errors:
            logger.error(f"Erreurs lors de l'insertion: {errors}")
            return False
        else:
            logger.info(f"✅ Résumé sauvegardé pour {product_data['fz_sku']}")
            
            # Vérification immédiate
            check_query = f"""
            SELECT COUNT(*) as count 
            FROM `{table_id}` 
            WHERE fz_sku = '{product_data['fz_sku']}' 
            AND summary_date = CURRENT_DATE()
            """
            result = bq_client.query(check_query).result()
            count = list(result)[0]['count']
            logger.info(f"Vérification: {count} ligne(s) trouvée(s) pour {product_data['fz_sku']}")
            
            return True
            
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde: {e}")
        return False

def main():
    """
    Fonction principale
    """
    logger.info("🚀 Démarrage du résumé automatique d'avis avec OpenAI")
    
    # Charger la liste des produits depuis le fichier
    products_to_analyze = load_products_from_file()
    
    total_cost = 0
    successful_analyses = 0
    
    try:
        # Traiter chaque produit de la liste
        for product_index, product_sku in enumerate(products_to_analyze, 1):
            logger.info(f"[{product_index}/{len(products_to_analyze)}] 🔍 Recherche d'avis pour {product_sku}")
            
            # 1. Récupération des données pour ce produit
            products_data = get_reviews_data(product_sku=product_sku)
            
            if not products_data:
                logger.warning(f"⚠️ Aucun avis trouvé pour {product_sku}")
                continue
            
            # 2. Traitement du produit (normalement 1 seul résultat)
            for product_data in products_data:
                logger.info(f"[{product_index}/{len(products_to_analyze)}] 📊 Analyse de {product_data['fz_sku']} - {product_data['total_reviews']} avis")
                
                # 3. Analyse IA
                analysis, cost = analyze_reviews_with_ai(
                    product_data['all_comments'],
                    product_data['avg_rating'], 
                    product_data['total_reviews']
                )
                
                total_cost += cost
                
                if analysis:
                    # 4. Sauvegarde
                    success = save_summary_to_bigquery(product_data, analysis, cost)
                    if success:
                        successful_analyses += 1
                        logger.info(f"✅ [{product_index}/{len(products_to_analyze)}] Traitement terminé pour {product_data['fz_sku']}")
                    else:
                        logger.error(f"❌ [{product_index}/{len(products_to_analyze)}] Échec sauvegarde pour {product_data['fz_sku']}")
                else:
                    logger.error(f"❌ [{product_index}/{len(products_to_analyze)}] Échec analyse IA pour {product_data['fz_sku']}")
        
        logger.info(f"🎉 Analyse terminée - {successful_analyses}/{len(products_to_analyze)} produits traités avec succès")
        logger.info(f"💰 Coût total de cette exécution: {total_cost:.4f}€")
    
    except Exception as e:
        logger.error(f"Erreur générale: {e}")
        raise

if __name__ == "__main__":
    main()
