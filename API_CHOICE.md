# API Choice

- **API choisie** : Open-Meteo — API météo open-source
- **URL base** : `https://api.open-meteo.com/v1/`
- **Documentation officielle** : https://open-meteo.com/en/docs
- **Auth** : None (totalement gratuite, aucune clé requise)

## Endpoints testés

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/v1/forecast?latitude=48.85&longitude=2.35&current_weather=true` | Météo actuelle à Paris |
| GET | `https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=1` | Géocodage d'une ville |

## Contrats attendus (champs & types)

```json
{
  "latitude":        float,
  "longitude":       float,
  "current_weather": {
    "temperature":   float,   // °C, plage réaliste : -90 à 60
    "windspeed":     float,
    "weathercode":   int,
    "time":          string
  }
}
```

## Cas de tests implémentés

| # | Test | Critère de succès |
|---|------|-------------------|
| 1 | Statut HTTP 200 | `status_code == 200` |
| 2 | Temps de réponse | `< 2 000 ms` |
| 3 | Champs JSON requis | `current_weather`, `latitude`, `longitude` présents |
| 4 | Plage de température | `-90 °C ≤ temp ≤ 60 °C` |
| 5 | Endpoint Géocodage | HTTP 200 + champ `results` présent |
| 6 | Content-Type | `application/json` dans les headers |

## Métriques QoS exposées

- **Disponibilité** (%) = tests PASS / total × 100
- **Temps de réponse moyen / min / max** (ms)
- **Historique** des 50 derniers résultats
- **Planification** : exécution automatique toutes les 5 minutes

## Limites / Rate limiting

- Aucune limite documentée pour les requêtes occasionnelles
- Fair-use : ne pas dépasser quelques milliers de requêtes/jour

## Risques

- API externe : dépend de la disponibilité d'open-meteo.com
- Pas de SLA officiel (mais très stable en pratique)

