# Sorties IA Saint-Dizier & Lac du Der — robot agenda sans clé IA

Un robot GitHub Actions qui régénère chaque nuit un calendrier `der.ics`
(4 activités par soir, scorées selon ton profil pondéré), publié sur GitHub
Pages. Ton téléphone abonné en webcal se met à jour tout seul. Gratuit, sans
serveur, sans clé API.

## Installation (5 minutes)

1. Crée un repo public, par ex. `agenda-ia-der`, et pousse ces fichiers :
   `build_agenda.py`, `activites_permanentes.json`, `.github/workflows/agenda.yml`.
2. Dans **Settings → Pages** : Source = branche `main`, dossier `/docs`.
3. Dans l'onglet **Actions** : lance une fois « Agenda Metz auto » avec
   *Run workflow* → le fichier `docs/der.ics` apparaît, Pages publie le **tableau de bord** à
   `https://gengiscard.github.io/agenda-ia-der/` et le calendrier à
   `https://gengiscard.github.io/agenda-ia-der/der.ics`.
4. **iPhone** : Réglages → Apps → Calendrier → Comptes → Ajouter un compte →
   Autre → *Ajouter un cal. avec abonnement* →
   `webcal://gengiscard.github.io/agenda-ia-der/der.ics`
   (Google Agenda : Autres agendas → + → À partir de l'URL, en `https://`).

C'est terminé : le cron tourne chaque nuit à 6h, commit le nouveau `.ics`
seulement s'il a changé, et ton calendrier suit (Apple/Google rafraîchissent
l'abonnement en quelques heures).

## Comment il choisit

- **Sources web** : flux agendas saint-dizier.fr + Office de tourisme lacduder.com + jds.fr
  (chaque source est optionnelle : si l'une tombe, l'autre suffit).
- **Couche de secours** : `activites_permanentes.json`, une quinzaine
  d'activités vérifiées à la main (Fight Camp 52, Cercle Pugilistique, Arcadia,
  Diable Rouge, Casino JOA, plage et golden hour du Der, restos asiatiques…) avec jours de la semaine et périodes
  de validité. Le calendrier n'est donc jamais vide.
- **Scoring /20** : mots-clés du profil avec tes pondérations — proximité des
  intérêts ×1, originalité ×2, adapté au profil ×3, ambiance sociale ×4,
  bonus véracité pour les activités vérifiées.
- **Règles** : après 17h30 en semaine / 8h le week-end, budget ≤ 50 €,
  villes à plus de ~30 min exclues (Reims, Troyes, Chaumont…), pas de répétition d'une activité dans la semaine,
  tri au meilleur score, UID stables (chaque mise à jour écrase la précédente).

## Personnaliser

- **Tes intérêts / pondérations** : dictionnaires `MOTS_INTERETS`,
  `MOTS_SOCIAL`, `MOTS_ORIGINALITE` en tête de `build_agenda.py`.
- **Tes adresses fétiches** : ajoute/retire des entrées dans
  `activites_permanentes.json` (jours 0=lundi…6=dimanche, `verify: true`
  ajoute « (À CONFIRMER) » au titre).
- **Heure du cron** : ligne `cron:` du workflow.

## Limites honnêtes

Le scoring est algorithmique (mots-clés), pas intelligent : il ne « comprend »
pas un événement comme le ferait Claude, et il ne remonte que ce qui est
publié dans les flux. Les événements repérés sans horaire précis sont marqués
« (À CONFIRMER) » avec le lien source. Pour un scan intelligent ponctuel,
l'appli HTML de scan intelligent (via Claude) reste complémentaire : elle
génère un `der.ics` que tu peux pousser dans `docs/` par-dessus celui du robot.

## Test local

```bash
pip install requests feedparser beautifulsoup4
python build_agenda.py            # avec collecte web
python build_agenda.py --offline  # uniquement la couche vérifiée
```
