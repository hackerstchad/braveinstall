# Livre / Guide Utilisateur — BraveInstall

## Table des matières
1. Introduction
2. Installation du projet
3. Utilisation de base
4. Options avancées
5. Plateformes supportées
6. Dépannage
7. FAQ
8. Licence et auteurs

## 1. Introduction
`BraveInstall` est un installateur Python avancé pour le navigateur Brave. Il détecte automatiquement votre système d'exploitation, choisit la meilleure méthode d'installation, applique une configuration post-installation et peut lancer Brave à la fin du processus.

## 2. Installation du projet
Clonez le dépôt ou placez-vous dans le dossier contenant `braveinstall.py` :

```bash
pip install -r requirements.txt
```

## 3. Utilisation de base
```bash
python braveinstall.py
```
Cette commande simple détecte votre système et installe Brave si nécessaire, puis le lance.

## 4. Options avancées
- `--dry-run` : simule l'installation sans rien modifier.
- `--force` : force la réinstallation.
- `--set-default` : définit Brave comme navigateur par défaut.
- `--search-engine duckduckgo` : configure le moteur de recherche.
- `--homepage https://example.com` : définit la page d'accueil.
- `--no-launch` : installe sans lancer Brave.
- `--proxy http://proxy:8080` : utilise un proxy pour les téléchargements.

## 5. Plateformes supportées
- Linux : Debian, Ubuntu, Fedora, Arch, openSUSE, etc.
- Windows 10/11 (via le setup officiel ou le zip portable).
- macOS (via DMG officiel).

## 6. Dépannage
- Si `sudo` est requis, le script le demandera automatiquement.
- En cas d'erreur réseau, vérifiez votre connexion ou utilisez `--proxy`.
- Les logs sont stockés dans `~/.local/share/braveinstall/logs/`.

## 7. FAQ
**Q : Puis-je utiliser ce script sans droits administrateur ?**
R : Sous Linux, l'installation native nécessite des droits élevés. Sous Windows et macOS, un compte administrateur est recommandé.

**Q : Le script est-il sûr ?**
R : Il télécharge depuis les sources officielles de Brave et vérifie les signatures lorsque c'est possible.

## 8. Licence et auteurs
- Auteur : Hackers Tchad
- Licence : MIT
