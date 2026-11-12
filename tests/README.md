# 🦁 BraveInstall

**BraveInstall** est un installateur Python avancé, multi-plateforme et autonome pour le navigateur **Brave**.

Il détecte automatiquement votre système d'exploitation, choisit la meilleure méthode d'installation (paquet natif, dépôt officiel, téléchargement direct), applique une configuration post-installation (politiques, raccourcis, moteur de recherche, page d'accueil) et peut lancer Brave immédiatement après l'installation.

---

## ✨ Fonctionnalités

- 🖥️ **Multi-plateforme** : Linux, Windows, macOS
- 🐧 **Linux avancé** : support de `apt`, `dnf`, `yum`, `zypper`, `pacman`/`AUR`, **BlackArch**
- 🪟 **Windows** : téléchargement du setup officiel et installation silencieuse
- 🍎 **macOS** : téléchargement du DMG et copie dans `/Applications`
- 🔍 **Détection automatique** : OS, distribution, architecture, environnement de bureau, WSL
- 🔐 **Vérification** : signatures GPG et checksums SHA-256/SHA-512
- ⚙️ **Configuration** : politiques d'entreprise, moteur de recherche, page d'accueil, télémétrie
- 🚀 **Lancement automatique** de Brave après installation
- 📎 **Création de raccourcis** : bureau Linux, Windows, macOS
- 📝 **Journalisation complète** dans `~/.local/share/braveinstall/logs/`
- 🧪 **Mode dry-run** pour simuler sans rien modifier
- 🌐 **Support proxy** pour les environnements restreints

---

## 📁 Structure du projet

```text
.
├── braveinstall.py      # Script principal (1000+ lignes)
├── requirements.txt     # Dépendances Python
├── README.md            # Ce fichier
├── RESOURCES.md         # Liens officiels et ressources
└── USER_GUIDE.md        # Guide utilisateur détaillé
```

---

## 🚀 Utilisation rapide

### 1. Cloner ou télécharger le projet

```bash
git clone https://github.com/exemple/braveinstall.git
cd braveinstall
```

### 2. Installer les dépendances (optionnel mais recommandé)

```bash
pip install -r requirements.txt
```

### 3. Lancer l'installation

```bash
python braveinstall.py
```

Brave sera installé puis lancé automatiquement.

---

## ⚙️ Options de ligne de commande

| Option | Description |
|--------|-------------|
| `--channel {stable,beta,nightly,dev}` | Canal Brave à installer (défaut : `stable`) |
| `--no-launch` | Ne pas lancer Brave après installation |
| `--no-shortcut` | Ne pas créer de raccourci bureau |
| `--set-default` | Définir Brave comme navigateur par défaut |
| `--policy-file PATH` | Appliquer un fichier de politiques JSON |
| `--dry-run` | Simuler sans modifier le système |
| `--force` | Forcer la réinstallation |
| `--keep-cache` | Conserver les fichiers téléchargés |
| `--skip-signature` | Ignorer la vérification de signature |
| `--proxy URL` | Utiliser un proxy HTTP/HTTPS |
| `--search-engine NAME` | Définir le moteur de recherche par défaut |
| `--homepage URL` | Définir la page d'accueil |
| `--enable-telemetry` | Activer la télémétrie Brave |
| `--extensions ID1 ID2 ...` | IDs d'extensions à pré-installer |
| `--brave-args ARGS ...` | Arguments passés au lancement de Brave |
| `--log-level LEVEL` | Niveau de log : DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `--log-dir PATH` | Dossier des journaux |
| `--info` | Afficher les informations système et quitter |
| `--version` | Afficher la version |
| `-i`, `--interactive` | Mode interactif avec questions `input()` |
| `--no-interactive` | Désactiver le mode interactif par défaut |

### Exemples

```bash
# Installation standard avec lancement automatique
python braveinstall.py

# Simulation sans modification
python braveinstall.py --dry-run --no-launch

# Installer Brave Beta, forcer la réinstallation, utiliser DuckDuckGo
python braveinstall.py --channel beta --force --search-engine duckduckgo

# Installation silencieuse avec proxy
python braveinstall.py --proxy http://proxy.entreprise:8080 --no-launch

# Mode interactif (par défaut)
python braveinstall.py

# Mode non-interactif pour scripts automatisés
python braveinstall.py --no-interactive
```

---

## 🛠️ Méthodes d'installation par plateforme

### Linux

| Distribution | Méthode |
|--------------|---------|
| Debian, Ubuntu, Mint, Pop!_OS, Zorin, Kali | Dépôt APT officiel Brave |
| Fedora, Nobara | Dépôt DNF officiel Brave |
| RHEL, CentOS, Oracle Linux | Dépôt YUM officiel Brave |
| openSUSE | Dépôt Zypper officiel Brave |
| Arch, Manjaro, EndeavourOS, **BlackArch** | `brave-bin` via AUR (`yay` ou `paru`) |
| Solus | `eopkg` (fallback) |

### Windows

Téléchargement du programme d'installation officiel depuis GitHub, puis exécution silencieuse :

```text
BraveBrowserSetup.exe --install --silent --system-level
```

### macOS

Téléchargement du DMG officiel, montage, copie de `Brave Browser.app` dans `/Applications`.

---

## 📜 Licence

Ce projet est sous licence **MIT**.

---

## 🤝 Contributions

Les contributions sont les bienvenues ! Ouvrez une issue ou une pull request sur le dépôt.

---

## 📧 Contact

Auteur : Hackers Tchad
Projet : [github.com/exemple/braveinstall](https://github.com/exemple/braveinstall)
