# Frida — skill Alexa pour Jeedom (Alexa-Hosted)

[Français](#français) · [English](#english)

Skill Alexa autonome qui envoie vos phrases aux **interactions Jeedom** (`interact::tryToReply`) et lit la réponse. Sur Echo Show, il ouvre aussi votre dashboard Jeedom. Aucun plugin Jeedom n'est nécessaire : seule l'API JSON-RPC du core est utilisée.

> **Crédits** — Adaptation de [HomeAssistantAssist](https://github.com/fabianosan/HomeAssistantAssist) de **Fabiano Santos** ([@fabianosan](https://github.com/fabianosan)), version du commit `7dfc40c` (16/10/2025). Le principe (intention unique `{query}` + slot `AMAZON.Person`, écran APL avec bouton, mots de sortie, 14 langues, démarrage par phrase pré-enregistrée) vient de ce projet.
>
> **Licence** — le dépôt d'origine ne publie **aucune licence** (ni fichier `LICENSE`, ni licence déclarée sur GitHub). Par défaut, tous les droits restent à son auteur : ce dépôt est donc gardé **privé**, pour un usage personnel. Avant toute publication, demander l'accord de l'auteur (issue sur le dépôt d'origine) ou qu'il ajoute une licence.

---

## Français

### Fonctionnement

```
« Alexa, ouvre assistant frida »  →  Lambda Alexa-Hosted  →  POST <jeedom>/core/api/jeeApi.php
                                                              méthode interact::tryToReply
« allume la cuisine »              ←  réponse lue          ←  { "result": { "reply": "C'est fait" } }
```

- **Conversation** : « Alexa, ouvre assistant frida », puis enchaînez les demandes ; la session reste ouverte (« Autre chose ? ») jusqu'à un mot de sortie (« non », « merci », « c'est tout »…) ou « stop ».
- **Demande directe** : « Alexa, demande à assistant frida d'allumer la cuisine » ; Alexa répond puis ferme la session (ou la garde ouverte avec `keep_session_open_oneshot=True`, comme l'original).
- **Dashboard** : « ouvre jeedom », « ouvre le tableau de bord »… ouvre le dashboard dans le navigateur de l'Echo Show. À l'ouverture du skill, l'écran affiche aussi un bouton « Ouvrir Jeedom ».
- **Contexte** : Jeedom garde le dernier équipement utilisé 5 minutes par profil (« allume le salon » → « et éteins-le ») si les interactions contextuelles sont activées dans Jeedom.
- **Démarrage par Jeedom** : un scénario dépose une phrase dans une variable, puis fait ouvrir le skill ; Alexa traite cette phrase en premier (voir plus bas).

### Prérequis

