# Restauration des métadonnées depuis la sauvegarde
        restore_cmd = ['vgcfgrestore', vg_name]
        restore_success, _, restore_stderr = self.run_as_root(restore_cmd)

        if not restore_success:
            self.log_error(f"Échec de la restauration des métadonnées du groupe '{vg_name}': {restore_stderr}")
            return False

        # Réactivation du groupe
        activate_cmd = ['vgchange', '--activate', 'y', vg_name]
        activate_success, _, activate_stderr = self.run_as_root(activate_cmd)

        if not activate_success:
            self.log_error(f"Échec de la réactivation du groupe '{vg_name}': {activate_stderr}")
            return False

        self.log_success(f"Réparation des métadonnées du groupe '{vg_name}' terminée")
        return True

    def migrate_logical_volume(self, vg_name, lv_name, dest_vg=None, new_name=None):
        """
        Migre un volume logique LVM vers un autre groupe ou le renomme.

        Args:
            vg_name: Nom du groupe de volumes source
            lv_name: Nom du volume logique à migrer
            dest_vg: Nom du groupe de volumes destination (optionnel)
            new_name: Nouveau nom pour le volume logique (optionnel)

        Returns:
            bool: True si la migration a réussi, False sinon
        """
        # Vérifier si le volume source existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # Au moins une des options doit être spécifiée
        if not dest_vg and not new_name:
            self.log_error("Vous devez spécifier une destination (dest_vg) ou un nouveau nom (new_name)")
            return False

        # Vérifier le groupe de destination s'il est spécifié
        if dest_vg and not self._check_vg_exists(dest_vg):
            self.log_error(f"Le groupe de volumes destination '{dest_vg}' n'existe pas")
            return False

        # Vérifier si le nom de destination est déjà utilisé
        if new_name and dest_vg and self._check_lv_exists(dest_vg, new_name):
            self.log_error(f"Un volume logique '{new_name}' existe déjà dans le groupe '{dest_vg}'")
            return False
        elif new_name and not dest_vg and self._check_lv_exists(vg_name, new_name):
            self.log_error(f"Un volume logique '{new_name}' existe déjà dans le groupe '{vg_name}'")
            return False

        # Chemin source
        source_path = f"/dev/{vg_name}/{lv_name}"

        # Démonter le volume s'il est monté
        mount_point = None
        if self._is_mounted(source_path):
            mount_point = self._get_mount_point(source_path)
            self.log_info(f"Démontage du volume '{source_path}' de '{mount_point}'")
            umount_cmd = ['umount', source_path]
            umount_success, _, umount_stderr = self.run_as_root(umount_cmd)

            if not umount_success:
                self.log_error(f"Impossible de démonter '{source_path}': {umount_stderr}")
                return False

        if dest_vg and new_name:
            self.log_info(f"Migration du volume '{lv_name}' de '{vg_name}' vers '{dest_vg}/{new_name}'")
            action = "migré et renommé"
            dest_path = f"/dev/{dest_vg}/{new_name}"

            # Approche: créer un snapshot, le convertir en volume normal dans le nouveau groupe
            # 1. Créer un snapshot temporaire
            snapshot_name = f"temp_migrate_{int(time.time())}"
            snap_cmd = ['lvcreate', '--snapshot', '--name', snapshot_name, source_path]
            snap_success, _, snap_stderr = self.run_as_root(snap_cmd)

            if not snap_success:
                self.log_error(f"Échec de la création du snapshot pour migration: {snap_stderr}")
                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', source_path, mount_point]
                    self.run_as_root(mount_cmd)
                return False

            # 2. Créer le volume de destination
            source_info = self._get_lv_info(vg_name, lv_name)
            if not source_info:
                self.log_error("Impossible d'obtenir les informations du volume source")
                return False

            create_cmd = ['lvcreate', '--name', new_name, '--size', source_info['size_raw'], dest_vg]
            create_success, _, create_stderr = self.run_as_root(create_cmd)

            if not create_success:
                self.log_error(f"Échec de la création du volume de destination: {create_stderr}")
                # Supprimer le snapshot
                self.run_as_root(['lvremove', '-f', f"/dev/{vg_name}/{snapshot_name}"])
                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', source_path, mount_point]
                    self.run_as_root(mount_cmd)
                return False

            # 3. Copier les données
            dd_cmd = ['dd', f"if=/dev/{vg_name}/{snapshot_name}", f"of=/dev/{dest_vg}/{new_name}", 'bs=4M', 'conv=noerror']
            dd_success, _, dd_stderr = self.run_as_root(dd_cmd)

            if not dd_success:
                self.log_error(f"Échec de la copie des données: {dd_stderr}")
                # Nettoyage
                self.run_as_root(['lvremove', '-f', f"/dev/{vg_name}/{snapshot_name}"])
                self.run_as_root(['lvremove', '-f', f"/dev/{dest_vg}/{new_name}"])
                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', source_path, mount_point]
                    self.run_as_root(mount_cmd)
                return False

            # 4. Supprimer le snapshot
            self.run_as_root(['lvremove', '-f', f"/dev/{vg_name}/{snapshot_name}"])

        elif dest_vg:
            self.log_info(f"Migration du volume '{lv_name}' de '{vg_name}' vers '{dest_vg}'")
            action = "migré"
            dest_path = f"/dev/{dest_vg}/{lv_name}"

            # Utiliser la même technique que ci-dessus, mais sans changer le nom
            # ...
            new_name = lv_name

            # 1. Créer un snapshot temporaire
            snapshot_name = f"temp_migrate_{int(time.time())}"
            snap_cmd = ['lvcreate', '--snapshot', '--name', snapshot_name, source_path]
            snap_success, _, snap_stderr = self.run_as_root(snap_cmd)

            if not snap_success:
                self.log_error(f"Échec de la création du snapshot pour migration: {snap_stderr}")
                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', source_path, mount_point]
                    self.run_as_root(mount_cmd)
                return False

            # 2. Créer le volume de destination
            source_info = self._get_lv_info(vg_name, lv_name)
            if not source_info:
                self.log_error("Impossible d'obtenir les informations du volume source")
                return False

            create_cmd = ['lvcreate', '--name', lv_name, '--size', source_info['size_raw'], dest_vg]
            create_success, _, create_stderr = self.run_as_root(create_cmd)

            if not create_success:
                self.log_error(f"Échec de la création du volume de destination: {create_stderr}")
                # Supprimer le snapshot
                self.run_as_root(['lvremove', '-f', f"/dev/{vg_name}/{snapshot_name}"])
                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', source_path, mount_point]
                    self.run_as_root(mount_cmd)
                return False

            # 3. Copier les données
            dd_cmd = ['dd', f"if=/dev/{vg_name}/{snapshot_name}", f"of=/dev/{dest_vg}/{lv_name}", 'bs=4M', 'conv=noerror']
            dd_success, _, dd_stderr = self.run_as_root(dd_cmd)

            if not dd_success:
                self.log_error(f"Échec de la copie des données: {dd_stderr}")
                # Nettoyage
                self.run_as_root(['lvremove', '-f', f"/dev/{vg_name}/{snapshot_name}"])
                self.run_as_root(['lvremove', '-f', f"/dev/{dest_vg}/{lv_name}"])
                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', source_path, mount_point]
                    self.run_as_root(mount_cmd)
                return False

            # 4. Supprimer le snapshot
            self.run_as_root(['lvremove', '-f', f"/dev/{vg_name}/{snapshot_name}"])

        elif new_name:
            self.log_info(f"Renommage du volume '{lv_name}' en '{new_name}' dans '{vg_name}'")
            action = "renommé"
            dest_path = f"/dev/{vg_name}/{new_name}"

            # Renommer simplement le volume
            rename_cmd = ['lvrename', vg_name, lv_name, new_name]
            rename_success, _, rename_stderr = self.run_as_root(rename_cmd)

            if not rename_success:
                self.log_error(f"Échec du renommage du volume: {rename_stderr}")
                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', source_path, mount_point]
                    self.run_as_root(mount_cmd)
                return False

        # Mettre à jour les entrées fstab si nécessaire
        if mount_point:
            # Supprimer l'ancienne entrée
            self._remove_fstab_entry(source_path)

            # Ajouter la nouvelle entrée
            fs_type = self._get_fs_type(dest_path)
            mount_options = self._get_mount_options(source_path)

            if fs_type:
                self._add_fstab_entry(dest_path, mount_point, fs_type, mount_options)

                # Remonter le volume
                mount_cmd = ['mount', dest_path, mount_point]
                mount_success, _, mount_stderr = self.run_as_root(mount_cmd)

                if not mount_success:
                    self.log_warning(f"Impossible de remonter le volume: {mount_stderr}")
                    self.log_warning("Vous devrez monter manuellement le volume")
                else:
                    self.log_info(f"Volume remonté avec succès sur '{mount_point}'")

        # Supprimer l'ancien volume si c'était une migration
        if dest_vg:
            remove_cmd = ['lvremove', '-f', source_path]
            remove_success, _, remove_stderr = self.run_as_root(remove_cmd)

            if not remove_success:
                self.log_warning(f"Impossible de supprimer l'ancien volume: {remove_stderr}")
                self.log_warning("Vous devrez supprimer manuellement l'ancien volume")

        self.log_success(f"Volume '{lv_name}' {action} avec succès")
        return True

    def activate_volume_group(self, vg_name, activate=True):
        """
        Active ou désactive un groupe de volumes LVM.

        Args:
            vg_name: Nom du groupe de volumes
            activate: Si True, active le groupe, sinon le désactive

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        if activate:
            self.log_info(f"Activation du groupe de volumes '{vg_name}'")
            cmd = ['vgchange', '--activate', 'y', vg_name]
        else:
            self.log_info(f"Désactivation du groupe de volumes '{vg_name}'")

            # Vérifier si des volumes sont montés
            lvs = self.list_logical_volumes(vg_name)
            mounted_lvs = [lv['name'] for lv in lvs if lv.get('mounted', False)]

            if mounted_lvs:
                self.log_error(f"Les volumes suivants sont encore montés: {', '.join(mounted_lvs)}")
                self.log_error("Veuillez les démonter avant de désactiver le groupe")
                return False

            cmd = ['vgchange', '--activate', 'n', vg_name]

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            if activate:
                self.log_success(f"Groupe de volumes '{vg_name}' activé avec succès")
            else:
                self.log_success(f"Groupe de volumes '{vg_name}' désactivé avec succès")
        else:
            if activate:
                self.log_error(f"Échec de l'activation du groupe de volumes '{vg_name}': {stderr}")
            else:
                self.log_error(f"Échec de la désactivation du groupe de volumes '{vg_name}': {stderr}")

        return success

    def get_thin_pool_usage(self, vg_name, pool_name):
        """
        Obtient les informations d'utilisation d'un pool thin LVM.

        Args:
            vg_name: Nom du groupe de volumes
            pool_name: Nom du pool thin

        Returns:
            dict: Informations sur l'utilisation du pool ou None si erreur
        """
        # Vérifier si le volume existe
        if not self._check_lv_exists(vg_name, pool_name):
            self.log_error(f"Le pool thin '{pool_name}' n'existe pas dans le groupe '{vg_name}'")
            return None

        # Vérifier si c'est un pool thin
        lv_info = self._get_lv_info(vg_name, pool_name)
        if not lv_info or 't' not in lv_info.get('attributes', ''):
            self.log_error(f"Le volume '{pool_name}' n'est pas un pool thin")
            return None

        self.log_info(f"Récupération des informations du pool thin '{pool_name}'")

        cmd = ['lvs', '--noheadings', '--options', 'lv_name,data_percent,metadata_percent,lv_size', '--units', 'b', f"{vg_name}/{pool_name}"]
        success, stdout, stderr = self.run_as_root(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec de la récupération des informations du pool thin: {stderr}")
            return None

        parts = stdout.strip().split()
        if len(parts) >= 4:
            try:
                # Format typique: pool_name data_percent metadata_percent size
                pool_info = {
                    'name': parts[0],
                    'data_percent': float(parts[1]),
                    'metadata_percent': float(parts[2]),
                    'size': self._format_bytes(int(parts[3].rstrip('B'))),
                    'size_bytes': int(parts[3].rstrip('B'))
                }

                # Calcul des valeurs dérivées
                pool_info['data_used'] = self._format_bytes(int(pool_info['size_bytes'] * pool_info['data_percent'] / 100))
                pool_info['data_free'] = self._format_bytes(int(pool_info['size_bytes'] * (100 - pool_info['data_percent']) / 100))

                return pool_info
            except (ValueError, IndexError) as e:
                self.log_error(f"Erreur lors du parsing des informations du pool thin: {str(e)}")
                return None

        self.log_error("Format inattendu dans la sortie de lvs")
        return None

    # ============================
    # === Fonctions auxiliaires ===
    # ============================

    def _check_pv_exists(self, pv_name):
        """
        Vérifie si un volume physique LVM existe.

        Args:
            pv_name: Nom du volume physique

        Returns:
            bool: True si le volume existe, False sinon
        """
        cmd = ['pvs', '--noheadings', pv_name]
        success, _, _ = self.run_as_root(cmd, no_output=True)
        return success

    def _check_vg_exists(self, vg_name):
        """
        Vérifie si un groupe de volumes LVM existe.

        Args:
            vg_name: Nom du groupe de volumes

        Returns:
            bool: True si le groupe existe, False sinon
        """
        cmd = ['vgs', '--noheadings', vg_name]
        success, _, _ = self.run_as_root(cmd, no_output=True)
        return success

    def _check_lv_exists(self, vg_name, lv_name):
        """
        Vérifie si un volume logique LVM existe.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique

        Returns:
            bool: True si le volume existe, False sinon
        """
        cmd = ['lvs', '--noheadings', f"{vg_name}/{lv_name}"]
        success, _, _ = self.run_as_root(cmd, no_output=True)
        return success

    def _get_pv_info(self, pv_name):
        """
        Obtient des informations détaillées sur un volume physique.

        Args:
            pv_name: Nom du volume physique

        Returns:
            dict: Informations sur le volume physique ou None si erreur
        """
        cmd = ['pvs', '--noheadings', '--units', 'b', '-o', 'pv_name,vg_name,pv_size,pv_free,pv_used,pv_attr', pv_name]
        success, stdout, _ = self.run_as_root(cmd, no_output=True)

        if not success:
            return None

        parts = stdout.strip().split()
        if len(parts) >= 6:
            return {
                'name': parts[0],
                'vg_name': parts[1] if parts[1] != "" else None,
                'pv_size': int(parts[2].rstrip('B')),
                'pv_free': int(parts[3].rstrip('B')),
                'pv_used': int(parts[4].rstrip('B')),
                'attributes': parts[5]
            }

        return None

    def _get_vg_info(self, vg_name):
        """
        Obtient des informations détaillées sur un groupe de volumes.

        Args:
            vg_name: Nom du groupe de volumes

        Returns:
            dict: Informations sur le groupe de volumes ou None si erreur
        """
        cmd = ['vgs', '--noheadings', '--units', 'b', '-o', 'vg_name,vg_size,vg_free,vg_extent_count,vg_attr', vg_name]
        success, stdout, _ = self.run_as_root(cmd, no_output=True)

        if not success:
            return None

        parts = stdout.strip().split()
        if len(parts) >= 5:
            return {
                'name': parts[0],
                'vg_size': int(parts[1].rstrip('B')),
                'vg_free': int(parts[2].rstrip('B')),
                'extents': parts[3],
                'attributes': parts[4]
            }

        return None

    def _get_lv_info(self, vg_name, lv_name):
        """
        Obtient des informations détaillées sur un volume logique.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique

        Returns:
            dict: Informations sur le volume logique ou None si erreur
        """
        cmd = ['lvs', '--noheadings', '--units', 'b', '-o', 'lv_name,lv_size,lv_attr,origin', f"{vg_name}/{lv_name}"]
        success, stdout, _ = self.run_as_root(cmd, no_output=True)

        if not success:
            return None

        parts = stdout.strip().split()
        if len(parts) >= 3:
            info = {
                'name': parts[0],
                'size_bytes': int(parts[1].rstrip('B')),
                'size_raw': parts[1],
                'attributes': parts[2]
            }

            # Ajouter l'origine si c'est un snapshot
            if len(parts) >= 4 and parts[3] != "":
                info['origin'] = parts[3]

            return info

        return None

    def _is_mounted(self, device):
        """
        Vérifie si un périphérique est monté.

        Args:
            device: Chemin du périphérique

        Returns:
            bool: True si le périphérique est monté, False sinon
        """
        cmd = ['mount']
        success, stdout, _ = self.run(cmd, no_output=True)

        if not success:
            return False

        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == device:
                return True

        return False

    def _get_mount_point(self, device):
        """
        Obtient le point de montage d'un périphérique.

        Args:
            device: Chemin du périphérique

        Returns:
            str: Point de montage ou None si non monté
        """
        cmd = ['mount']
        success, stdout, _ = self.run(cmd, no_output=True)

        if not success:
            return None

        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == device:
                return parts[2]

        return None

    def _get_mount_options(self, device):
        """
        Obtient les options de montage d'un périphérique.

        Args:
            device: Chemin du périphérique

        Returns:
            str: Options de montage ou None si non monté
        """
        cmd = ['mount']
        success, stdout, _ = self.run(cmd, no_output=True)

        if not success:
            return None

        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 6 and parts[0] == device:
                # Format: device on mountpoint type filesystem (options)
                options = parts[5]
                if options.startswith('(') and options.endswith(')'):
                    return options[1:-1]
                return options

        return None

    def _get_fs_type(self, device):
        """
        Obtient le type de système de fichiers d'un périphérique.

        Args:
            device: Chemin du périphérique

        Returns:
            str: Type de système de fichiers ou None si non détecté
        """
        cmd = ['blkid', '-o', 'value', '-s', 'TYPE', device]
        success, stdout, _ = self.run_as_root(cmd, no_output=True)

        if success and stdout.strip():
            return stdout.strip()

        # Alternative avec file si blkid ne fonctionne pas
        cmd = ['file', '-s', device]
        success, stdout, _ = self.run(cmd, no_output=True)

        if success:
            if 'ext4' in stdout:
                return 'ext4'
            elif 'ext3' in stdout:
                return 'ext3'
            elif 'ext2' in stdout:
                return 'ext2'
            elif 'XFS' in stdout:
                return 'xfs'
            elif 'swap' in stdout:
                return 'swap'

        return None

    def _add_fstab_entry(self, device, mount_point, fs_type, options=None):
        """
        Ajoute une entrée dans /etc/fstab pour un montage persistant.

        Args:
            device: Chemin du périphérique
            mount_point: Point de montage
            fs_type: Type de système de fichiers
            options: Options de montage (optionnel)

        Returns:
            bool: True si l'ajout a réussi, False sinon
        """
        if not options:
            options = "defaults"

        # Vérifier si l'entrée existe déjà
        fstab_path = "/etc/fstab"
        cmd = ['grep', '-q', device, fstab_path]
        entry_exists = self.run(cmd, no_output=True)[0]

        if entry_exists:
            self.log_info(f"Une entrée pour {device} existe déjà dans {fstab_path}")
            return True

        # Ajouter l'entrée
        entry = f"{device} {mount_point} {fs_type} {options} 0 2"
        cmd = ['bash', '-c', f"echo '{entry}' >> {fstab_path}"]
        success, _, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Entrée ajoutée dans {fstab_path} pour {device}")
            return True
        else:
            self.log_error(f"Échec de l'ajout de l'entrée dans {fstab_path}: {stderr}")
            return False

    def _remove_fstab_entry(self, device):
        """
        Supprime une entrée dans /etc/fstab.

        Args:
            device: Chemin du périphérique

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        fstab_path = "/etc/fstab"

        # Vérifier si l'entrée existe
        cmd = ['grep', '-q', device, fstab_path]
        entry_exists = self.run(cmd, no_output=True)[0]

        if not entry_exists:
            self.log_info(f"Aucune entrée pour {device} dans {fstab_path}")
            return True

        # Créer un fichier temporaire sans l'entrée
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name

            # Lire fstab et exclure l'entrée
            cmd = ['grep', '-v', device, fstab_path]
            success, stdout, _ = self.run(cmd, no_output=True)

            if success:
                temp_file.write(stdout)

        # Remplacer fstab par le fichier temporaire
        cmd = ['mv', temp_path, fstab_path]
        success, _, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Entrée pour {device} supprimée de {fstab_path}")
            return True
        else:
            self.log_error(f"Échec de la suppression de l'entrée de {fstab_path}: {stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False

    def _convert_size_to_bytes(self, size_str):
        """
        Convertit une taille en chaîne (ex: '5G', '500M') en octets.

        Args:
            size_str: Chaîne représentant une taille

        Returns:
            int: Taille en octets ou None si format invalide
        """
        if not size_str:
            return None

        size_str = str(size_str).upper()

        # Motif pour les unités: 5G, 500M, 1T, etc.
        match = re.match(r'^(\d+(?:\.\d+)?)([KMGT])?B?    def create_logical_volume(self, vg_name, lv_name, size, filesystem=None, mount_point=None, mount_options=None):
        """
        Crée un nouveau volume logique LVM.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à créer
            size: Taille du volume (ex: '5G', '500M')
            filesystem: Système de fichiers à créer (ex: 'ext4', 'xfs')
            mount_point: Point de montage (optionnel)
            mount_options: Options de montage (optionnel)

        Returns:
            bool: True si la création a réussi, False sinon
        """
        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier si le volume logique existe déjà
        if self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' existe déjà dans le groupe '{vg_name}'")
            return False

        # Vérifier si le groupe a assez d'espace
        vg_info = self._get_vg_info(vg_name)
        if not vg_info:
            self.log_error(f"Impossible d'obtenir les informations sur le groupe '{vg_name}'")
            return False

        # Convertir la taille en octets pour comparaison
        size_bytes = self._convert_size_to_bytes(size)
        if size_bytes > vg_info.get('vg_free', 0):
            self.log_error(f"Espace insuffisant dans le groupe '{vg_name}' pour créer un volume de {size}")
            self.log_error(f"Espace disponible: {self._format_bytes(vg_info.get('vg_free', 0))}")
            return False

        self.log_info(f"Création du volume logique '{lv_name}' de taille {size} dans le groupe '{vg_name}'")

        # Créer le volume logique
        cmd = ['lvcreate', '--name', lv_name, '--size', size, vg_name]
        success, stdout, stderr = self.run_as_root(cmd)

        if not success:
            self.log_error(f"Échec de la création du volume logique '{lv_name}': {stderr}")
            return False

        self.log_success(f"Volume logique '{lv_name}' créé avec succès")

        # Chemin complet du volume
        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Créer un système de fichiers si demandé
        if filesystem:
            self.log_info(f"Création du système de fichiers {filesystem} sur '{lv_path}'")

            format_cmd = ['mkfs', '-t', filesystem]

            # Options spécifiques selon le système de fichiers
            if filesystem == 'ext4':
                format_cmd.extend(['-F', lv_path])
            elif filesystem == 'xfs':
                format_cmd.extend(['-f', lv_path])
            else:
                format_cmd.append(lv_path)

            format_success, _, format_stderr = self.run_as_root(format_cmd)

            if not format_success:
                self.log_error(f"Échec de la création du système de fichiers {filesystem} sur '{lv_path}': {format_stderr}")
                return False

            self.log_success(f"Système de fichiers {filesystem} créé avec succès sur '{lv_path}'")

        # Monter le volume si un point de montage est spécifié
        if mount_point:
            # Créer le point de montage s'il n'existe pas
            if not os.path.exists(mount_point):
                mkdir_cmd = ['mkdir', '-p', mount_point]
                self.run_as_root(mkdir_cmd)

            # Monter le volume
            self.log_info(f"Montage de '{lv_path}' sur '{mount_point}'")

            mount_cmd = ['mount']
            if mount_options:
                mount_cmd.extend(['-o', mount_options])
            mount_cmd.extend([lv_path, mount_point])

            mount_success, _, mount_stderr = self.run_as_root(mount_cmd)

            if not mount_success:
                self.log_error(f"Échec du montage de '{lv_path}' sur '{mount_point}': {mount_stderr}")
                return False

            self.log_success(f"Volume '{lv_path}' monté avec succès sur '{mount_point}'")

            # Ajouter au fstab pour montage persistant
            self._add_fstab_entry(lv_path, mount_point, filesystem, mount_options)

        return True

    def extend_logical_volume(self, vg_name, lv_name, additional_size, resize_fs=True):
        """
        Étend un volume logique LVM existant.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à étendre
            additional_size: Taille supplémentaire (ex: '+5G', '+500M')
            resize_fs: Si True, redimensionne aussi le système de fichiers

        Returns:
            bool: True si l'extension a réussi, False sinon
        """
        # Vérifier si le volume existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # S'assurer que la taille supplémentaire commence par '+'
        if not additional_size.startswith('+'):
            additional_size = '+' + additional_size

        # Vérifier si le groupe a assez d'espace
        vg_info = self._get_vg_info(vg_name)
        if not vg_info:
            self.log_error(f"Impossible d'obtenir les informations sur le groupe '{vg_name}'")
            return False

        # Convertir la taille en octets pour comparaison
        size_bytes = self._convert_size_to_bytes(additional_size[1:])  # Enlever le '+'
        if size_bytes > vg_info.get('vg_free', 0):
            self.log_error(f"Espace insuffisant dans le groupe '{vg_name}' pour étendre le volume de {additional_size}")
            self.log_error(f"Espace disponible: {self._format_bytes(vg_info.get('vg_free', 0))}")
            return False

        self.log_info(f"Extension du volume logique '{lv_name}' de {additional_size}")

        # Chemin complet du volume
        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Étendre le volume logique
        cmd = ['lvextend', '--size', additional_size]

        if resize_fs:
            cmd.append('--resizefs')

        cmd.append(lv_path)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume logique '{lv_name}' étendu avec succès")
        else:
            self.log_error(f"Échec de l'extension du volume logique '{lv_name}': {stderr}")

        return success

    def reduce_logical_volume(self, vg_name, lv_name, size_reduction, resize_fs=True, force=False):
        """
        Réduit la taille d'un volume logique LVM.
        ATTENTION: Cette opération est risquée et peut entraîner une perte de données.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à réduire
            size_reduction: Réduction de taille (ex: '-2G', '-500M')
            resize_fs: Si True, redimensionne aussi le système de fichiers
            force: Si True, force la réduction même en cas d'avertissements

        Returns:
            bool: True si la réduction a réussi, False sinon
        """
        # Vérifier si le volume existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # S'assurer que la taille de réduction commence par '-'
        if not size_reduction.startswith('-'):
            size_reduction = '-' + size_reduction

        self.log_warning(f"Réduction du volume logique '{lv_name}' de {size_reduction}. Cette opération est risquée!")

        # Chemin complet du volume
        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Vérifier le système de fichiers
        fs_type = self._get_fs_type(lv_path)

        if fs_type and resize_fs:
            # Réduire le système de fichiers d'abord pour ext4
            if 'ext' in fs_type.lower():
                # Démonter si nécessaire
                is_mounted = self._is_mounted(lv_path)
                mount_point = None

                if is_mounted:
                    mount_point = self._get_mount_point(lv_path)
                    umount_cmd = ['umount', lv_path]
                    umount_success, _, _ = self.run_as_root(umount_cmd)

                    if not umount_success:
                        self.log_error(f"Impossible de démonter '{lv_path}' pour redimensionner le système de fichiers")
                        return False

                # Vérifier le système de fichiers
                fsck_cmd = ['e2fsck', '-f', lv_path]
                self.run_as_root(fsck_cmd)

                # Obtenir la nouvelle taille en blocs
                # Pour cela, nous devons connaître la taille actuelle et soustraire la réduction
                lvs_cmd = ['lvdisplay', '--units', 'B', lv_path]
                lvs_success, lvs_stdout, _ = self.run_as_root(lvs_cmd, no_output=True)

                current_size_bytes = None
                if lvs_success:
                    for line in lvs_stdout.splitlines():
                        if "LV Size" in line:
                            size_match = re.search(r'(\d+) B', line)
                            if size_match:
                                current_size_bytes = int(size_match.group(1))
                                break

                if not current_size_bytes:
                    self.log_error("Impossible de déterminer la taille actuelle du volume")
                    return False

                # Convertir la réduction en octets
                reduction_bytes = self._convert_size_to_bytes(size_reduction[1:])  # Enlever le '-'
                new_size_bytes = current_size_bytes - reduction_bytes

                # Réduire le système de fichiers (la taille doit être en blocs de 4K pour resize2fs)
                block_size = 4096  # Taille de bloc standard pour ext4
                new_size_blocks = new_size_bytes // block_size

                resize_cmd = ['resize2fs', lv_path, str(new_size_blocks) + 'K']
                resize_success, _, resize_stderr = self.run_as_root(resize_cmd)

                if not resize_success:
                    self.log_error(f"Échec du redimensionnement du système de fichiers: {resize_stderr}")

                    # Remonter si nécessaire
                    if mount_point:
                        mount_cmd = ['mount', lv_path, mount_point]
                        self.run_as_root(mount_cmd)

                    return False

                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', lv_path, mount_point]
                    self.run_as_root(mount_cmd)

        # Réduire le volume logique
        cmd = ['lvreduce']

        if force:
            cmd.append('--force')

        cmd.extend(['--size', size_reduction, lv_path])

        if not resize_fs:
            # Demander confirmation
            self.log_warning("ATTENTION: Vous avez choisi de ne pas redimensionner le système de fichiers.")
            self.log_warning("Cela peut entraîner une corruption des données si le système de fichiers est plus grand que le volume.")

            if not force:
                self.log_error("Opération annulée pour sécurité. Utilisez force=True pour forcer la réduction.")
                return False

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume logique '{lv_name}' réduit avec succès")
        else:
            self.log_error(f"Échec de la réduction du volume logique '{lv_name}': {stderr}")

        return success

    def remove_logical_volume(self, vg_name, lv_name, force=False):
        """
        Supprime un volume logique LVM.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à supprimer
            force: Si True, force la suppression même si le volume est utilisé

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        # Vérifier si le volume existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Démonter le volume s'il est monté
        if self._is_mounted(lv_path):
            self.log_info(f"Démontage du volume '{lv_path}'")
            umount_cmd = ['umount', lv_path]
            umount_success, _, umount_stderr = self.run_as_root(umount_cmd)

            if not umount_success and not force:
                self.log_error(f"Impossible de démonter '{lv_path}': {umount_stderr}")
                return False

            # Supprimer les entrées fstab
            self._remove_fstab_entry(lv_path)

        self.log_info(f"Suppression du volume logique '{lv_name}' du groupe '{vg_name}'")

        cmd = ['lvremove']

        if force:
            cmd.extend(['--force', '--yes'])

        cmd.append(lv_path)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume logique '{lv_name}' supprimé avec succès")
        else:
            self.log_error(f"Échec de la suppression du volume logique '{lv_name}': {stderr}")

        return success

    def create_snapshot(self, vg_name, lv_name, snapshot_name, size='5G', merge_on_close=False):
        """
        Crée un instantané d'un volume logique LVM.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique source
            snapshot_name: Nom du snapshot à créer
            size: Taille de l'espace pour les modifications (ex: '5G')
            merge_on_close: Si True, configure pour fusionner au prochain redémarrage

        Returns:
            bool: True si la création du snapshot a réussi, False sinon
        """
        # Vérifier si le volume source existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique source '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # Vérifier si le snapshot existe déjà
        if self._check_lv_exists(vg_name, snapshot_name):
            self.log_error(f"Un volume logique '{snapshot_name}' existe déjà dans le groupe '{vg_name}'")
            return False

        # Vérifier si le groupe a assez d'espace
        vg_info = self._get_vg_info(vg_name)
        if not vg_info:
            self.log_error(f"Impossible d'obtenir les informations sur le groupe '{vg_name}'")
            return False

        # Convertir la taille en octets pour comparaison
        size_bytes = self._convert_size_to_bytes(size)
        if size_bytes > vg_info.get('vg_free', 0):
            self.log_error(f"Espace insuffisant dans le groupe '{vg_name}' pour créer un snapshot de {size}")
            self.log_error(f"Espace disponible: {self._format_bytes(vg_info.get('vg_free', 0))}")
            return False

        self.log_info(f"Création d'un snapshot '{snapshot_name}' du volume '{lv_name}' avec taille {size}")

        cmd = ['lvcreate', '--snapshot', '--name', snapshot_name, '--size', size, f"/dev/{vg_name}/{lv_name}"]
        success, stdout, stderr = self.run_as_root(cmd)

        if not success:
            self.log_error(f"Échec de la création du snapshot '{snapshot_name}': {stderr}")
            return False

        self.log_success(f"Snapshot '{snapshot_name}' créé avec succès")

        # Configurer la fusion automatique si demandé
        if merge_on_close:
            self.log_info(f"Configuration du snapshot '{snapshot_name}' pour fusion au prochain redémarrage")
            merge_cmd = ['lvchange', '--merge', f"/dev/{vg_name}/{snapshot_name}"]
            merge_success, _, merge_stderr = self.run_as_root(merge_cmd)

            if not merge_success:
                self.log_error(f"Échec de la configuration de fusion pour '{snapshot_name}': {merge_stderr}")
                return False

            self.log_success(f"Snapshot '{snapshot_name}' configuré pour fusion au prochain redémarrage")

        return True

    def merge_snapshot(self, vg_name, snapshot_name, activate=True):
        """
        Fusionne un snapshot avec son volume source.

        Args:
            vg_name: Nom du groupe de volumes
            snapshot_name: Nom du snapshot à fusionner
            activate: Si True, active la fusion immédiatement si possible

        Returns:
            bool: True si la fusion a démarré avec succès, False sinon
        """
        # Vérifier si le snapshot existe
        if not self._check_lv_exists(vg_name, snapshot_name):
            self.log_error(f"Le snapshot '{snapshot_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # Vérifier si c'est un snapshot
        lv_info = self._get_lv_info(vg_name, snapshot_name)
        if not lv_info or 's' not in lv_info.get('attributes', ''):
            self.log_error(f"Le volume '{snapshot_name}' n'est pas un snapshot")
            return False

        self.log_info(f"Configuration du snapshot '{snapshot_name}' pour fusion")

        # Configurer la fusion
        merge_cmd = ['lvchange', '--merge', f"/dev/{vg_name}/{snapshot_name}"]
        merge_success, _, merge_stderr = self.run_as_root(merge_cmd)

        if not merge_success:
            self.log_error(f"Échec de la configuration de fusion pour '{snapshot_name}': {merge_stderr}")
            return False

        self.log_success(f"Snapshot '{snapshot_name}' configuré pour fusion")

        # Activer la fusion maintenant si demandé et possible
        if activate:
            self.log_info("Tentative d'activation de la fusion immédiatement")

            # Pour activer la fusion immédiatement, il faut désactiver puis réactiver le VG
            # Vérifier d'abord si le volume source est monté
            origin_name = None

            for line in lv_info.get('origin', '').splitlines():
                if line.strip():
                    origin_name = line.strip()
                    break

            if origin_name and self._is_mounted(f"/dev/{vg_name}/{origin_name}"):
                self.log_warning(f"Le volume source '{origin_name}' est monté, la fusion sera effectuée au prochain redémarrage")
                return True

            # Désactiver le groupe
            self.log_info(f"Désactivation du groupe '{vg_name}' pour préparer la fusion")
            deact_cmd = ['vgchange', '-an', vg_name]
            deact_success, _, _ = self.run_as_root(deact_cmd)

            if not deact_success:
                self.log_warning("Impossible de désactiver le groupe, la fusion sera effectuée au prochain redémarrage")
                return True

            # Réactiver le groupe
            self.log_info(f"Réactivation du groupe '{vg_name}' pour finaliser la fusion")
            act_cmd = ['vgchange', '-ay', vg_name]
            act_success, _, _ = self.run_as_root(act_cmd)

            if not act_success:
                self.log_warning("Impossible de réactiver le groupe, la fusion sera effectuée au prochain redémarrage")
                # Tenter de réactiver quand même
                self.run_as_root(['vgchange', '-ay', vg_name])
                return True

            self.log_success("Fusion du snapshot activée avec succès")
        else:
            self.log_info("La fusion sera effectuée au prochain redémarrage")

        return True

    def list_volume_groups(self):
        """
        Liste tous les groupes de volumes LVM disponibles.

        Returns:
            list: Liste de dictionnaires avec les informations des groupes de volumes
        """
        self.log_info("Listage des groupes de volumes LVM")

        cmd = ['vgs', '--noheadings', '--options', 'vg_name,vg_size,vg_free,vg_extent_count,vg_attr', '--units', 'b']
        success, stdout, stderr = self.run_as_root(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec du listage des groupes de volumes: {stderr}")
            return []

        vgs = []
        for line in stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                vg = {
                    'name': parts[0],
                    'size': self._format_bytes(int(parts[1].rstrip('B'))),
                    'size_bytes': int(parts[1].rstrip('B')),
                    'free': self._format_bytes(int(parts[2].rstrip('B'))),
                    'free_bytes': int(parts[2].rstrip('B')),
                    'extents': parts[3],
                    'attributes': parts[4]
                }
                vgs.append(vg)

        self.log_info(f"Trouvé {len(vgs)} groupe(s) de volumes")
        return vgs

    def list_physical_volumes(self, vg_name=None):
        """
        Liste tous les volumes physiques LVM disponibles.

        Args:
            vg_name: Nom du groupe de volumes à filtrer (optionnel)

        Returns:
            list: Liste de dictionnaires avec les informations des volumes physiques
        """
        if vg_name:
            self.log_info(f"Listage des volumes physiques dans le groupe '{vg_name}'")
        else:
            self.log_info("Listage de tous les volumes physiques LVM")

        cmd = ['pvs', '--noheadings', '--options', 'pv_name,vg_name,pv_size,pv_free,pv_attr', '--units', 'b']

        if vg_name:
            cmd.append(vg_name)

        success, stdout, stderr = self.run_as_root(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec du listage des volumes physiques: {stderr}")
            return []

        pvs = []
        for line in stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                pv = {
                    'name': parts[0],
                    'vg_name': parts[1] if parts[1] != "" else None,
                    'size': self._format_bytes(int(parts[2].rstrip('B'))),
                    'size_bytes': int(parts[2].rstrip('B')),
                    'free': self._format_bytes(int(parts[3].rstrip('B'))),
                    'free_bytes': int(parts[3].rstrip('B')),
                    'attributes': parts[4]
                }
                pvs.append(pv)

        if vg_name:
            self.log_info(f"Trouvé {len(pvs)} volume(s) physique(s) dans le groupe '{vg_name}'")
        else:
            self.log_info(f"Trouvé {len(pvs)} volume(s) physique(s) au total")

        return pvs

    def list_logical_volumes(self, vg_name=None):
        """
        Liste tous les volumes logiques LVM disponibles.

        Args:
            vg_name: Nom du groupe de volumes à filtrer (optionnel)

        Returns:
            list: Liste de dictionnaires avec les informations des volumes logiques
        """
        if vg_name:
            self.log_info(f"Listage des volumes logiques dans le groupe '{vg_name}'")
        else:
            self.log_info("Listage de tous les volumes logiques LVM")

        cmd = ['lvs', '--noheadings', '--options', 'vg_name,lv_name,lv_size,lv_attr,lv_path,origin', '--units', 'b']

        if vg_name:
            cmd.append(vg_name)

        success, stdout, stderr = self.run_as_root(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec du listage des volumes logiques: {stderr}")
            return []

        lvs = []
        for line in stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                lv = {
                    'vg_name': parts[0],
                    'name': parts[1],
                    'size': self._format_bytes(int(parts[2].rstrip('B'))),
                    'size_bytes': int(parts[2].rstrip('B')),
                    'attributes': parts[3],
                    'path': parts[4]
                }

                # Déterminer si c'est un snapshot
                if 's' in lv['attributes']:
                    lv['is_snapshot'] = True
                    if len(parts) >= 6:
                        lv['origin'] = parts[5]
                else:
                    lv['is_snapshot'] = False

                # Vérifier si le volume est monté
                lv['mounted'] = self._is_mounted(lv['path'])
                if lv['mounted']:
                    lv['mount_point'] = self._get_mount_point(lv['path'])

                lvs.append(lv)

        if vg_name:
            self.log_info(f"Trouvé {len(lvs)} volume(s) logique(s) dans le groupe '{vg_name}'")
        else:
            self.log_info(f"Trouvé {len(lvs)} volume(s) logique(s) au total")

        return lvs

    def repair_volume_group_metadata(self, vg_name):
        """
        Tente de réparer les métadonnées LVM d'un groupe de volumes.

        Args:
            vg_name: Nom du groupe de volumes à réparer

        Returns:
            bool: True si la réparation a réussi, False sinon
        """
        self.log_warning(f"Tentative de réparation des métadonnées du groupe '{vg_name}'")

        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas ou n'est pas accessible")
            return False

        # Sauvegarde des métadonnées
        backup_cmd = ['vgcfgbackup', vg_name]
        backup_success, _, backup_stderr = self.run_as_root(backup_cmd)

        if not backup_success:
            self.log_warning(f"Impossible de sauvegarder les métadonnées du groupe '{vg_name}': {backup_stderr}")

        # Vérification des métadonnées
        check_cmd = ['vgck', vg_name]
        check_success, _, check_stderr = self.run_as_root(check_cmd)

        if check_success:
            self.log_info(f"Les métadonnées du groupe '{vg_name}' semblent intactes")
        else:
            self.log_warning(f"Des problèmes détectés dans les métadonnées du groupe '{vg_name}': {check_stderr}")

        # Restauration des métadonnées depuis la sauv#!/usr/bin/env python3
"""
Module utilitaire pour la gestion avancée des volumes logiques LVM.
Permet de créer, modifier, supprimer et gérer des groupes de volumes,
volumes logiques et snapshots LVM.
"""

from .commands import Commands
import os
import re
import time
import json
import tempfile


class LvmCommands(Commands):
    """
    Classe pour gérer les volumes logiques LVM.
    Hérite de la classe Commands pour la gestion des commandes système.
    """

    def create_physical_volume(self, devices):
        """
        Initialise un ou plusieurs périphériques comme volumes physiques LVM.

        Args:
            devices: Périphérique ou liste de périphériques à initialiser

        Returns:
            bool: True si l'initialisation a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(devices, str):
            devices = [devices]

        if not devices:
            self.log_error("Aucun périphérique spécifié")
            return False

        # Vérifier si les périphériques existent
        missing_devices = []
        for device in devices:
            if not os.path.exists(device):
                missing_devices.append(device)

        if missing_devices:
            self.log_error(f"Les périphériques suivants n'existent pas: {', '.join(missing_devices)}")
            return False

        self.log_info(f"Initialisation de {len(devices)} périphérique(s) comme volumes physiques LVM")

        # Initialiser les volumes physiques
        cmd = ['pvcreate', '--yes']
        cmd.extend(devices)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volumes physiques créés avec succès: {', '.join(devices)}")
            return True
        else:
            self.log_error(f"Échec de la création des volumes physiques: {stderr}")
            return False

    def remove_physical_volume(self, pv_name):
        """
        Supprime un volume physique LVM.

        Args:
            pv_name: Nom du volume physique à supprimer

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        # Vérifier si le volume physique existe
        if not self._check_pv_exists(pv_name):
            self.log_error(f"Le volume physique {pv_name} n'existe pas")
            return False

        # Vérifier si le volume physique est utilisé par un groupe de volumes
        pv_info = self._get_pv_info(pv_name)
        if pv_info and pv_info.get('vg_name') and pv_info.get('vg_name') != '':
            self.log_error(f"Le volume physique {pv_name} est utilisé par le groupe de volumes {pv_info.get('vg_name')}")
            return False

        self.log_info(f"Suppression du volume physique {pv_name}")

        # Supprimer le volume physique
        cmd = ['pvremove', '--yes', pv_name]
        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume physique {pv_name} supprimé avec succès")
            return True
        else:
            self.log_error(f"Échec de la suppression du volume physique {pv_name}: {stderr}")
            return False

    def create_volume_group(self, vg_name, pv_names, force=False, cluster=False):
        """
        Crée un nouveau groupe de volumes LVM.

        Args:
            vg_name: Nom du groupe de volumes
            pv_names: Périphérique ou liste de périphériques à inclure dans le VG
            force: Si True, force la création même si des warnings sont détectés
            cluster: Si True, active le mode cluster

        Returns:
            bool: True si la création a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(pv_names, str):
            pv_names = [pv_names]

        if not pv_names:
            self.log_error("Aucun volume physique spécifié pour le groupe de volumes")
            return False

        # Vérifier si les volumes physiques existent
        missing_pvs = []
        for pv in pv_names:
            if not self._check_pv_exists(pv):
                missing_pvs.append(pv)

        if missing_pvs:
            # Tenter de créer les volumes physiques manquants
            self.log_warning(f"Les volumes physiques suivants n'existent pas: {', '.join(missing_pvs)}")
            self.log_info("Tentative de création des volumes physiques manquants...")

            pv_success = self.create_physical_volume(missing_pvs)
            if not pv_success:
                return False

        # Vérifier si le groupe de volumes existe déjà
        if self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes {vg_name} existe déjà")
            return False

        self.log_info(f"Création du groupe de volumes LVM '{vg_name}' avec les volumes physiques: {', '.join(pv_names)}")

        # Construire la commande
        cmd = ['vgcreate']

        if force:
            cmd.append('--force')

        if cluster:
            cmd.extend(['--clustered', 'y'])

        cmd.append(vg_name)
        cmd.extend(pv_names)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' créé avec succès")
            return True
        else:
            self.log_error(f"Échec de la création du groupe de volumes '{vg_name}': {stderr}")
            return False

    def remove_volume_group(self, vg_name, force=False):
        """
        Supprime un groupe de volumes LVM.

        Args:
            vg_name: Nom du groupe de volumes à supprimer
            force: Si True, force la suppression même si des warnings sont détectés

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier s'il y a des volumes logiques actifs
        lvs = self.list_logical_volumes(vg_name)
        if lvs and not force:
            self.log_error(f"Le groupe de volumes '{vg_name}' contient des volumes logiques. Utilisez force=True pour forcer la suppression")
            return False

        # Supprimer les volumes logiques d'abord si force est True
        if lvs and force:
            self.log_warning(f"Suppression forcée des volumes logiques dans '{vg_name}'")
            for lv in lvs:
                self.remove_logical_volume(vg_name, lv['name'], force=True)

        self.log_info(f"Suppression du groupe de volumes '{vg_name}'")

        cmd = ['vgremove']

        if force:
            cmd.append('--force')

        cmd.append(vg_name)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' supprimé avec succès")
            return True
        else:
            self.log_error(f"Échec de la suppression du groupe de volumes '{vg_name}': {stderr}")
            return False

    def extend_volume_group(self, vg_name, pv_names):
        """
        Étend un groupe de volumes LVM en ajoutant de nouveaux volumes physiques.

        Args:
            vg_name: Nom du groupe de volumes à étendre
            pv_names: Volume physique ou liste de volumes physiques à ajouter

        Returns:
            bool: True si l'extension a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(pv_names, str):
            pv_names = [pv_names]

        if not pv_names:
            self.log_error("Aucun volume physique spécifié pour l'extension du groupe de volumes")
            return False

        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier si les volumes physiques existent et sont disponibles
        missing_pvs = []
        used_pvs = []

        for pv in pv_names:
            if not self._check_pv_exists(pv):
                missing_pvs.append(pv)
            else:
                pv_info = self._get_pv_info(pv)
                if pv_info and pv_info.get('vg_name') and pv_info.get('vg_name') != '':
                    if pv_info.get('vg_name') == vg_name:
                        used_pvs.append(pv)  # Déjà dans ce VG
                    else:
                        missing_pvs.append(pv)  # Utilisé par un autre VG

        if missing_pvs:
            # Tenter de créer les volumes physiques manquants
            self.log_warning(f"Les volumes physiques suivants ne sont pas disponibles: {', '.join(missing_pvs)}")
            create_new = []

            for pv in missing_pvs:
                if os.path.exists(pv) and not self._check_pv_exists(pv):
                    create_new.append(pv)

            if create_new:
                self.log_info("Tentative de création des volumes physiques manquants...")
                self.create_physical_volume(create_new)

        # Filtrer les PVs déjà utilisés par ce VG
        pv_names = [pv for pv in pv_names if pv not in used_pvs]

        if not pv_names:
            self.log_warning(f"Aucun volume physique disponible pour l'extension")
            return True  # Pas d'erreur, mais rien à faire

        self.log_info(f"Extension du groupe de volumes '{vg_name}' avec les volumes physiques: {', '.join(pv_names)}")

        cmd = ['vgextend', vg_name]
        cmd.extend(pv_names)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' étendu avec succès")
            return True
        else:
            self.log_error(f"Échec de l'extension du groupe de volumes '{vg_name}': {stderr}")
            return False

    def reduce_volume_group(self, vg_name, pv_names):
        """
        Réduit un groupe de volumes LVM en retirant des volumes physiques.

        Args:
            vg_name: Nom du groupe de volumes à réduire
            pv_names: Volume physique ou liste de volumes physiques à retirer

        Returns:
            bool: True si la réduction a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(pv_names, str):
            pv_names = [pv_names]

        if not pv_names:
            self.log_error("Aucun volume physique spécifié pour la réduction du groupe de volumes")
            return False

        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier si les volumes physiques sont dans ce groupe
        for pv in pv_names:
            pv_info = self._get_pv_info(pv)
            if not pv_info or pv_info.get('vg_name') != vg_name:
                self.log_error(f"Le volume physique {pv} n'appartient pas au groupe de volumes {vg_name}")
                return False

        # Vérifier s'il reste assez d'espace pour déplacer les données
        vg_info = self._get_vg_info(vg_name)

        total_space_to_remove = 0
        for pv in pv_names:
            pv_info = self._get_pv_info(pv)
            if pv_info:
                total_space_to_remove += pv_info.get('pv_used', 0)

        remaining_vg_size = vg_info.get('vg_size', 0) - total_space_to_remove
        if remaining_vg_size < 0:
            self.log_error(f"Espace insuffisant dans le groupe pour déplacer les données des volumes physiques à retirer")
            return False

        self.log_info(f"Réduction du groupe de volumes '{vg_name}' en retirant les volumes physiques: {', '.join(pv_names)}")

        # Déplacer d'abord les données hors des PVs à retirer
        for pv in pv_names:
            self.log_info(f"Déplacement des données hors du volume physique {pv}")
            pvmove_cmd = ['pvmove', pv]
            pvmove_success, _, pvmove_stderr = self.run_as_root(pvmove_cmd)

            if not pvmove_success:
                self.log_error(f"Échec du déplacement des données hors de {pv}: {pvmove_stderr}")
                return False

        # Retirer les volumes physiques
        cmd = ['vgreduce', vg_name]
        cmd.extend(pv_names)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' réduit avec succès")
            return True
        else:
            self.log_error(f"Échec de la réduction du groupe de volumes '{vg_name}': {stderr}")
            return False

    def create_logical_volume(self, vg_name, lv_name, size, filesystem=None, mount_point, size_str)
        if not match:
            return None

        value = float(match.group(1))
        unit = match.group(2) if match.group(2) else 'B'

        # Convertir en octets
        multipliers = {
            'B': 1,
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }

        return int(value * multipliers.get(unit, 1))

    def _format_bytes(self, bytes, precision=2):
        """
        Formate un nombre d'octets en une chaîne lisible par l'homme.

        Args:
            bytes: Nombre d'octets
            precision: Nombre de décimales

        Returns:
            str: Taille formatée (ex: "5.25 GB")
        """
        if bytes < 0:
            return "0 B"

        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

        i = 0
        while bytes >= 1024 and i < len(units) - 1:
            bytes /= 1024
            i += 1

        return f"{bytes:.{precision}f} {units[i]}"    def create_logical_volume(self, vg_name, lv_name, size, filesystem=None, mount_point=None, mount_options=None):
        """
        Crée un nouveau volume logique LVM.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à créer
            size: Taille du volume (ex: '5G', '500M')
            filesystem: Système de fichiers à créer (ex: 'ext4', 'xfs')
            mount_point: Point de montage (optionnel)
            mount_options: Options de montage (optionnel)

        Returns:
            bool: True si la création a réussi, False sinon
        """
        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier si le volume logique existe déjà
        if self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' existe déjà dans le groupe '{vg_name}'")
            return False

        # Vérifier si le groupe a assez d'espace
        vg_info = self._get_vg_info(vg_name)
        if not vg_info:
            self.log_error(f"Impossible d'obtenir les informations sur le groupe '{vg_name}'")
            return False

        # Convertir la taille en octets pour comparaison
        size_bytes = self._convert_size_to_bytes(size)
        if size_bytes > vg_info.get('vg_free', 0):
            self.log_error(f"Espace insuffisant dans le groupe '{vg_name}' pour créer un volume de {size}")
            self.log_error(f"Espace disponible: {self._format_bytes(vg_info.get('vg_free', 0))}")
            return False

        self.log_info(f"Création du volume logique '{lv_name}' de taille {size} dans le groupe '{vg_name}'")

        # Créer le volume logique
        cmd = ['lvcreate', '--name', lv_name, '--size', size, vg_name]
        success, stdout, stderr = self.run_as_root(cmd)

        if not success:
            self.log_error(f"Échec de la création du volume logique '{lv_name}': {stderr}")
            return False

        self.log_success(f"Volume logique '{lv_name}' créé avec succès")

        # Chemin complet du volume
        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Créer un système de fichiers si demandé
        if filesystem:
            self.log_info(f"Création du système de fichiers {filesystem} sur '{lv_path}'")

            format_cmd = ['mkfs', '-t', filesystem]

            # Options spécifiques selon le système de fichiers
            if filesystem == 'ext4':
                format_cmd.extend(['-F', lv_path])
            elif filesystem == 'xfs':
                format_cmd.extend(['-f', lv_path])
            else:
                format_cmd.append(lv_path)

            format_success, _, format_stderr = self.run_as_root(format_cmd)

            if not format_success:
                self.log_error(f"Échec de la création du système de fichiers {filesystem} sur '{lv_path}': {format_stderr}")
                return False

            self.log_success(f"Système de fichiers {filesystem} créé avec succès sur '{lv_path}'")

        # Monter le volume si un point de montage est spécifié
        if mount_point:
            # Créer le point de montage s'il n'existe pas
            if not os.path.exists(mount_point):
                mkdir_cmd = ['mkdir', '-p', mount_point]
                self.run_as_root(mkdir_cmd)

            # Monter le volume
            self.log_info(f"Montage de '{lv_path}' sur '{mount_point}'")

            mount_cmd = ['mount']
            if mount_options:
                mount_cmd.extend(['-o', mount_options])
            mount_cmd.extend([lv_path, mount_point])

            mount_success, _, mount_stderr = self.run_as_root(mount_cmd)

            if not mount_success:
                self.log_error(f"Échec du montage de '{lv_path}' sur '{mount_point}': {mount_stderr}")
                return False

            self.log_success(f"Volume '{lv_path}' monté avec succès sur '{mount_point}'")

            # Ajouter au fstab pour montage persistant
            self._add_fstab_entry(lv_path, mount_point, filesystem, mount_options)

        return True

    def extend_logical_volume(self, vg_name, lv_name, additional_size, resize_fs=True):
        """
        Étend un volume logique LVM existant.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à étendre
            additional_size: Taille supplémentaire (ex: '+5G', '+500M')
            resize_fs: Si True, redimensionne aussi le système de fichiers

        Returns:
            bool: True si l'extension a réussi, False sinon
        """
        # Vérifier si le volume existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # S'assurer que la taille supplémentaire commence par '+'
        if not additional_size.startswith('+'):
            additional_size = '+' + additional_size

        # Vérifier si le groupe a assez d'espace
        vg_info = self._get_vg_info(vg_name)
        if not vg_info:
            self.log_error(f"Impossible d'obtenir les informations sur le groupe '{vg_name}'")
            return False

        # Convertir la taille en octets pour comparaison
        size_bytes = self._convert_size_to_bytes(additional_size[1:])  # Enlever le '+'
        if size_bytes > vg_info.get('vg_free', 0):
            self.log_error(f"Espace insuffisant dans le groupe '{vg_name}' pour étendre le volume de {additional_size}")
            self.log_error(f"Espace disponible: {self._format_bytes(vg_info.get('vg_free', 0))}")
            return False

        self.log_info(f"Extension du volume logique '{lv_name}' de {additional_size}")

        # Chemin complet du volume
        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Étendre le volume logique
        cmd = ['lvextend', '--size', additional_size]

        if resize_fs:
            cmd.append('--resizefs')

        cmd.append(lv_path)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume logique '{lv_name}' étendu avec succès")
        else:
            self.log_error(f"Échec de l'extension du volume logique '{lv_name}': {stderr}")

        return success

    def reduce_logical_volume(self, vg_name, lv_name, size_reduction, resize_fs=True, force=False):
        """
        Réduit la taille d'un volume logique LVM.
        ATTENTION: Cette opération est risquée et peut entraîner une perte de données.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à réduire
            size_reduction: Réduction de taille (ex: '-2G', '-500M')
            resize_fs: Si True, redimensionne aussi le système de fichiers
            force: Si True, force la réduction même en cas d'avertissements

        Returns:
            bool: True si la réduction a réussi, False sinon
        """
        # Vérifier si le volume existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # S'assurer que la taille de réduction commence par '-'
        if not size_reduction.startswith('-'):
            size_reduction = '-' + size_reduction

        self.log_warning(f"Réduction du volume logique '{lv_name}' de {size_reduction}. Cette opération est risquée!")

        # Chemin complet du volume
        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Vérifier le système de fichiers
        fs_type = self._get_fs_type(lv_path)

        if fs_type and resize_fs:
            # Réduire le système de fichiers d'abord pour ext4
            if 'ext' in fs_type.lower():
                # Démonter si nécessaire
                is_mounted = self._is_mounted(lv_path)
                mount_point = None

                if is_mounted:
                    mount_point = self._get_mount_point(lv_path)
                    umount_cmd = ['umount', lv_path]
                    umount_success, _, _ = self.run_as_root(umount_cmd)

                    if not umount_success:
                        self.log_error(f"Impossible de démonter '{lv_path}' pour redimensionner le système de fichiers")
                        return False

                # Vérifier le système de fichiers
                fsck_cmd = ['e2fsck', '-f', lv_path]
                self.run_as_root(fsck_cmd)

                # Obtenir la nouvelle taille en blocs
                # Pour cela, nous devons connaître la taille actuelle et soustraire la réduction
                lvs_cmd = ['lvdisplay', '--units', 'B', lv_path]
                lvs_success, lvs_stdout, _ = self.run_as_root(lvs_cmd, no_output=True)

                current_size_bytes = None
                if lvs_success:
                    for line in lvs_stdout.splitlines():
                        if "LV Size" in line:
                            size_match = re.search(r'(\d+) B', line)
                            if size_match:
                                current_size_bytes = int(size_match.group(1))
                                break

                if not current_size_bytes:
                    self.log_error("Impossible de déterminer la taille actuelle du volume")
                    return False

                # Convertir la réduction en octets
                reduction_bytes = self._convert_size_to_bytes(size_reduction[1:])  # Enlever le '-'
                new_size_bytes = current_size_bytes - reduction_bytes

                # Réduire le système de fichiers (la taille doit être en blocs de 4K pour resize2fs)
                block_size = 4096  # Taille de bloc standard pour ext4
                new_size_blocks = new_size_bytes // block_size

                resize_cmd = ['resize2fs', lv_path, str(new_size_blocks) + 'K']
                resize_success, _, resize_stderr = self.run_as_root(resize_cmd)

                if not resize_success:
                    self.log_error(f"Échec du redimensionnement du système de fichiers: {resize_stderr}")

                    # Remonter si nécessaire
                    if mount_point:
                        mount_cmd = ['mount', lv_path, mount_point]
                        self.run_as_root(mount_cmd)

                    return False

                # Remonter si nécessaire
                if mount_point:
                    mount_cmd = ['mount', lv_path, mount_point]
                    self.run_as_root(mount_cmd)

        # Réduire le volume logique
        cmd = ['lvreduce']

        if force:
            cmd.append('--force')

        cmd.extend(['--size', size_reduction, lv_path])

        if not resize_fs:
            # Demander confirmation
            self.log_warning("ATTENTION: Vous avez choisi de ne pas redimensionner le système de fichiers.")
            self.log_warning("Cela peut entraîner une corruption des données si le système de fichiers est plus grand que le volume.")

            if not force:
                self.log_error("Opération annulée pour sécurité. Utilisez force=True pour forcer la réduction.")
                return False

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume logique '{lv_name}' réduit avec succès")
        else:
            self.log_error(f"Échec de la réduction du volume logique '{lv_name}': {stderr}")

        return success

    def remove_logical_volume(self, vg_name, lv_name, force=False):
        """
        Supprime un volume logique LVM.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique à supprimer
            force: Si True, force la suppression même si le volume est utilisé

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        # Vérifier si le volume existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        lv_path = f"/dev/{vg_name}/{lv_name}"

        # Démonter le volume s'il est monté
        if self._is_mounted(lv_path):
            self.log_info(f"Démontage du volume '{lv_path}'")
            umount_cmd = ['umount', lv_path]
            umount_success, _, umount_stderr = self.run_as_root(umount_cmd)

            if not umount_success and not force:
                self.log_error(f"Impossible de démonter '{lv_path}': {umount_stderr}")
                return False

            # Supprimer les entrées fstab
            self._remove_fstab_entry(lv_path)

        self.log_info(f"Suppression du volume logique '{lv_name}' du groupe '{vg_name}'")

        cmd = ['lvremove']

        if force:
            cmd.extend(['--force', '--yes'])

        cmd.append(lv_path)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume logique '{lv_name}' supprimé avec succès")
        else:
            self.log_error(f"Échec de la suppression du volume logique '{lv_name}': {stderr}")

        return success

    def create_snapshot(self, vg_name, lv_name, snapshot_name, size='5G', merge_on_close=False):
        """
        Crée un instantané d'un volume logique LVM.

        Args:
            vg_name: Nom du groupe de volumes
            lv_name: Nom du volume logique source
            snapshot_name: Nom du snapshot à créer
            size: Taille de l'espace pour les modifications (ex: '5G')
            merge_on_close: Si True, configure pour fusionner au prochain redémarrage

        Returns:
            bool: True si la création du snapshot a réussi, False sinon
        """
        # Vérifier si le volume source existe
        if not self._check_lv_exists(vg_name, lv_name):
            self.log_error(f"Le volume logique source '{lv_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # Vérifier si le snapshot existe déjà
        if self._check_lv_exists(vg_name, snapshot_name):
            self.log_error(f"Un volume logique '{snapshot_name}' existe déjà dans le groupe '{vg_name}'")
            return False

        # Vérifier si le groupe a assez d'espace
        vg_info = self._get_vg_info(vg_name)
        if not vg_info:
            self.log_error(f"Impossible d'obtenir les informations sur le groupe '{vg_name}'")
            return False

        # Convertir la taille en octets pour comparaison
        size_bytes = self._convert_size_to_bytes(size)
        if size_bytes > vg_info.get('vg_free', 0):
            self.log_error(f"Espace insuffisant dans le groupe '{vg_name}' pour créer un snapshot de {size}")
            self.log_error(f"Espace disponible: {self._format_bytes(vg_info.get('vg_free', 0))}")
            return False

        self.log_info(f"Création d'un snapshot '{snapshot_name}' du volume '{lv_name}' avec taille {size}")

        cmd = ['lvcreate', '--snapshot', '--name', snapshot_name, '--size', size, f"/dev/{vg_name}/{lv_name}"]
        success, stdout, stderr = self.run_as_root(cmd)

        if not success:
            self.log_error(f"Échec de la création du snapshot '{snapshot_name}': {stderr}")
            return False

        self.log_success(f"Snapshot '{snapshot_name}' créé avec succès")

        # Configurer la fusion automatique si demandé
        if merge_on_close:
            self.log_info(f"Configuration du snapshot '{snapshot_name}' pour fusion au prochain redémarrage")
            merge_cmd = ['lvchange', '--merge', f"/dev/{vg_name}/{snapshot_name}"]
            merge_success, _, merge_stderr = self.run_as_root(merge_cmd)

            if not merge_success:
                self.log_error(f"Échec de la configuration de fusion pour '{snapshot_name}': {merge_stderr}")
                return False

            self.log_success(f"Snapshot '{snapshot_name}' configuré pour fusion au prochain redémarrage")

        return True

    def merge_snapshot(self, vg_name, snapshot_name, activate=True):
        """
        Fusionne un snapshot avec son volume source.

        Args:
            vg_name: Nom du groupe de volumes
            snapshot_name: Nom du snapshot à fusionner
            activate: Si True, active la fusion immédiatement si possible

        Returns:
            bool: True si la fusion a démarré avec succès, False sinon
        """
        # Vérifier si le snapshot existe
        if not self._check_lv_exists(vg_name, snapshot_name):
            self.log_error(f"Le snapshot '{snapshot_name}' n'existe pas dans le groupe '{vg_name}'")
            return False

        # Vérifier si c'est un snapshot
        lv_info = self._get_lv_info(vg_name, snapshot_name)
        if not lv_info or 's' not in lv_info.get('attributes', ''):
            self.log_error(f"Le volume '{snapshot_name}' n'est pas un snapshot")
            return False

        self.log_info(f"Configuration du snapshot '{snapshot_name}' pour fusion")

        # Configurer la fusion
        merge_cmd = ['lvchange', '--merge', f"/dev/{vg_name}/{snapshot_name}"]
        merge_success, _, merge_stderr = self.run_as_root(merge_cmd)

        if not merge_success:
            self.log_error(f"Échec de la configuration de fusion pour '{snapshot_name}': {merge_stderr}")
            return False

        self.log_success(f"Snapshot '{snapshot_name}' configuré pour fusion")

        # Activer la fusion maintenant si demandé et possible
        if activate:
            self.log_info("Tentative d'activation de la fusion immédiatement")

            # Pour activer la fusion immédiatement, il faut désactiver puis réactiver le VG
            # Vérifier d'abord si le volume source est monté
            origin_name = None

            for line in lv_info.get('origin', '').splitlines():
                if line.strip():
                    origin_name = line.strip()
                    break

            if origin_name and self._is_mounted(f"/dev/{vg_name}/{origin_name}"):
                self.log_warning(f"Le volume source '{origin_name}' est monté, la fusion sera effectuée au prochain redémarrage")
                return True

            # Désactiver le groupe
            self.log_info(f"Désactivation du groupe '{vg_name}' pour préparer la fusion")
            deact_cmd = ['vgchange', '-an', vg_name]
            deact_success, _, _ = self.run_as_root(deact_cmd)

            if not deact_success:
                self.log_warning("Impossible de désactiver le groupe, la fusion sera effectuée au prochain redémarrage")
                return True

            # Réactiver le groupe
            self.log_info(f"Réactivation du groupe '{vg_name}' pour finaliser la fusion")
            act_cmd = ['vgchange', '-ay', vg_name]
            act_success, _, _ = self.run_as_root(act_cmd)

            if not act_success:
                self.log_warning("Impossible de réactiver le groupe, la fusion sera effectuée au prochain redémarrage")
                # Tenter de réactiver quand même
                self.run_as_root(['vgchange', '-ay', vg_name])
                return True

            self.log_success("Fusion du snapshot activée avec succès")
        else:
            self.log_info("La fusion sera effectuée au prochain redémarrage")

        return True

    def list_volume_groups(self):
        """
        Liste tous les groupes de volumes LVM disponibles.

        Returns:
            list: Liste de dictionnaires avec les informations des groupes de volumes
        """
        self.log_info("Listage des groupes de volumes LVM")

        cmd = ['vgs', '--noheadings', '--options', 'vg_name,vg_size,vg_free,vg_extent_count,vg_attr', '--units', 'b']
        success, stdout, stderr = self.run_as_root(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec du listage des groupes de volumes: {stderr}")
            return []

        vgs = []
        for line in stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                vg = {
                    'name': parts[0],
                    'size': self._format_bytes(int(parts[1].rstrip('B'))),
                    'size_bytes': int(parts[1].rstrip('B')),
                    'free': self._format_bytes(int(parts[2].rstrip('B'))),
                    'free_bytes': int(parts[2].rstrip('B')),
                    'extents': parts[3],
                    'attributes': parts[4]
                }
                vgs.append(vg)

        self.log_info(f"Trouvé {len(vgs)} groupe(s) de volumes")
        return vgs

    def list_physical_volumes(self, vg_name=None):
        """
        Liste tous les volumes physiques LVM disponibles.

        Args:
            vg_name: Nom du groupe de volumes à filtrer (optionnel)

        Returns:
            list: Liste de dictionnaires avec les informations des volumes physiques
        """
        if vg_name:
            self.log_info(f"Listage des volumes physiques dans le groupe '{vg_name}'")
        else:
            self.log_info("Listage de tous les volumes physiques LVM")

        cmd = ['pvs', '--noheadings', '--options', 'pv_name,vg_name,pv_size,pv_free,pv_attr', '--units', 'b']

        if vg_name:
            cmd.append(vg_name)

        success, stdout, stderr = self.run_as_root(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec du listage des volumes physiques: {stderr}")
            return []

        pvs = []
        for line in stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                pv = {
                    'name': parts[0],
                    'vg_name': parts[1] if parts[1] != "" else None,
                    'size': self._format_bytes(int(parts[2].rstrip('B'))),
                    'size_bytes': int(parts[2].rstrip('B')),
                    'free': self._format_bytes(int(parts[3].rstrip('B'))),
                    'free_bytes': int(parts[3].rstrip('B')),
                    'attributes': parts[4]
                }
                pvs.append(pv)

        if vg_name:
            self.log_info(f"Trouvé {len(pvs)} volume(s) physique(s) dans le groupe '{vg_name}'")
        else:
            self.log_info(f"Trouvé {len(pvs)} volume(s) physique(s) au total")

        return pvs

    def list_logical_volumes(self, vg_name=None):
        """
        Liste tous les volumes logiques LVM disponibles.

        Args:
            vg_name: Nom du groupe de volumes à filtrer (optionnel)

        Returns:
            list: Liste de dictionnaires avec les informations des volumes logiques
        """
        if vg_name:
            self.log_info(f"Listage des volumes logiques dans le groupe '{vg_name}'")
        else:
            self.log_info("Listage de tous les volumes logiques LVM")

        cmd = ['lvs', '--noheadings', '--options', 'vg_name,lv_name,lv_size,lv_attr,lv_path,origin', '--units', 'b']

        if vg_name:
            cmd.append(vg_name)

        success, stdout, stderr = self.run_as_root(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec du listage des volumes logiques: {stderr}")
            return []

        lvs = []
        for line in stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                lv = {
                    'vg_name': parts[0],
                    'name': parts[1],
                    'size': self._format_bytes(int(parts[2].rstrip('B'))),
                    'size_bytes': int(parts[2].rstrip('B')),
                    'attributes': parts[3],
                    'path': parts[4]
                }

                # Déterminer si c'est un snapshot
                if 's' in lv['attributes']:
                    lv['is_snapshot'] = True
                    if len(parts) >= 6:
                        lv['origin'] = parts[5]
                else:
                    lv['is_snapshot'] = False

                # Vérifier si le volume est monté
                lv['mounted'] = self._is_mounted(lv['path'])
                if lv['mounted']:
                    lv['mount_point'] = self._get_mount_point(lv['path'])

                lvs.append(lv)

        if vg_name:
            self.log_info(f"Trouvé {len(lvs)} volume(s) logique(s) dans le groupe '{vg_name}'")
        else:
            self.log_info(f"Trouvé {len(lvs)} volume(s) logique(s) au total")

        return lvs

    def repair_volume_group_metadata(self, vg_name):
        """
        Tente de réparer les métadonnées LVM d'un groupe de volumes.

        Args:
            vg_name: Nom du groupe de volumes à réparer

        Returns:
            bool: True si la réparation a réussi, False sinon
        """
        self.log_warning(f"Tentative de réparation des métadonnées du groupe '{vg_name}'")

        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas ou n'est pas accessible")
            return False

        # Sauvegarde des métadonnées
        backup_cmd = ['vgcfgbackup', vg_name]
        backup_success, _, backup_stderr = self.run_as_root(backup_cmd)

        if not backup_success:
            self.log_warning(f"Impossible de sauvegarder les métadonnées du groupe '{vg_name}': {backup_stderr}")

        # Vérification des métadonnées
        check_cmd = ['vgck', vg_name]
        check_success, _, check_stderr = self.run_as_root(check_cmd)

        if check_success:
            self.log_info(f"Les métadonnées du groupe '{vg_name}' semblent intactes")
        else:
            self.log_warning(f"Des problèmes détectés dans les métadonnées du groupe '{vg_name}': {check_stderr}")

        # Restauration des métadonnées depuis la sauv#!/usr/bin/env python3
"""
Module utilitaire pour la gestion avancée des volumes logiques LVM.
Permet de créer, modifier, supprimer et gérer des groupes de volumes,
volumes logiques et snapshots LVM.
"""

from .commands import Commands
import os
import re
import time
import json
import tempfile


class LvmCommands(Commands):
    """
    Classe pour gérer les volumes logiques LVM.
    Hérite de la classe Commands pour la gestion des commandes système.
    """

    def create_physical_volume(self, devices):
        """
        Initialise un ou plusieurs périphériques comme volumes physiques LVM.

        Args:
            devices: Périphérique ou liste de périphériques à initialiser

        Returns:
            bool: True si l'initialisation a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(devices, str):
            devices = [devices]

        if not devices:
            self.log_error("Aucun périphérique spécifié")
            return False

        # Vérifier si les périphériques existent
        missing_devices = []
        for device in devices:
            if not os.path.exists(device):
                missing_devices.append(device)

        if missing_devices:
            self.log_error(f"Les périphériques suivants n'existent pas: {', '.join(missing_devices)}")
            return False

        self.log_info(f"Initialisation de {len(devices)} périphérique(s) comme volumes physiques LVM")

        # Initialiser les volumes physiques
        cmd = ['pvcreate', '--yes']
        cmd.extend(devices)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volumes physiques créés avec succès: {', '.join(devices)}")
            return True
        else:
            self.log_error(f"Échec de la création des volumes physiques: {stderr}")
            return False

    def remove_physical_volume(self, pv_name):
        """
        Supprime un volume physique LVM.

        Args:
            pv_name: Nom du volume physique à supprimer

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        # Vérifier si le volume physique existe
        if not self._check_pv_exists(pv_name):
            self.log_error(f"Le volume physique {pv_name} n'existe pas")
            return False

        # Vérifier si le volume physique est utilisé par un groupe de volumes
        pv_info = self._get_pv_info(pv_name)
        if pv_info and pv_info.get('vg_name') and pv_info.get('vg_name') != '':
            self.log_error(f"Le volume physique {pv_name} est utilisé par le groupe de volumes {pv_info.get('vg_name')}")
            return False

        self.log_info(f"Suppression du volume physique {pv_name}")

        # Supprimer le volume physique
        cmd = ['pvremove', '--yes', pv_name]
        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Volume physique {pv_name} supprimé avec succès")
            return True
        else:
            self.log_error(f"Échec de la suppression du volume physique {pv_name}: {stderr}")
            return False

    def create_volume_group(self, vg_name, pv_names, force=False, cluster=False):
        """
        Crée un nouveau groupe de volumes LVM.

        Args:
            vg_name: Nom du groupe de volumes
            pv_names: Périphérique ou liste de périphériques à inclure dans le VG
            force: Si True, force la création même si des warnings sont détectés
            cluster: Si True, active le mode cluster

        Returns:
            bool: True si la création a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(pv_names, str):
            pv_names = [pv_names]

        if not pv_names:
            self.log_error("Aucun volume physique spécifié pour le groupe de volumes")
            return False

        # Vérifier si les volumes physiques existent
        missing_pvs = []
        for pv in pv_names:
            if not self._check_pv_exists(pv):
                missing_pvs.append(pv)

        if missing_pvs:
            # Tenter de créer les volumes physiques manquants
            self.log_warning(f"Les volumes physiques suivants n'existent pas: {', '.join(missing_pvs)}")
            self.log_info("Tentative de création des volumes physiques manquants...")

            pv_success = self.create_physical_volume(missing_pvs)
            if not pv_success:
                return False

        # Vérifier si le groupe de volumes existe déjà
        if self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes {vg_name} existe déjà")
            return False

        self.log_info(f"Création du groupe de volumes LVM '{vg_name}' avec les volumes physiques: {', '.join(pv_names)}")

        # Construire la commande
        cmd = ['vgcreate']

        if force:
            cmd.append('--force')

        if cluster:
            cmd.extend(['--clustered', 'y'])

        cmd.append(vg_name)
        cmd.extend(pv_names)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' créé avec succès")
            return True
        else:
            self.log_error(f"Échec de la création du groupe de volumes '{vg_name}': {stderr}")
            return False

    def remove_volume_group(self, vg_name, force=False):
        """
        Supprime un groupe de volumes LVM.

        Args:
            vg_name: Nom du groupe de volumes à supprimer
            force: Si True, force la suppression même si des warnings sont détectés

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier s'il y a des volumes logiques actifs
        lvs = self.list_logical_volumes(vg_name)
        if lvs and not force:
            self.log_error(f"Le groupe de volumes '{vg_name}' contient des volumes logiques. Utilisez force=True pour forcer la suppression")
            return False

        # Supprimer les volumes logiques d'abord si force est True
        if lvs and force:
            self.log_warning(f"Suppression forcée des volumes logiques dans '{vg_name}'")
            for lv in lvs:
                self.remove_logical_volume(vg_name, lv['name'], force=True)

        self.log_info(f"Suppression du groupe de volumes '{vg_name}'")

        cmd = ['vgremove']

        if force:
            cmd.append('--force')

        cmd.append(vg_name)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' supprimé avec succès")
            return True
        else:
            self.log_error(f"Échec de la suppression du groupe de volumes '{vg_name}': {stderr}")
            return False

    def extend_volume_group(self, vg_name, pv_names):
        """
        Étend un groupe de volumes LVM en ajoutant de nouveaux volumes physiques.

        Args:
            vg_name: Nom du groupe de volumes à étendre
            pv_names: Volume physique ou liste de volumes physiques à ajouter

        Returns:
            bool: True si l'extension a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(pv_names, str):
            pv_names = [pv_names]

        if not pv_names:
            self.log_error("Aucun volume physique spécifié pour l'extension du groupe de volumes")
            return False

        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier si les volumes physiques existent et sont disponibles
        missing_pvs = []
        used_pvs = []

        for pv in pv_names:
            if not self._check_pv_exists(pv):
                missing_pvs.append(pv)
            else:
                pv_info = self._get_pv_info(pv)
                if pv_info and pv_info.get('vg_name') and pv_info.get('vg_name') != '':
                    if pv_info.get('vg_name') == vg_name:
                        used_pvs.append(pv)  # Déjà dans ce VG
                    else:
                        missing_pvs.append(pv)  # Utilisé par un autre VG

        if missing_pvs:
            # Tenter de créer les volumes physiques manquants
            self.log_warning(f"Les volumes physiques suivants ne sont pas disponibles: {', '.join(missing_pvs)}")
            create_new = []

            for pv in missing_pvs:
                if os.path.exists(pv) and not self._check_pv_exists(pv):
                    create_new.append(pv)

            if create_new:
                self.log_info("Tentative de création des volumes physiques manquants...")
                self.create_physical_volume(create_new)

        # Filtrer les PVs déjà utilisés par ce VG
        pv_names = [pv for pv in pv_names if pv not in used_pvs]

        if not pv_names:
            self.log_warning(f"Aucun volume physique disponible pour l'extension")
            return True  # Pas d'erreur, mais rien à faire

        self.log_info(f"Extension du groupe de volumes '{vg_name}' avec les volumes physiques: {', '.join(pv_names)}")

        cmd = ['vgextend', vg_name]
        cmd.extend(pv_names)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' étendu avec succès")
            return True
        else:
            self.log_error(f"Échec de l'extension du groupe de volumes '{vg_name}': {stderr}")
            return False

    def reduce_volume_group(self, vg_name, pv_names):
        """
        Réduit un groupe de volumes LVM en retirant des volumes physiques.

        Args:
            vg_name: Nom du groupe de volumes à réduire
            pv_names: Volume physique ou liste de volumes physiques à retirer

        Returns:
            bool: True si la réduction a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(pv_names, str):
            pv_names = [pv_names]

        if not pv_names:
            self.log_error("Aucun volume physique spécifié pour la réduction du groupe de volumes")
            return False

        # Vérifier si le groupe existe
        if not self._check_vg_exists(vg_name):
            self.log_error(f"Le groupe de volumes '{vg_name}' n'existe pas")
            return False

        # Vérifier si les volumes physiques sont dans ce groupe
        for pv in pv_names:
            pv_info = self._get_pv_info(pv)
            if not pv_info or pv_info.get('vg_name') != vg_name:
                self.log_error(f"Le volume physique {pv} n'appartient pas au groupe de volumes {vg_name}")
                return False

        # Vérifier s'il reste assez d'espace pour déplacer les données
        vg_info = self._get_vg_info(vg_name)

        total_space_to_remove = 0
        for pv in pv_names:
            pv_info = self._get_pv_info(pv)
            if pv_info:
                total_space_to_remove += pv_info.get('pv_used', 0)

        remaining_vg_size = vg_info.get('vg_size', 0) - total_space_to_remove
        if remaining_vg_size < 0:
            self.log_error(f"Espace insuffisant dans le groupe pour déplacer les données des volumes physiques à retirer")
            return False

        self.log_info(f"Réduction du groupe de volumes '{vg_name}' en retirant les volumes physiques: {', '.join(pv_names)}")

        # Déplacer d'abord les données hors des PVs à retirer
        for pv in pv_names:
            self.log_info(f"Déplacement des données hors du volume physique {pv}")
            pvmove_cmd = ['pvmove', pv]
            pvmove_success, _, pvmove_stderr = self.run_as_root(pvmove_cmd)

            if not pvmove_success:
                self.log_error(f"Échec du déplacement des données hors de {pv}: {pvmove_stderr}")
                return False

        # Retirer les volumes physiques
        cmd = ['vgreduce', vg_name]
        cmd.extend(pv_names)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Groupe de volumes '{vg_name}' réduit avec succès")
            return True
        else:
            self.log_error(f"Échec de la réduction du groupe de volumes '{vg_name}': {stderr}")
            return False

    def create_logical_volume(self, vg_name, lv_name, size, filesystem=None, mount_point