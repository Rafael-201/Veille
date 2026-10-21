# La Veille

Ma page d'actu perso, en quatre rubriques : **finance, science, spatial, hôtellerie**.
Elle compte aussi une section **Mes sélections** pour les articles que je commente, et une liste **À lire** pour garder un article de côté.

- Les news arrivent toutes seules : chaque matin vers 6-7 h, GitHub relit les flux RSS des sources et republie le site.
- Les articles s'accumulent : chacun reste visible **30 jours** après sa publication, puis disparaît. La recherche fouille donc tout le dernier mois.
- **3 articles maximum par source** à chaque mise à jour, et jamais plus de 3 par source pour un même jour (les plus récents). Réglable en haut de `fetch_feeds.py` (`MAX_PER_FEED`, `MAX_PER_DAY`).
- C'est gratuit : hébergement GitHub Pages, sans nom de domaine. L'adresse a la forme `https://TON-PSEUDO.github.io/veille/`.
- Rien à installer sur ton ordinateur.

---

## Mise en ligne (une seule fois, environ 10 minutes)

### 1. Crée le dépôt
1. Crée un compte gratuit sur [github.com](https://github.com) si tu n'en as pas.
2. En haut à droite, clique sur **+** puis **New repository**.
3. Nom : `veille`. Visibilité : **Public**, car GitHub Pages n'est gratuit que pour les dépôts publics. Clique sur **Create repository**.

### 2. Envoie les fichiers
1. Dans le nouveau dépôt, clique sur **uploading an existing file**.
2. Dézippe `la-veille.zip`, puis glisse dans la page **tous les fichiers** du dossier.
3. Clique sur **Commit changes**.

> ⚠️ Le dossier `.github` est caché sur Mac et souvent sur Windows, et il ne part pas toujours avec le glisser-déposer. Vérifie qu'il est bien présent dans le dépôt. Sinon, crée le fichier à la main :
> **Add file → Create new file**, nom `.github/workflows/update.yml`. Colle dedans le contenu du fichier `workflow-a-copier.yml` (c'est une copie visible du même fichier ; ouvre-le avec un éditeur de texte), puis **Commit changes**. Tu peux ensuite supprimer `workflow-a-copier.yml` du dépôt.

### 3. Active GitHub Pages
1. Va dans **Settings → Pages**.
2. Dans **Build and deployment → Source**, choisis **GitHub Actions**.

### 4. Lance la première mise à jour
1. Va dans l'onglet **Actions**. Si GitHub demande d'activer les workflows, accepte.
2. Clique sur **Mise à jour des news**, puis sur **Run workflow** et confirme avec le bouton vert.
3. Attends environ 1 à 2 minutes, jusqu'à la coche verte.
4. Ton site est en ligne à l'adresse `https://TON-PSEUDO.github.io/veille/`. Le lien s'affiche aussi dans **Settings → Pages**.

Ensuite, tout se fait seul chaque matin. Pour forcer une mise à jour en journée : **Actions → Mise à jour des news → Run workflow**.

---

## Blocs « Transactions » et « Marchés »

- **Hôtellerie → Transactions** : rachats, cessions et portefeuilles d'hôtels, classés par marché (Amérique du Nord, Amérique latine, Europe, Moyen-Orient, Asie-Pacifique, Afrique, International). Alimenté par des recherches Google News par région et par les articles des sources hôtelières qui parlent d'une transaction.
- **Finance → Marchés** : indices à la dernière clôture (Yahoo Finance), avec la variation de la séance et sur un mois, et l'actualité des marchés de chaque région.
- Le classement par région est automatique, à partir des lieux cités dans le titre. Il peut parfois se tromper, par exemple pour un hôtel londonien racheté par un fonds de Dubaï.
- Pour modifier les recherches, les régions ou les indices : `sources.json`, sections `topics`, `regions` et `indices`.

## Résumé « L'essentiel »

Sur la page « À la une », chaque rubrique est résumée en 4 ou 5 points, avec les liens vers les articles. Ce résumé remplace la liste d'articles sur cette page ; les articles complets restent dans chaque rubrique.
Il est écrit chaque matin vers 8 h 45 (heure de Genève) par une tâche planifiée Claude, qui lit `news.json`, écrit `summaries.json` et republie le site.
Si un matin le résumé n'est pas mis à jour, le site affiche le précédent avec sa date.

## Ajouter un article dans « Mes sélections »

1. Dans le dépôt, ouvre `selections.json` et clique sur le crayon ✏️.
2. Ajoute un bloc comme celui-ci. Attention à la **virgule** entre deux blocs :

```json
[
  {
    "title": "Titre de l'article",
    "link": "https://lien-vers-l-article",
    "source": "Les Echos",
    "cat": "finance",
    "date": "2026-10-16",
    "note": "Mon avis en une ou deux phrases."
  },
  {
    "title": "Un autre article",
    "link": "https://...",
    "cat": "spatial",
    "date": "2026-10-17",
    "note": "..."
  }
]
```

- `cat` peut valoir `finance`, `science`, `spatial` ou `hotellerie`.
- `source` est facultatif : sans lui, le nom du site est déduit du lien.
- Supprime le bloc d'exemple fourni au départ.
- Clique sur **Commit changes**. Le site se met à jour en environ une minute.

Astuce : tu peux aussi m'envoyer le lien et ton avis dans Claude, et je te prépare le bloc à coller.

## Ajouter ou retirer une source

Tout se trouve dans `sources.json`, une rubrique par bloc. Pour ajouter un flux, copie une ligne et change `name`, `url` et `lang` (`fr` ou `en`).
`exclude` est facultatif : il écarte les articles dont le titre ou le lien contient l'un des mots indiqués. C'est utile pour filtrer les bons plans et les promos.

## Vérifier que tout marche

- En bas du site, **État des sources** montre chaque flux : point vert s'il est OK, rouge s'il est en panne. Quand une source tombe, ses articles déjà archivés restent affichés.
- Dans l'onglet **Actions** de GitHub, chaque passage apparaît avec une coche verte, ou une croix rouge s'il y a eu un problème. Clique dessus pour voir le détail.

## Bon à savoir

- **« Nouveau »** marque les articles parus depuis ta dernière visite. **Marquer comme vu** remet ce compteur à zéro.
- **À lire** et le thème clair/sombre sont enregistrés **dans ton navigateur** : ils ne se synchronisent pas entre ton téléphone et ton ordinateur.
- Le dépôt est public, donc tes sélections le sont aussi. Le site demande aux moteurs de recherche de ne pas l'indexer, mais toute personne qui a le lien peut le voir.
- GitHub met parfois jusqu'à une heure de retard sur l'horaire prévu. Si les news ne bougent plus du tout, va dans **Actions** : GitHub désactive les tâches planifiées des dépôts sans activité pendant 60 jours, et il suffit alors de cliquer sur **Enable workflow**.
- Si l'étape « Enregistrer les données » échoue avec une erreur de permission : **Settings → Actions → General → Workflow permissions → Read and write permissions**.

## Structure

Tous les fichiers sont à la racine du dépôt :

```
index.html             la page
style.css              le style (couleurs, typographie)
app.js                 l'affichage, la recherche, les filtres
sources.json           la liste des flux RSS
selections.json        mes sélections (à modifier à la main)
news.json              généré automatiquement — ne pas modifier
status.json            généré automatiquement
launches.json          prochains lancements (Launch Library 2), généré automatiquement
markets.json           indices boursiers (Yahoo Finance), généré automatiquement
summaries.json         résumés « L'essentiel », écrits chaque matin par Claude
fetch_feeds.py         le script qui lit les flux
.github/workflows/update.yml   la tâche automatique (chaque matin)
```