1. Jeedom joignable **depuis Internet en HTTPS avec un certificat valide** (DNS Jeedom, reverse proxy…). La Lambda tourne chez Amazon, pas sur votre réseau.
2. Des **interactions** Jeedom qui répondent (Outils → Interactions ; testez-les d'abord avec le bouton « Tester »).
3. API JSON-RPC activée : Réglages → Système → Configuration → **API** → « Accès API JSON-RPC » = **Activé** (pas « IP blanche » ni « Localhost » : Amazon appelle depuis ses propres adresses).
4. Une **clé API** :
   - recommandé : la clé d'un **utilisateur dédié** de profil « Utilisateur » (Réglages → Système → Utilisateurs → colonne clé API) ; ses droits limitent ce que le skill peut faire ;
   - ou la clé API du core (Réglages → Système → Configuration → API), qui donne tous les droits.

> Le core Jeedom écrit chaque requête JSON-RPC, clé comprise, dans le log `api` au niveau *info*. Laissez ce log au niveau *error* en production.

### Installation

1. Dans la [console développeur Alexa](https://developer.amazon.com/alexa/console/ask) : **Create Skill**
   - nom : `Frida` (au choix), langue principale : **French (FR)** ;
   - type d'expérience : *Other* → modèle **Custom** → hébergement **Alexa-hosted (Python)** ;
   - région d'hébergement : **EU (Ireland)** pour l'Europe ;
   - modèle de départ : **Start from Scratch** (l'option *Import skill* ne fonctionne qu'avec un dépôt Git public).
2. Sur votre PC, copiez `lambda/config.cfg` en `lambda/config.local.cfg` (ignoré par git), renseignez-le (voir ci-dessous), puis construisez le paquet :
   ```bash
   python build_zip.py
   ```
   `lambda.zip` contient le dossier `lambda/` attendu par Amazon, avec votre `config.local.cfg` à la place de `config.cfg`.
3. Onglet **Code** : **Import Code** → choisissez `lambda.zip`, cochez tous les fichiers → **Import**, puis **Deploy**. (Sans Python : créez les fichiers un par un avec *Create File* et renseignez `config.cfg` dans l'éditeur.)
4. Onglet **Build** :
   - *Interaction Model* → *JSON Editor* : collez le contenu de `skill-package/interactionModels/custom/fr-FR.json` (une fois par langue ajoutée) ;
   - *Interfaces* : activez **Alexa Presentation Language** et cochez les formats d'écran (Hub Round, Hub Landscape Small/Medium/Large, Hub Portrait, TV Fullscreen, Mobile) ;
   - **Save** puis **Build skill**.
5. Onglet **Test** : passez de *Off* à **Development**, tapez « ouvre assistant frida ».
6. Le skill est actif sur tous les Echo du compte. Pour le retrouver dans l'app Alexa : Plus → Skills et jeux → Vos skills → **Dév.**

### `config.cfg`

| Clé | Défaut | Rôle |
|---|---|---|
| `jeedom_url` | — (obligatoire) | URL externe de Jeedom, ex. `https://maison.example.com` |
| `jeedom_apikey` | — (obligatoire) | Clé API (utilisateur dédié recommandé) |
| `jeedom_profile` | vide | Profil passé aux interactions : mémoire de contexte, `#profile#`, restriction « personne » des interactions |
| `jeedom_dashboard` | `index.php?v=m` | Page ouverte sur Echo Show : chemin Jeedom (ex. `index.php?v=d&p=plan&plan_id=2&fullscreen=1` pour un design) ou URL complète |
| `jeedom_prompt_variable` | vide | Nom d'une variable de scénario lue à l'ouverture du skill (vide = désactivé) |
| `jeedom_timeout` | `6.5` | Délai max (s) laissé à Jeedom, plafonné à 7,5 s (limite Alexa : 8 s au total) |
| `verify_ssl` | `True` | Vérifier le certificat HTTPS de Jeedom |
| `keep_session_open` | `True` | Garder la session ouverte après une réponse quand le skill a été ouvert (« Alexa, ouvre … ») |
| `keep_session_open_oneshot` | `False` | Garder aussi la session ouverte après une demande directe (« Alexa, demande à … de … ») : Alexa demande « Autre chose ? » |
| `suppress_greeting` | `False` | Ne pas prononcer le message d'accueil à l'ouverture |
| `debug` | `False` | Logs détaillés dans CloudWatch (la clé API n'y apparaît jamais) |

Les textes et mots-clés (ouverture du dashboard, mots de sortie) sont dans `lambda/locale/<langue>.lang`.

### Nom d'appel

Par défaut « **assistant frida** » (fr), « frida assistant » (en), « frida assistent » (de, nl), « asistente frida » (es), « assistente frida » (it, pt). Pour le changer : Build → *Invocations* → *Skill Invocation Name*, puis **Build skill**. Choisissez un nom de deux mots ou plus, facile à prononcer, différent des autres skills activés.

### Démarrer une conversation depuis Jeedom

1. `config.cfg` : `jeedom_prompt_variable=alexa_prompt`.
2. Dans un scénario : `variable(alexa_prompt, quelle est la température du salon)`, puis faites ouvrir le skill sur l'Echo voulu (par exemple avec une commande « commande vocale » du plugin Alexa : « ouvre assistant frida »).
3. À l'ouverture, le skill lit la variable, la **vide**, envoie la phrase à Jeedom et garde la session ouverte pour la suite.

La remise à vide passe par `datastore::save`, réservée à la clé API du core ou à un utilisateur **administrateur**. Avec une clé « Utilisateur », videz la variable vous-même dans le scénario (par exemple une minute plus tard), sinon la phrase est rejouée à chaque ouverture. La valeur `none` est ignorée, comme dans l'original.

### Echo Show

- Le navigateur de l'Echo Show affiche la page de connexion Jeedom la première fois : connectez-vous en cochant « Enregistrer cet appareil ».
- `index.php?v=m` (version mobile) est le plus lisible sur petit écran ; un design en `fullscreen=1` convient aux Echo Show 10/15.

### Limites

- **8 secondes** au total côté Alexa : les interactions qui appellent un LLM lent ou un scénario long n'auront pas le temps de répondre (message « Jeedom a mis trop de temps à répondre »).
- Le skill reste en mode développement : il n'est utilisable que sur les appareils de votre compte Amazon.

### Tests

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

Les tests n'ont pas besoin du SDK Alexa (stubs dans `tests/conftest.py`). Si `ask-sdk-core` est installé, `tests/test_real_sdk.py` vérifie en plus les réponses JSON produites par le vrai SDK.

### Différences avec HomeAssistantAssist

| Sujet | Original (Home Assistant) | Frida |
|---|---|---|
| Appel serveur | `POST /api/conversation/process`, jeton Bearer | JSON-RPC `interact::tryToReply`, clé API dans le corps |
| Suivi de conversation | `conversation_id` en **variable globale** de la Lambda : partagé entre utilisateurs et gardé d'une session à l'autre | Contexte gardé par Jeedom, par profil (`jeedom_profile`) ; rien de partagé dans la Lambda |
| Écran APL | `is_apl_supported` global, fixé à l'ouverture : un Echo sans écran pouvait recevoir des directives APL après un Echo Show | Détecté à chaque requête, sur l'appareil qui parle |
| Accueil | Message différent « une fois par jour » via une date globale au fuseau UTC−3 codé en dur | Un seul message d'accueil, sans état global |
| Session | `ask_for_further_commands` garde aussi ouvertes les demandes directes | Deux options : `keep_session_open` (après « Alexa, ouvre … », activée) et `keep_session_open_oneshot` (demande directe, désactivée par défaut ; `True` = comportement de l'original) |
| Délai | 7 s fixes, plus 5 s de lecture de l'`input_text` à l'ouverture (jusqu'à 12 s > limite Alexa) | Budget unique < 8 s calculé sur le temps restant de la Lambda, message distinct délai / injoignable / clé refusée |
| Phrase de démarrage | `input_text` HA, non vidée par le skill | Variable de scénario Jeedom, vidée après lecture |
| Nettoyage vocal | Supprime `-`, `%`, `€`, accents hors liste (« -5 °C » devenait « 5 °C ») | Garde nombres négatifs et unités, retire HTML, markdown, emojis ; virgule décimale pour de/fr/es/it/nl/pt ; échappement SSML (`&`, `<`) |
| Mots-clés | Recherche de sous-chaîne (« ouvrir le panneau » dans n'importe quelle phrase) | Mot ou expression entière, sans tenir compte des accents ni de la casse |
| Configuration | `debug=False` lu comme vrai ; espaces autour de `=` cassaient la clé ; erreur fatale à l'import si la config manque | Booléens lus correctement, espaces tolérés, message vocal « skill non configuré » |
| Erreurs HTTP | `int(response.status_code, 0)` levait une exception sur les pages d'erreur HTML | Codes HTTP et JSON-RPC classés (auth / injoignable / délai / erreur) |
| Intentions | `FallbackIntent` et `NavigateHomeIntent` déclarées sans handler ; `CanFulfillIntentRequest` appelait une méthode inexistante du SDK | Handlers ajoutés ; `CanFulfillIntentRequest` retiré (utile seulement aux skills publiés) |
| Reconnaissance de pièce | `device_id` ajouté à la phrase pour un agent IA | Retiré (les interactions Jeedom ne l'exploitent pas) |
| Tests | Aucun | 104 tests pytest |
| Langues | 14 (nl-NL avec le nom d'appel espagnol « casa inteligente ») | Les mêmes 14, textes réécrits pour Jeedom, nom d'appel par langue |

---

## English

Standalone Alexa skill that sends your sentences to **Jeedom interactions** (`interact::tryToReply` over the core JSON-RPC API) and reads the answer aloud. On an Echo Show it can also open your Jeedom dashboard. No Jeedom plugin is required.

> **Credits** — Adapted from [HomeAssistantAssist](https://github.com/fabianosan/HomeAssistantAssist) by **Fabiano Santos** ([@fabianosan](https://github.com/fabianosan)), commit `7dfc40c`. The original repository has **no license**, so all rights remain with its author: this repository is kept **private** for personal use. Ask the author before publishing it.

### Requirements

1. Jeedom reachable **from the Internet over HTTPS with a valid certificate**.
2. Working Jeedom **interactions** (Tools → Interactions).
3. Settings → System → Configuration → **API**: JSON-RPC access **Enabled** (not "white IP" / "localhost").
4. An **API key**: preferably the key of a dedicated Jeedom user with the "User" profile, or the core API key (full rights).

> Jeedom core logs every JSON-RPC request, key included, in the `api` log at *info* level. Keep that log at *error* level.

### Installation

1. [Alexa developer console](https://developer.amazon.com/alexa/console/ask) → **Create Skill**: *Other* → **Custom** → **Alexa-hosted (Python)**, hosting region close to you, **Start from Scratch** (*Import skill* only works with a public Git repository).
2. Copy `lambda/config.cfg` to `lambda/config.local.cfg` (git-ignored), fill it in, run `python build_zip.py`, then in the **Code** tab use **Import Code** with `lambda.zip` and click **Deploy**.
3. **Build** tab: paste `skill-package/interactionModels/custom/<locale>.json` in the *JSON Editor*, enable **Alexa Presentation Language** under *Interfaces* (all screen formats), **Build skill**.
4. **Test** tab: set it to **Development** and type "open frida assistant".
5. The skill works on every Echo of your account (Alexa app → More → Skills & Games → Your Skills → **Dev**).

### `config.cfg`

| Key | Default | Purpose |
|---|---|---|
| `jeedom_url` | — (required) | External Jeedom URL |
| `jeedom_apikey` | — (required) | API key |
| `jeedom_profile` | empty | Profile sent to interactions (context memory, `#profile#`) |
| `jeedom_dashboard` | `index.php?v=m` | Page opened on Echo Show: Jeedom path or full URL |
| `jeedom_prompt_variable` | empty | Scenario variable read (then cleared) when the skill opens |
| `jeedom_timeout` | `6.5` | Max seconds for Jeedom, capped at 7.5 (Alexa limit: 8 s) |
| `verify_ssl` | `True` | Check Jeedom's HTTPS certificate |
| `keep_session_open` | `True` | Keep the session open after an answer when the skill was opened |
| `keep_session_open_oneshot` | `False` | Also keep it open after a one-shot request ("Alexa, ask … to …"), like the original |
| `suppress_greeting` | `False` | Skip the welcome message |
| `debug` | `False` | Verbose CloudWatch logs (the API key is never logged) |

Texts and keywords (open dashboard, exit words) live in `lambda/locale/<locale>.lang`.

### Invocation name

Default: "frida assistant" (en), "assistant frida" (fr), "frida assistent" (de, nl), "asistente frida" (es), "assistente frida" (it, pt). Change it under Build → *Invocations*, then **Build skill**.

### Start a conversation from Jeedom

Set `jeedom_prompt_variable=alexa_prompt`, store a sentence in that variable from a scenario, then make the Echo open the skill. The skill reads the variable, clears it (core API key or admin user required; otherwise clear it in your scenario), sends the sentence to Jeedom and keeps the session open.

### Tests

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

The differences with the original skill are listed in the French section above ("Différences avec HomeAssistantAssist").
