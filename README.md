# Frida — skill Alexa pour Jeedom (Alexa-Hosted)

[Français](#français) · [English](#english)

Skill Alexa qui envoie vos phrases au **plugin Jeedom Alexa** (`alexaapiv2`) et lit la réponse : interactions Jeedom, IA (`ai_assistant`, `mcp_jeedom`). Sur Echo Show, il ouvre aussi votre dashboard Jeedom. Frida n'appelle que l'endpoint vocal du plugin, avec la clé API du plugin : jamais l'API du core ni sa clé.

> **Crédits** — Adaptation de [HomeAssistantAssist](https://github.com/fabianosan/HomeAssistantAssist) de **Fabiano Santos** ([@fabianosan](https://github.com/fabianosan)), version du commit `7dfc40c` (16/10/2025). Le principe (intention unique `{query}` + slot `AMAZON.Person`, écran APL avec bouton, mots de sortie, 14 langues, démarrage par phrase pré-enregistrée — non reprise ici) vient de ce projet.
>
> **Licence** — le dépôt d'origine ne publie **aucune licence** (ni fichier `LICENSE`, ni licence déclarée sur GitHub). Ce projet reprend son principe, avec un code réécrit pour Jeedom, et le crédite ci-dessus. Pour toute remarque de l'auteur d'origine, ouvrez une issue sur ce dépôt.

---

## Français

### Fonctionnement

```
« Alexa, ouvre assistant frida »  →  Lambda Alexa-Hosted  →  POST <jeedom>/plugins/alexaapiv2/core/php/voiceRouter.php
                                                              Authorization: Bearer <clé du plugin Alexa>
« allume la cuisine »              ←  réponse lue          ←  { "reply": "C'est fait", "matched": true }
```

- **Conversation** : « Alexa, ouvre assistant frida », puis enchaînez les demandes ; la session reste ouverte (« Autre chose ? ») jusqu'à un mot de sortie (« non », « merci », « c'est tout »…) ou « stop ».
- **Demande directe** : « Alexa, demande à assistant frida d'allumer la cuisine » ; Alexa répond puis ferme la session (ou la garde ouverte avec `keep_session_open_oneshot=True`, comme l'original).
- **Dashboard** : « ouvre jeedom », « ouvre le tableau de bord »… ouvre le dashboard dans le navigateur de l'Echo Show. À l'ouverture du skill, l'écran affiche aussi un bouton « Ouvrir Jeedom ».
- **Plugin Alexa** : le plugin choisit la voie (interactions, LLM avec le contexte de la maison, MCP en asynchrone) et peut demander « Veux-tu dire… ? » (voir plus bas).
- **Questions des scénarios** : pour qu'un scénario pose une question et attende votre réponse, utilisez le skill `premiumAsk` du plugin Alexa, pas Frida.

### Prérequis

1. Jeedom joignable **depuis Internet en HTTPS avec un certificat valide** (DNS Jeedom, reverse proxy…). La Lambda tourne chez Amazon, pas sur votre réseau.
2. Le **plugin Alexa** (`alexaapiv2`) installé et activé, avec ses réglages de commande vocale (interactions, IA).
3. La **clé API du plugin Alexa** : Réglages → Système → Configuration → API → ligne « Alexa Premium ». N'utilisez jamais la clé API du core : elle donne tous les droits sur Jeedom.

### Installation

**Avec le plugin Alexa (`alexaapiv2`)** : page du plugin → *Skills Alexa* → **Déployer Skill Frida**. Le plugin télécharge ce dépôt, génère `config.py` (URL externe et clé du plugin), puis crée ou met à jour le skill sur votre compte développeur Amazon (code, 13 langues, compilation, activation). Relancez le bouton après chaque mise à jour du dépôt.

**À la main** (sans le plugin) :

