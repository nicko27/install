#!/usr/bin/env python3
"""
Script pour mettre à jour le fichier template_field.py
"""
import re

# Lire le contenu du fichier
with open('/media/nico/Drive/pcUtils/ui/config_screen/template_field.py', 'r') as f:
    content = f.read()

# Modifier la méthode on_mount
on_mount_pattern = r'async def on_mount\(self\) -> None:.*?try:.*?select = self\.query_one.*?select\.on_changed = self\.on_select_changed.*?logger\.debug\(f"Événement \'changed\' enregistré pour le widget Select"\).*?except Exception as e:.*?logger\.error\(f"Erreur lors de l\'enregistrement de l\'événement: \{e\}"\)'
on_mount_replacement = '''async def on_mount(self) -> None:
        """Méthode appelée lorsque le widget est monté"""
        # Récupérer le widget Select et s'abonner à son événement Changed
        try:
            select = self.query_one(f"#{self.select_id}", Select)
            logger.debug(f"Widget Select trouvé avec ID: {self.select_id}")
            
            # Utiliser on_select_changed directement comme gestionnaire d'événement
            select.on_changed = self.on_select_changed
            
            # Utiliser également watch comme méthode alternative pour s'assurer que l'événement est capturé
            self.watch(select, "changed", self._on_select_changed_watch)
            
            logger.debug(f"Événement 'changed' enregistré pour le widget Select avec deux méthodes")
            
            # Afficher les IDs des champs disponibles pour le débogage
            logger.debug(f"Clés disponibles dans fields_by_id: {list(self.fields_by_id.keys())}")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de l'événement: {e}")
            logger.error(f"Détails de l'erreur: {type(e).__name__}: {str(e)}")'''

# Remplacer en utilisant des expressions régulières avec le flag DOTALL pour que le point corresponde aussi aux sauts de ligne
updated_content = re.sub(on_mount_pattern, on_mount_replacement, content, flags=re.DOTALL)

# Écrire le contenu mis à jour dans le fichier
with open('/media/nico/Drive/pcUtils/ui/config_screen/template_field.py', 'w') as f:
    f.write(updated_content)

print("Mise à jour terminée.")