1. Dans la [console développeur Alexa](https://developer.amazon.com/alexa/console/ask) : **Create Skill**
   - nom : `Frida` (au choix), langue principale : **French (FR)** ;
   - type d'expérience : *Other* → modèle **Custom** → hébergement **Alexa-hosted (Python)** ;
   - région d'hébergement : **EU (Ireland)** pour l'Europe ;
   - modèle de départ : **Import skill** avec l'URL de ce dépôt (`https://github.com/limad/alexaSkill_Frida.git`), ou **Start from Scratch**.
2. Sur votre PC, copiez `lambda/config.py` en `lambda/config.local.py` (ignoré par git), renseignez-le (voir ci-dessous), puis construisez le paquet :
   ```bash
   python build_zip.py
   ```
   `lambda.zip` contient le dossier `lambda/` attendu par Amazon, avec votre `config.local.py` à la place de `config.py`.
3. Onglet **Code** : **Import Code** → choisissez `lambda.zip`, cochez tous les fichiers → **Import**, puis **Deploy**. (Sans Python : créez les fichiers un par un avec *Create File* et renseignez `config.py` dans l'éditeur.)
4. Onglet **Build** :
   - *Interaction Model* → *JSON Editor* : collez le contenu de `skill-package/interactionModels/custom/fr-FR.json` (une fois par langue ajoutée) ;
   - *Interfaces* : activez **Alexa Presentation Language** et cochez les formats d'écran (Hub Round, Hub Landscape Small/Medium/Large, Hub Portrait, TV Fullscreen, Mobile) ;
   - **Save** puis **Build skill**.
5. Onglet **Test** : passez de *Off* à **Development**, tapez « ouvre assistant frida ».
6. Le skill est actif sur tous les Echo du compte. Pour le retrouver dans l'app Alexa : Plus → Skills et jeux → Vos skills → **Dév.**

### `config.py`

Une ligne par réglage : texte entre guillemets (`JEEDOM_URL = "https://…"`), `True` / `False` sans guillemets. Une faute de frappe (guillemet oublié…) ne fait pas planter le skill : il répond « pas encore configuré ».

| Réglage | Défaut | Rôle |
|---|---|---|
| `JEEDOM_URL` | — (obligatoire) | URL externe de Jeedom, ex. `"https://maison.example.com"` |
| `JEEDOM_APIKEY` | — (obligatoire) | Clé API du plugin Alexa (`alexaapiv2`) |
| `JEEDOM_DASHBOARD` | `"index.php?v=m"` | Page ouverte sur Echo Show : chemin Jeedom (ex. `index.php?v=d&p=plan&plan_id=2&fullscreen=1` pour un design) ou URL complète |
| `JEEDOM_TIMEOUT` | `6.5` | Délai max (s) laissé à Jeedom, plafonné à 7,5 s (limite Alexa : 8 s au total) |
| `VERIFY_SSL` | `True` | Vérifier le certificat HTTPS de Jeedom |
| `KEEP_SESSION_OPEN` | `True` | Garder la session ouverte après une réponse quand le skill a été ouvert (« Alexa, ouvre … ») |
| `KEEP_SESSION_OPEN_ONESHOT` | `False` | Garder aussi la session ouverte après une demande directe (« Alexa, demande à … de … ») : Alexa demande « Autre chose ? » |
| `SUPPRESS_GREETING` | `False` | Ne pas prononcer le message d'accueil à l'ouverture |
| `DEBUG` | `False` | Logs détaillés dans CloudWatch (la clé API n'y apparaît jamais) |

Les textes et mots-clés (ouverture du dashboard, mots de sortie) sont dans `lambda/locale/<langue>.lang`.

### Nom d'appel

Par défaut « **assistant frida** » (fr), « frida assistant » (en), « frida assistent » (de, nl), « asistente frida » (es), « assistente frida » (it, pt). Pour le changer : Build → *Invocations* → *Skill Invocation Name*, puis **Build skill**. Choisissez un nom de deux mots ou plus, facile à prononcer, différent des autres skills activés.

### Plugin Alexa : IA et choix

Frida envoie la phrase à `plugins/alexaapiv2/core/php/voiceRouter.php`, le même point d'entrée que le skill `premiumAsk` :

- le plugin choisit : interactions, LLM avec le contexte de la maison (`ai_assistant`), ou client MCP (`mcp_jeedom`) en asynchrone (« Je m'en occupe », la réponse est lue ensuite sur l'Echo) ; ces réglages se font dans le plugin Alexa ;
- l'identifiant Alexa de l'appareil est envoyé : le plugin le relie à l'Echo (pièce, réponse asynchrone). Ces identifiants sont propres à chaque skill : la liaison se fait d'elle-même au premier usage de Frida sur chaque Echo ;
- quand Jeedom propose un choix (« Veux-tu dire : Lampe salon ? », « 1 : salon, 2 : cuisine »), répondez « oui », « non », ou le numéro (« deux », « le deuxième ») ;
- en cas d'échec (plugin désactivé, clé refusée, délai dépassé), Frida dit pourquoi ; il n'existe pas de repli sur le core.

### Echo Show

- Le navigateur de l'Echo Show affiche la page de connexion Jeedom la première fois : connectez-vous en cochant « Enregistrer cet appareil ».
- `index.php?v=m` (version mobile) est le plus lisible sur petit écran ; un design en `fullscreen=1` convient aux Echo Show 10/15.

### Limites

- **8 secondes** au total côté Alexa : un LLM lent ou un scénario long n'aura pas le temps de répondre (message « Jeedom a mis trop de temps à répondre »). Pour les traitements longs (MCP), activez le mode asynchrone du plugin Alexa.
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
| Appel serveur | `POST /api/conversation/process`, jeton Bearer | Endpoint vocal du plugin Alexa, clé du plugin en en-tête `Authorization` |
| Suivi de conversation | `conversation_id` en **variable globale** de la Lambda : partagé entre utilisateurs et gardé d'une session à l'autre | Géré par le plugin Alexa ; rien de partagé dans la Lambda |
| Écran APL | `is_apl_supported` global, fixé à l'ouverture : un Echo sans écran pouvait recevoir des directives APL après un Echo Show | Détecté à chaque requête, sur l'appareil qui parle |
| Accueil | Message différent « une fois par jour » via une date globale au fuseau UTC−3 codé en dur | Un seul message d'accueil, sans état global |
| Session | `ask_for_further_commands` garde aussi ouvertes les demandes directes | Deux options : `keep_session_open` (après « Alexa, ouvre … », activée) et `keep_session_open_oneshot` (demande directe, désactivée par défaut ; `True` = comportement de l'original) |
| Délai | 7 s fixes, plus 5 s de lecture de l'`input_text` à l'ouverture (jusqu'à 12 s > limite Alexa) | Budget unique < 8 s calculé sur le temps restant de la Lambda, message distinct délai / injoignable / clé refusée |
| Phrase de démarrage | `input_text` HA lue à l'ouverture | Non reprise : les questions des scénarios passent par le skill `premiumAsk` |
| Nettoyage vocal | Supprime `-`, `%`, `€`, accents hors liste (« -5 °C » devenait « 5 °C ») | Garde nombres négatifs et unités, retire HTML, markdown, emojis ; virgule décimale pour de/fr/es/it/nl/pt ; échappement SSML (`&`, `<`) |
| Mots-clés | Recherche de sous-chaîne (« ouvrir le panneau » dans n'importe quelle phrase) | Mot ou expression entière, sans tenir compte des accents ni de la casse |
| Configuration | `debug=False` lu comme vrai ; espaces autour de `=` cassaient la clé ; erreur fatale à l'import si la config manque | `config.py` (format commun aux skills du plugin), booléens lus correctement, faute de frappe → message vocal « skill non configuré » |
| Erreurs HTTP | `int(response.status_code, 0)` levait une exception sur les pages d'erreur HTML | Codes HTTP classés (auth / injoignable / délai / erreur) |
| Intentions | `FallbackIntent` et `NavigateHomeIntent` déclarées sans handler ; `CanFulfillIntentRequest` appelait une méthode inexistante du SDK | Handlers ajoutés ; `CanFulfillIntentRequest` retiré (utile seulement aux skills publiés) |
| IA | Agent de conversation HA (OpenAI, Gemini…) | Plugin Alexa : interactions, LLM via `ai_assistant`, MCP via `mcp_jeedom` |
| Reconnaissance de pièce | `device_id` ajouté à la phrase pour un agent IA | Identifiant d'appareil envoyé au plugin Alexa, qui le relie à l'Echo |
| Tests | Aucun | Tests pytest |
| Langues | 14, dont pt-PT que la plateforme Alexa ne propose pas, et nl-NL avec le nom d'appel espagnol « casa inteligente » | 13 langues Alexa, textes réécrits pour Jeedom, nom d'appel par langue |

---

## English

Alexa skill that sends your sentences to the **Jeedom Alexa plugin** (`alexaapiv2`) and reads the answer aloud: Jeedom interactions, AI (`ai_assistant`, `mcp_jeedom`). On an Echo Show it can also open your Jeedom dashboard. Frida only calls the plugin's voice endpoint, with the plugin API key — never the core API nor its key.

> **Credits** — Adapted from [HomeAssistantAssist](https://github.com/fabianosan/HomeAssistantAssist) by **Fabiano Santos** ([@fabianosan](https://github.com/fabianosan)), commit `7dfc40c`. The original repository has **no license**; this project reuses its concept with code rewritten for Jeedom and credits it above. The original author can reach us through an issue on this repository.

### Requirements

1. Jeedom reachable **from the Internet over HTTPS with a valid certificate**.
2. The **Alexa plugin** (`alexaapiv2`) installed and enabled.
3. The **Alexa plugin API key** (Settings → System → Configuration → API, "Alexa Premium" row). Never use the core API key: it grants full rights.

### Installation

**With the Alexa plugin (`alexaapiv2`)**: plugin page → *Skills Alexa* → **Déployer Skill Frida** (downloads this repository, writes `config.py` with the external URL and the plugin key, creates or updates the skill, builds and enables it).

**Manually**:

1. [Alexa developer console](https://developer.amazon.com/alexa/console/ask) → **Create Skill**: *Other* → **Custom** → **Alexa-hosted (Python)**, hosting region close to you, **Import skill** with this repository's URL, or **Start from Scratch**.
2. Copy `lambda/config.py` to `lambda/config.local.py` (git-ignored), fill it in, run `python build_zip.py`, then in the **Code** tab use **Import Code** with `lambda.zip` and click **Deploy**.
3. **Build** tab: paste `skill-package/interactionModels/custom/<locale>.json` in the *JSON Editor*, enable **Alexa Presentation Language** under *Interfaces* (all screen formats), **Build skill**.
4. **Test** tab: set it to **Development** and type "open frida assistant".
5. The skill works on every Echo of your account (Alexa app → More → Skills & Games → Your Skills → **Dev**).

### `config.py`

One line per setting: text in quotes (`JEEDOM_URL = "https://…"`), `True` / `False` without quotes. A typo (missing quote…) does not crash the skill: it answers "not configured yet".

| Setting | Default | Purpose |
|---|---|---|
| `JEEDOM_URL` | — (required) | External Jeedom URL |
| `JEEDOM_APIKEY` | — (required) | API key of the Alexa plugin (`alexaapiv2`) |
| `JEEDOM_DASHBOARD` | `"index.php?v=m"` | Page opened on Echo Show: Jeedom path or full URL |
| `JEEDOM_TIMEOUT` | `6.5` | Max seconds for Jeedom, capped at 7.5 (Alexa limit: 8 s) |
| `VERIFY_SSL` | `True` | Check Jeedom's HTTPS certificate |
| `KEEP_SESSION_OPEN` | `True` | Keep the session open after an answer when the skill was opened |
| `KEEP_SESSION_OPEN_ONESHOT` | `False` | Also keep it open after a one-shot request ("Alexa, ask … to …"), like the original |
| `SUPPRESS_GREETING` | `False` | Skip the welcome message |
| `DEBUG` | `False` | Verbose CloudWatch logs (the API key is never logged) |

Texts and keywords (open dashboard, exit words) live in `lambda/locale/<locale>.lang`.

### Invocation name

Default: "frida assistant" (en), "assistant frida" (fr), "frida assistent" (de, nl), "asistente frida" (es), "assistente frida" (it, pt). Change it under Build → *Invocations*, then **Build skill**.

### Scenario questions

To have a scenario ask a question and wait for your answer, use the `premiumAsk` skill of the Alexa plugin, not Frida.

### Tests

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

The differences with the original skill are listed in the French section above ("Différences avec HomeAssistantAssist").
